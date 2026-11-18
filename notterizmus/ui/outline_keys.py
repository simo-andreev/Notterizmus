"""OutlineEditor, part: keys in the outline: Enter, Backspace, Delete, Tab, arrows and the rest of on_key."""
from __future__ import annotations

import time

from gi.repository import Gdk

from ..model import Node, editable_order, indent, is_text, move, normalize_runs, outdent, remove_promote
from .rows import TableRow, _mods
DOUBLE_CTRL = 0.4  # seconds between two Ctrl taps
MODIFIER_KEYS = {"Shift_L", "Shift_R", "Alt_L", "Alt_R", "Super_L", "Super_R", "Meta_L", "Meta_R",
                 "ISO_Level3_Shift", "Caps_Lock"}

class KeysMixin:
    """Mixed into OutlineEditor (outline.py); uses its state."""

    # -- keyboard ---------------------------------------------------------------------

    def on_key_released(self, keyval):
        if Gdk.keyval_name(keyval) in ("Control_L", "Control_R"):
            self._ctrl_armed = False

    def common_key(self, view, name, ctrl, shift, alt):
        """Keys that work everywhere, table cells included."""
        if ctrl and not alt and not shift and name in ("Page_Up", "Page_Down"):
            # previous/next chapter (also an app shortcut; this keeps GtkTextView from taking it)
            self.activate_action("win.prev-chapter" if name == "Page_Up" else "win.next-chapter", None)
            return True
        if ctrl and not alt:
            if name == "z":
                self.undo()
                return True
            if name in ("Z", "y", "Y"):
                self.redo()
                return True
        return False

    def on_key(self, row, view, keyval, state):
        name = Gdk.keyval_name(keyval)
        ctrl, shift, alt = _mods(state)
        if name in ("Control_L", "Control_R"):
            now = time.monotonic()
            if now - self._ctrl_time < DOUBLE_CTRL:
                self._ctrl_armed = True
            self._ctrl_time = now
            return False
        if name in MODIFIER_KEYS:
            return False
        self._ctrl_time = 0.0
        if self._ctrl_armed and ctrl and name in ("Up", "Down"):
            self.add_caret(view, -1 if name == "Up" else 1)
            return True
        if self.common_key(view, name, ctrl, shift, alt):
            return True
        if self.mc_views:
            handled = self._multi_key(view, keyval, name, ctrl, alt)
            if handled is not None:
                return handled
        if self.sel:
            handled = self._sel_key(name, ctrl, shift, alt)
            if handled is not None:
                return handled
        if name == "Escape" and self.on_escape is not None and self.on_escape():
            return True  # nothing of the editor's to cancel: e.g. close the find bar
        if not (ctrl and name in ("w", "W")):
            self._wstack = []

        v, node = view, row.node
        if ctrl and not alt:
            if name == "w":
                self.expand_selection()
                return True
            if name == "W":
                self.shrink_selection()
                return True
            if name in ("a", "A"):
                self.select_all()
                return True
            if name in ("b", "B"):
                v.toggle("bold")
                return True
            if name in ("i", "I"):
                v.toggle("italic")
                return True
            if name == "space":
                if shift:
                    self.cycle_kind(node)
                else:
                    self.show_assist(v)
                return True
            if name == "t":
                self.add_component(node, "table")
                return True
            if name == "d":
                self.insert_drawing(node)
                return True
            if name in ("Return", "KP_Enter"):
                self.add_component(node, "next")
                return True
            if name == "V":
                self.paste(row, v, plain=True)
                return True
            return False
        if alt and name in ("Insert", "KP_Insert"):
            self.show_add_menu(row, v)
            return True
        if alt and name in ("Up", "Down"):
            with self._op():
                if move(node, -1 if name == "Up" else 1):
                    self.refresh(focus=node, offset=v.cursor_offset())
            return True
        if name == "Menu" or (shift and name == "F10"):
            self._prepare_context(row, v, None)
            return False
        if name in ("Return", "KP_Enter"):
            if not shift:
                self.split(row)
            return True
        if name == "Tab":
            with self._op():
                if indent(node):
                    self.refresh(focus=node, offset=v.cursor_offset())
            return True
        if name == "ISO_Left_Tab":
            with self._op():
                if outdent(node):
                    self.refresh(focus=node, offset=v.cursor_offset())
            return True
        if name == "BackSpace" and not v.has_selection() and v.cursor_offset() == 0:
            return self.backspace(row)
        if name == "Delete" and not v.has_selection() and v.cursor_iter().is_end():
            return self.delete_forward(row)
        if name in ("Up", "Down"):
            edge = v.on_first_line() if name == "Up" else v.on_last_line()
            if shift and edge:
                if not self.sel:
                    self.sel_anchor = self.sel_head = node
                self.extend_selection(-1 if name == "Up" else 1)
                return True
            if edge and not shift:
                return self.focus_neighbor(node, -1 if name == "Up" else 1)
        return False

    def _order(self):
        return editable_order(self.doc.root)

    def focus_neighbor(self, node, delta, create=False):
        order = self._order()
        i = order.index(node) + delta
        while 0 <= i < len(order):
            target = order[i]
            row = self.rows.get(target.id)
            if isinstance(row, TableRow):
                row.focus_cell(0 if delta > 0 else len(row.rows) - 1, 0)
                return True
            if row and row.views():  # blocks from a newer version can't take the cursor
                row.focus(0 if delta > 0 else -1)
                return True
            i += delta
        if create and delta > 0:
            with self._op():
                new = Node("bullet", marker="dot") if node.parent.kind != "root" else Node("heading")
                node.parent.insert(node.index() + 1, new)
                self.refresh(focus=new, offset=0)
        return True

    # -- editing operations ---------------------------------------------------------------

    def split(self, row):
        v, node = row.view, row.node
        buf = v.get_buffer()
        with self._op():
            it = v.cursor_iter()
            if not node.text and not node.children:
                # Enter on an empty item: step out one level. A bullet directly under a
                # numbered item becomes that item's next sibling (Ⅰ.1.a + bullets -> Ⅰ.1.b).
                if node.kind == "bullet" and node.parent.kind == "heading":
                    parent = node.parent
                    node.detach()
                    node.kind = "heading"
                    parent.parent.insert(parent.index() + 1, node)
                    self.refresh(focus=node, offset=0)
                    return
                if node.parent.kind != "root" and outdent(node):
                    self.refresh(focus=node, offset=0)
                    return
            if it.get_offset() == 0 and node.text:
                new = Node(node.kind, marker=node.marker)
                node.parent.insert(node.index(), new)
                self.refresh(focus=node, offset=0)
                return
            at_end = it.is_end()
            after = v.get_runs(it, buf.get_end_iter())
            if not at_end:
                buf.delete(it, buf.get_end_iter())
            if at_end and node.children:
                fc = node.children[0]
                kind = fc.kind if fc.kind in ("heading", "bullet") else "bullet"
                new = Node(kind, marker=fc.marker if fc.kind == "bullet" else "dot")
                node.insert(0, new)
            else:
                new = Node(node.kind, runs=after, marker=node.marker)
                node.parent.insert(node.index() + 1, new)
            self.refresh(focus=new, offset=0)

    def _prev_text_node(self, node):
        order = self._order()
        for n in reversed(order[:order.index(node)]):
            if is_text(n):
                return n
        return None

    def backspace(self, row):
        node = row.node
        order = self._order()
        idx = order.index(node)
        prev = order[idx - 1] if idx > 0 else None
        if not node.text:
            target = self._prev_text_node(node)
            if target is None and len(order) == 1:
                return True
            with self._op():
                remove_promote(node)
                self._ensure_nonempty()
                self.refresh(focus=target or self._order()[0], offset=-1)
            return True
        if node.children or prev is None or not is_text(prev) or prev.id not in self.rows:
            return True
        with self._op():
            join = len(prev.text)
            prev.runs = normalize_runs(prev.runs + node.runs)
            self.rows[prev.id].reload()
            node.detach()
            self.refresh(focus=prev, offset=join)
        return True

    def delete_forward(self, row):
        node = row.node
        order = self._order()
        idx = order.index(node)
        nxt = order[idx + 1] if idx + 1 < len(order) else None
        if nxt is None or not is_text(nxt) or nxt.children or nxt.id not in self.rows:
            return True
        with self._op():
            join = len(node.text)
            node.runs = normalize_runs(node.runs + nxt.runs)
            row.reload()
            nxt.detach()
            self.refresh(focus=node, offset=join)
        return True
