"""OutlineEditor, part: undo and redo: whole-chapter snapshots. Every change goes through _op() or _commit()."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager

from ..model import Node, display_order, is_text
from .rows import TableRow, TextRow, row_type
COALESCE = 1.5     # seconds: typing in one item within this gap is one undo step

class UndoMixin:
    """Mixed into OutlineEditor (outline.py); uses its state."""

    # -- history ---------------------------------------------------------------------

    def _snapshot(self):
        content = json.dumps([c.to_json() for c in self.doc.root.children], ensure_ascii=False)
        if self._focus_hint:
            fid, off = self._focus_hint
        elif self.current is not None:
            fid = self.current.id
            row = self.rows.get(fid)
            off = row.cursor_offset() if row else None
        else:
            fid = off = None
        return content, fid, off

    def _commit(self, group=None):
        if self._suspend or self.doc is None:
            return
        snap = self._snapshot()
        if self._cur and snap[0] == self._cur[0]:
            self._cur = snap
            return
        now = time.monotonic()
        if not (group is not None and group == self._last_group and now - self._last_time < COALESCE):
            if self._cur:
                self._undo.append(self._cur)
                del self._undo[:-500]
        self._redo.clear()
        self._cur = snap
        if group is None or group[0] != "t":
            self._tg = None
        self._last_group = group
        self._last_time = now
        self.emit("changed")

    @contextmanager
    def _op(self, group=None):
        self._suspend += 1
        try:
            yield
        finally:
            self._suspend -= 1
            if self._suspend == 0:
                self._commit(group)

    def replace_content(self, root):
        """Replace the whole chapter (e.g. with an earlier version) as one undoable step."""
        self._undo.append(self._cur)
        self._redo.clear()
        content = json.dumps([c.to_json() for c in root.children], ensure_ascii=False)
        first = next((n for n in display_order(root) if is_text(n)), None)
        self._restore((content, first.id if first else None, -1))

    def undo(self):
        if not self._undo:
            self.emit("message", "Nothing to undo")
            return
        self._redo.append(self._cur)
        self._restore(self._undo.pop())

    def redo(self):
        if not self._redo:
            self.emit("message", "Nothing to redo")
            return
        self._undo.append(self._cur)
        self._restore(self._redo.pop())

    def _restore(self, snap):
        content, fid, off = snap
        self._cur = snap
        self._last_group = None
        self._tg = None
        self.doc.root = Node("root", children=[Node.from_json(c) for c in json.loads(content)])
        self._ensure_nonempty()
        self.mc_views = []
        # keep the existing row widgets (same node ids); only reload what changed
        old_rows, self.rows = self.rows, {}
        for n in self.doc.root.walk():
            r = old_rows.get(n.id)
            if r is None or type(r) is not row_type(n.kind):
                continue
            same = (r.node.runs == n.runs) if isinstance(r, TextRow) else (r.node.data == n.data)
            r.node = n
            if not same:
                if isinstance(r, TextRow):
                    r.reload()
                elif isinstance(r, TableRow):
                    r.header_btn.set_active(bool(n.data.get("header")))
                    r.build()
            self.rows[n.id] = r
        self.sel = []
        self.current = self.cur_view = None
        target = next((n for n in self.doc.root.walk() if n.id == fid), None) \
            or next(n for n in display_order(self.doc.root))
        self.refresh(focus=target, offset=-1 if off is None else off)
        self.emit("changed")

    def mark_changed(self, node, structural=False):
        if structural:
            self._commit(None)
        else:
            self._commit(self._text_group(node, self.cur_view))

    def _text_group(self, node, view):
        """Undo granularity for typing: one step per word (plus the spaces after it).
        A new step also starts when switching between typing and deleting, when the
        cursor jumps, or after a paste."""
        le = getattr(view, "last_edit", None) or ("?", "", -1)
        kind, text, off = le
        word = kind == "ins" and len(text) == 1 and (text.isalnum() or text in "'’_")
        end = off + len(text) if kind == "ins" else off
        prev = self._tg
        new = (prev is None or prev["node"] != node.id or prev["kind"] != kind
               or kind not in ("ins", "del")
               or (kind == "ins" and (len(text) != 1 or (word and not prev["word"])))
               or abs(off - prev["end"]) > 1)
        if new:
            self._tg_n += 1
        self._tg = {"node": node.id, "kind": kind, "word": word, "end": end}
        return ("t", node.id, self._tg_n)
