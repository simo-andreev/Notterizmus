"""OutlineEditor, part: copy, cut and paste of items and text (the app's own JSON, TopCoding's editor's
JSON, HTML, plain text)."""
from __future__ import annotations

import json

from gi.repository import Gdk, Gio, GLib

from .. import lexical
from ..export import runs_html, to_html, to_plain
from ..importer import block_nodes, html_items, join_lines, parse, text_items
from ..layout import layout
from ..model import (Node, Run, can_contain, enclosing_heading, fresh_ids, leaf_insert_index, runs_from_json,
                     runs_text, runs_to_json, selected_json)
from .rows import TextRow

NODES_MIME = "application/x-notterizmus-nodes+json"
RUNS_MIME = "application/x-notterizmus-runs+json"
TEXT_MIMES = ["text/plain;charset=utf-8", "text/plain"]
# A copy from TopCoding's editor: read first, and used only when it has a drawing.
EDITOR_MIMES = [lexical.CHROME_CUSTOM_MIME, lexical.FIREFOX_CUSTOM_MIME]


def _bytes(s):
    return GLib.Bytes.new(s if isinstance(s, bytes) else s.encode("utf-8"))


def export_formats(lines, rules):
    """(MIME type, data) pairs of an export for the clipboard: HTML and plain text, and,
    when there is a drawing, the form TopCoding's editor takes drawings in."""
    code_prefix = rules["export"]["code_prefix"]
    plain = to_plain(lines)
    custom = lexical.clipboard_data(lines, code_prefix)
    return (custom or []) \
        + [("text/html", to_html(lines, code_prefix=code_prefix))] + [(m, plain) for m in TEXT_MIMES]


def _decode(raw):
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(raw) > 1 and raw[1:2] == b"\x00"):
        return raw.decode("utf-16", errors="replace").rstrip("\x00")
    return raw.decode("utf-8", errors="replace").rstrip("\x00")

class ClipboardMixin:
    """Mixed into OutlineEditor (outline.py); uses its state."""

    # -- clipboard -----------------------------------------------------------------------

    def _set_clipboard(self, pairs):
        provider = Gdk.ContentProvider.new_union(
            [Gdk.ContentProvider.new_for_bytes(mime, _bytes(data)) for mime, data in pairs])
        self.get_clipboard().set_content(provider)

    def copy_items(self, cut=False):
        """Copy (or cut) the selected items, and only those; with none selected, the current
        item with everything under it."""
        nodes = list(self.sel) or (list(self.current.walk()) if self.current else [])
        if not nodes:
            return
        ids = {n.id for n in nodes}
        lines = layout(self.doc.root, self.rules)
        keep = []
        for i, ln in enumerate(lines):
            if ln.node is not None:
                if ln.node.id in ids:
                    keep.append(ln)
                continue
            before = next((l.node for l in reversed(lines[:i]) if l.node is not None), None)
            after = next((l.node for l in lines[i + 1:] if l.node is not None), None)
            if before is not None and after is not None and before.id in ids and after.id in ids:
                keep.append(ln)
        data = json.dumps({"nodes": selected_json(nodes)}, ensure_ascii=False)
        self._set_clipboard([(NODES_MIME, data), *export_formats(keep, self.rules)])
        if cut:
            self.delete_items(nodes)
        self.emit("message", f"{'Cut' if cut else 'Copied'} {len(ids)} item{'s' if len(ids) != 1 else ''}")

    def copy_text(self, view, cut=False):
        sel = view.get_buffer().get_selection_bounds()
        if not sel:
            return False
        runs = view.get_runs(*sel)
        self._set_clipboard([(RUNS_MIME, json.dumps(runs_to_json(runs), ensure_ascii=False)),
                             ("text/html", f'<meta charset="utf-8"><p>{runs_html(runs)}</p>'),
                             *[(m, runs_text(runs)) for m in TEXT_MIMES]])
        if cut:
            with self._op():
                view.get_buffer().delete_selection(True, True)
        return True

    def _paste_plain_cmd(self):
        row = self.rows.get(self.current.id) if self.current else None
        if isinstance(row, TextRow):
            self.paste(row, row.view, plain=True)

    def paste(self, row, view, plain=False):
        if not isinstance(row, TextRow):
            return
        self.clear_selection()
        cb = self.get_clipboard()
        formats = cb.get_formats()
        order = TEXT_MIMES if plain else [NODES_MIME, RUNS_MIME, *EDITOR_MIMES, "text/html"] + TEXT_MIMES
        ctx = (row.node.id, view.cursor_offset(), view.selection_offsets())
        self._read_clip(cb, [m for m in order if formats.contain_mime_type(m)], ctx, plain)

    def _read_clip(self, cb, mimes, ctx, plain):
        """Read the first of `mimes` (the clipboard's formats, best first) and paste it."""
        if not mimes:
            cb.read_text_async(None, self._on_clip_text, (ctx, plain))
            return
        cb.read_async(mimes[:1], GLib.PRIORITY_DEFAULT, None, self._on_clip_stream, (ctx, plain, mimes))

    def _without_editor_json(self, cb, mimes, ctx, plain):
        """Go on to the HTML and text after a copy from TopCoding's editor that holds no
        drawing, or can't be read."""
        self._read_clip(cb, [m for m in mimes if m not in EDITOR_MIMES], ctx, plain)

    def _on_clip_text(self, cb, res, data):
        ctx, plain = data
        try:
            text = cb.read_text_finish(res)
        except GLib.Error:
            return
        if text:
            self._pasted(ctx, "text/plain", text, plain)

    def _on_clip_stream(self, cb, res, data):
        ctx, plain, mimes = data
        try:
            stream, _mime = cb.read_finish(res)
        except GLib.Error as e:
            if mimes[0] in EDITOR_MIMES:
                self._without_editor_json(cb, mimes, ctx, plain)
            else:
                self.emit("message", f"Paste failed: {e.message}")
            return
        out = Gio.MemoryOutputStream.new_resizable()
        out.splice_async(stream, Gio.OutputStreamSpliceFlags.CLOSE_SOURCE | Gio.OutputStreamSpliceFlags.CLOSE_TARGET,
                         GLib.PRIORITY_DEFAULT, None, self._on_clip_data, (cb, ctx, plain, mimes))

    def _on_clip_data(self, out, res, data):
        cb, ctx, plain, mimes = data
        mime = mimes[0]
        try:
            out.splice_finish(res)
        except GLib.Error as e:
            if mime in EDITOR_MIMES:
                self._without_editor_json(cb, mimes, ctx, plain)
            else:
                self.emit("message", f"Paste failed: {e.message}")
            return
        raw = out.steal_as_bytes().get_data() or b""
        if mime in EDITOR_MIMES:
            items = lexical.pasted_items(mime, raw)
            if items is None:
                self._without_editor_json(cb, mimes, ctx, plain)
            else:
                self._pasted(ctx, mime, None, plain, items)
            return
        self._pasted(ctx, mime, _decode(raw), plain)

    def _pasted(self, ctx, mime, text, plain, items=None):
        """Paste clipboard content of type `mime`: its text, or for a copy from
        TopCoding's editor, the items read from it."""
        fid, off, selo = ctx
        row = self.rows.get(fid)
        if not isinstance(row, TextRow):
            return
        node, v = row.node, row.view
        v.grab_focus()
        if selo:
            v.select_range(*selo)
        else:
            v.set_cursor(off)
        if mime == NODES_MIME:
            nodes = [fresh_ids(Node.from_json(d)) for d in json.loads(text).get("nodes", [])]
            self.insert_forest(node, nodes)
            return
        if mime == RUNS_MIME:
            with self._op():
                v.insert_runs(runs_from_json(json.loads(text)))
            return
        if items is None:
            items = html_items(text) if mime == "text/html" else text_items(text)
        lines = [it[1] for it in items if it[0] == "line"]
        while lines and not runs_text(lines[-1]).strip():
            lines.pop()
        while lines and not runs_text(lines[0]).strip():
            lines.pop(0)
        if plain:
            with self._op():
                v.insert_runs([Run(runs_text(join_lines(lines)))])
            return
        has_block = any(it[0] in ("table", "drawing") for it in items)
        if len(lines) <= 1 and not has_block:
            with self._op():
                v.insert_runs(lines[0] if lines else [])
            return
        forest = parse(items, self.rules)
        if forest is None:
            # plain paragraphs: keep them together in this item (formatting kept); a table
            # or drawing copied on its own or with such text goes after the item
            with self._op():
                if lines:
                    v.insert_runs(join_lines(lines))
                self._insert_blocks(node, block_nodes(items))
            paras, cur = [], []
            for l in lines + [[]]:
                if runs_text(l).strip():
                    cur.append(l)
                elif cur:
                    paras.append(join_lines(cur))
                    cur = []
            if len(paras) > 1:
                self.emit("toast", f"Pasted {len(paras)} paragraphs into one item", "One Item per Paragraph",
                          lambda: self._resplit(ctx, paras, block_nodes(items)))
            return
        count = sum(1 for top in forest for _ in top.walk())
        self.insert_forest(node, forest)
        plain_text = "\n".join(runs_text(l) for l in lines)
        self.emit("toast", f"Pasted {count} items as an outline", "Paste as Plain Text",
                  lambda: self._replace_with_plain(ctx, plain_text))

    def _resplit(self, ctx, lines, blocks=()):
        self.undo()
        row = self.rows.get(ctx[0])
        if isinstance(row, TextRow):
            row.view.set_cursor(ctx[1])
            self._paste_lines(row.node, row.view, lines, blocks)

    def _insert_blocks(self, node, blocks, focus=None):
        """Put pasted tables and drawings after node, where Ctrl+T and Ctrl+D put one.
        The cursor goes into the last table; when a drawing comes last (no cursor can be
        in one), to the end of `focus`, or it stays where it is. Call inside _op()."""
        after = node
        for blk in blocks:
            self._insert_leaf(after, blk)
            if node.kind != "heading":  # under a numbered item they line up by themselves
                after = blk
        if blocks and blocks[-1].kind == "table":
            self.refresh(focus=blocks[-1], offset=0)
        elif focus is not None:
            self.refresh(focus=focus, offset=-1)
        elif blocks:
            self.refresh()

    def _replace_with_plain(self, ctx, text):
        self.undo()
        self._pasted(ctx, "text/plain", text, True)

    def _paste_lines(self, node, v, lines, blocks=()):
        if not lines:
            return
        with self._op():
            v.insert_runs(lines[0])
            prev = node
            kind = node.kind if node.kind in ("heading", "bullet") else "bullet"
            for l in lines[1:]:
                new = Node(kind, runs=[Run(r.text.replace("\n", " "), r.bold, r.italic) for r in l],
                           marker=node.marker)
                prev.parent.insert(prev.index() + 1, new)
                prev = new
            self._insert_blocks(prev, blocks, focus=prev)

    def insert_forest(self, anchor, forest):
        if not forest:
            return
        root = self.doc.root
        with self._op():
            replace = anchor.kind in ("heading", "bullet") and not anchor.text and not anchor.children
            h = enclosing_heading(anchor)
            if replace:
                par, idx = anchor.parent, anchor.index()
                anchor.detach()
                if can_contain(par, Node("heading")):
                    hpos = [par, idx]
                else:
                    hh = enclosing_heading(par)
                    hpos = [hh.parent, hh.index() + 1] if hh else [root, len(root.children)]
                lpos = [par, idx]
            else:
                if h is not None:
                    hpos = [h.parent, h.index() + 1]
                else:
                    top = anchor
                    while top.parent is not root:
                        top = top.parent
                    hpos = [root, top.index() + 1]
                lpos = [anchor, leaf_insert_index(anchor)] if anchor.kind == "heading" \
                    else [anchor.parent, anchor.index() + 1]
            last = None
            for n in forest:
                pos, other = (hpos, lpos) if n.kind == "heading" else (lpos, hpos)
                p, i = pos
                if not can_contain(p, n):
                    p, i = root, len(root.children)
                    pos[:] = [p, i]
                p.insert(i, n)
                pos[1] += 1
                if other[0] is p and other[1] >= i:
                    other[1] += 1
                last = n
            self._ensure_nonempty()
            tail = list(last.walk())[-1]
            self.refresh(focus=tail, offset=-1)
