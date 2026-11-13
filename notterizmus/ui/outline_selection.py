"""OutlineEditor, part: item selection (Ctrl+A, Ctrl+W / Ctrl+Shift+W, Shift+arrows)
and formatting several items at once."""
from __future__ import annotations

from ..model import indent, normalize_runs, outdent
from .rows import TableRow, TextRow


def _top_level(nodes):
    ids = {n.id for n in nodes}
    out = []
    for n in nodes:
        p = n.parent
        while p is not None and p.id not in ids:
            p = p.parent
        if p is None:
            out.append(n)
    return out

class SelectionMixin:
    """Mixed into OutlineEditor (outline.py); uses its state."""

    # -- item selection (Ctrl+A, Ctrl+W, Shift+Up/Down) -------------------------------------

    def _sel_ids(self):
        return {n.id for top in self.sel for n in top.walk()}

    def _apply_sel_css(self):
        ids = self._sel_ids()
        for nid, row in self.rows.items():
            (row.add_css_class if nid in ids else row.remove_css_class)("node-selected")

    def set_selection(self, nodes):
        self.sel = _top_level(list(nodes))
        if self.sel and self.cur_view is not None:
            self.cur_view.set_cursor(self.cur_view.cursor_offset())  # drop the text selection
        self._apply_sel_css()

    def clear_selection(self):
        if self.sel:
            self.sel = []
            self.sel_anchor = self.sel_head = None
            self._apply_sel_css()

    def select_all(self):
        order = self._order()
        self.sel_anchor, self.sel_head = order[0], order[-1]
        self.set_selection(self.doc.root.children)

    def extend_selection(self, delta):
        order = self._order()
        if self.sel_anchor not in order or self.sel_head not in order:
            self.sel_anchor = self.sel_head = self.current
        i = max(0, min(len(order) - 1, order.index(self.sel_head) + delta))
        self.sel_head = order[i]
        a, b = sorted((order.index(self.sel_anchor), i))
        self.set_selection(order[a:b + 1])

    def _sel_state(self):
        if self.sel:
            return ("nodes", list(self.sel))
        v = self.cur_view
        if v is None:
            return ("none",)
        return ("text", v, v.selection_offsets() or v.cursor_offset())

    def expand_selection(self):
        node, v = self.current, self.cur_view
        if node is None:
            return
        state = self._sel_state()
        if self.sel:
            parent = self.sel[0].parent
            if parent is None or parent.kind == "root":
                if set(map(id, self.sel)) == set(map(id, self.doc.root.children)):
                    return
                new = list(self.doc.root.children)
            else:
                new = [parent]
        else:
            row = self.rows.get(node.id)
            if isinstance(row, TextRow) and v is row.view:
                text = v.get_plain()
                so = v.selection_offsets()
                if so is None:
                    wb = v.word_bounds(v.cursor_iter())
                    if wb and wb != (0, len(text)):
                        self._wstack.append(state)
                        v.select_range(*wb)
                        return
                if text and so != (0, len(text)):
                    self._wstack.append(state)
                    v.select_range(0, len(text))
                    return
            new = [node]
        self._wstack.append(state)
        self.set_selection(new)

    def shrink_selection(self):
        if not self._wstack:
            return
        st = self._wstack.pop()
        if st[0] == "nodes":
            self.set_selection(st[1])
            return
        self.clear_selection()
        if st[0] == "text":
            v, where = st[1], st[2]
            if isinstance(where, tuple):
                v.select_range(*where)
            else:
                v.set_cursor(where)

    def _sel_key(self, name, ctrl, shift, alt):
        if ctrl and name in ("c", "C"):
            self.copy_items()
            return True
        if ctrl and name in ("x", "X"):
            self.copy_items(cut=True)
            return True
        if name in ("Delete", "BackSpace"):
            self.delete_items(self.sel)
            return True
        if ctrl and name in ("b", "B", "i", "I"):
            self.format_items("bold" if name.lower() == "b" else "italic")
            return True
        if name in ("Tab", "ISO_Left_Tab"):
            nodes = list(self.sel)
            with self._op():
                for n in (nodes if name == "Tab" else reversed(nodes)):
                    (indent if name == "Tab" else outdent)(n)
                self.refresh()
            return True
        if ctrl and name == "w":
            self.expand_selection()
            return True
        if ctrl and name == "W":
            self.shrink_selection()
            return True
        if ctrl and name in ("a", "A"):
            self.select_all()
            return True
        if shift and name in ("Up", "Down"):
            self.extend_selection(-1 if name == "Up" else 1)
            return True
        if name == "Escape":
            self.clear_selection()
            return True
        self.clear_selection()
        self._wstack = []
        return None

    def format_items(self, attr):
        nodes = [n for top in self.sel for n in top.walk()]
        runs = [r for n in nodes for r in n.runs]
        runs += [r for n in nodes if n.kind == "table" for row in n.data.get("rows", [])
                 for cell in row for r in cell]
        if not runs:
            return
        on = not all(getattr(r, attr) for r in runs)
        with self._op():
            for r in runs:
                setattr(r, attr, on)
            for n in nodes:
                row = self.rows.get(n.id)
                if isinstance(row, TextRow):
                    n.runs = normalize_runs(n.runs)
                    row.reload()
                elif isinstance(row, TableRow):
                    row.build()
