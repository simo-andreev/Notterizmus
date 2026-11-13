"""OutlineEditor, part: item types, and adding and deleting items and tables."""
from __future__ import annotations

from ..model import (Node, enclosing_heading, is_text, leaf_insert_index, new_table_data, remove_promote,
                     set_kind)
from .outline_selection import _top_level


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
        """what: next | child | parent | bullet:<marker> | table"""
        if node is None or self.doc is None:
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
        """Delete items with everything under them."""
        nodes = _top_level(list(nodes))
        if not nodes:
            return
        order = self._order()
        first = min(order.index(n) for n in nodes)
        with self._op():
            for n in nodes:
                if n.parent is not None:
                    n.detach()
            self._ensure_nonempty()
            self.sel = []
            order = self._order()
            target = next((n for n in reversed(order[:max(first, 1)]) if is_text(n)), None) \
                or next((n for n in order if is_text(n)), order[0])
            self.refresh(focus=target, offset=-1)
