"""OutlineEditor, part: item types, and adding and deleting items, tables and drawings."""
from __future__ import annotations

from .. import drawing
from ..model import (Node, enclosing_heading, is_text, leaf_insert_index, new_table_data, remove_items,
                     remove_promote, set_kind)
from . import drawing_web


class ItemsMixin:
    """Mixed into OutlineEditor (outline.py); uses its state."""

    def kind_options(self):
        opts = [("heading", None, "Numbered Item", self.rules["heading"]["trigger"])]
        for name, m in self.rules["markers"].items():
            opts.append(("bullet", name, f"{m['symbol']}   {m.get('label', name)}", m.get("trigger", "")))
        return opts

    def change_kind(self, node, kind, marker):
        err = set_kind(node, kind, marker)
        if err:
            self.emit("message", err)
            return False
        with self._op():
            self.refresh(focus=node)
        return True

    def cycle_kind(self, node):
        opts = self.kind_options()
        cur = next((i for i, (k, m, *_) in enumerate(opts)
                    if k == node.kind and (k != "bullet" or m == node.marker)), -1)
        for step in range(1, len(opts)):
            k, m, *_ = opts[(cur + step) % len(opts)]
            if set_kind(node, k, m) is None:
                with self._op():
                    self.refresh(focus=node)
                return

    def _set_kind_cmd(self, target):
        node = self._menu_node or self.current
        if node is None or not is_text(node):
            return
        kind, _, marker = target.partition(":")
        self.change_kind(node, kind, marker or None)

    def _insert_leaf(self, node, new):
        if node.kind == "heading":
            node.insert(leaf_insert_index(node), new)
        else:
            node.parent.insert(node.index() + 1, new)

    def add_component(self, node, what):
        """what: next | child | parent | bullet:<marker> | table | drawing"""
        if node is None or self.doc is None:
            return
        if what == "drawing":
            self.insert_drawing(node)
            return
        root = self.doc.root
        h = enclosing_heading(node)
        with self._op():
            if what == "parent" and (h is None or h.parent.kind != "heading"):
                what = "next"
            if what == "next":
                new = Node("heading")
                if h is not None:
                    h.parent.insert(h.index() + 1, new)
                else:
                    top = node
                    while top.parent is not root:
                        top = top.parent
                    root.insert(top.index() + 1, new)
            elif what == "child":
                new = Node("heading")
                (h or root).append(new)
            elif what == "parent":
                p = h.parent
                new = Node("heading")
                p.parent.insert(p.index() + 1, new)
            elif what.startswith("bullet:"):
                new = Node("bullet", marker=what.split(":", 1)[1])
                self._insert_leaf(node, new)
            elif what == "table":
                new = Node("table", data=new_table_data(2, 2))
                self._insert_leaf(node, new)
            else:
                return
            self.refresh(focus=new, offset=0)

    def insert_table(self, node=None):
        self.add_component(node or self.current, "table")

    # -- drawings ---------------------------------------------------------------------

    def _node_by_id(self, nid):
        return next((n for n in self.doc.root.walk() if n.id == nid), None) if self.doc else None

    def _open_drawing(self, data, done):
        if drawing_web.edit(self.get_root(), data, done) is None:
            self.emit("message", drawing_web.MISSING)

    def insert_drawing(self, node=None):
        """Open the drawing window on an empty drawing; it becomes a block after `node`
        (where a table would go) once the user keeps it with something in it."""
        node = node or self.current
        if node is None or self.doc is None:
            return
        anchor = node.id

        def done(data):
            target = self._node_by_id(anchor) or self.current
            if target is None or drawing.is_empty(data):
                return
            with self._op():
                self._insert_leaf(target, Node("drawing", data=data))
                self.refresh()

        self._open_drawing(drawing.new_data(), done)

    def copy_drawing(self, node):
        """Copy one drawing by itself: it is selected, as a click on it would, and copied."""
        if node is None or node.kind != "drawing":
            return
        self.set_selection([node])
        self.copy_items()

    def edit_drawing(self, node):
        if node is None or node.kind != "drawing":
            return
        nid = node.id

        def done(data):
            n = self._node_by_id(nid)
            if n is None or drawing.scene(data) == drawing.scene(n.data):
                return
            if drawing.is_empty(data):  # everything erased: no block left to show
                self.delete_items([n])
                return
            with self._op():
                n.data = {**n.data, **drawing.scene(data)}
                row = self.rows.get(n.id)
                if row is not None:
                    row.reload()

        self._open_drawing(node.data, done)

    def delete_node(self, node):
        """Delete one item; its sub-items move up into its place."""
        if node is None:
            return
        with self._op():
            target = self._prev_text_node(node)
            remove_promote(node)
            self._ensure_nonempty()
            self.refresh(focus=target or self._order()[0], offset=-1)

    def delete_items(self, nodes):
        """Delete these items and nothing else: sub-items that aren't among them move up into
        their place, as with Delete Item (model.remove_items)."""
        order = self._order()
        pos = {id(n): i for i, n in enumerate(order)}
        nodes = [n for n in nodes if id(n) in pos]
        if not nodes:
            return
        first = min(pos[id(n)] for n in nodes)
        with self._op():
            remove_items(nodes)
            self._ensure_nonempty()
            self.sel = []
            order = self._order()
            target = next((n for n in reversed(order[:max(first, 1)]) if is_text(n)), None) \
                or next((n for n in order if is_text(n)), order[0])
            self.refresh(focus=target, offset=-1)
