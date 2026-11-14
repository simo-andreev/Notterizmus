"""OutlineEditor, part: item selection (Ctrl+A, Ctrl+W / Ctrl+Shift+W, Shift+arrows,
dragging across items) and formatting several items at once."""
from __future__ import annotations

from dataclasses import dataclass

from gi.repository import Gdk, Graphene, Gtk

from ..model import indent, normalize_runs, outdent
from .rows import TableRow, TextRow

DRAG_EDGE = 30        # px from the top or bottom of the outline where a drag scrolls it
DRAG_MAX_SPEED = 2400  # px per second, with the pointer far past the edge


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


def _offset_at(view, x, y):
    """Character offset in view nearest to (x, y), a point in the view (may be outside it)."""
    y = max(0, min(y, view.get_height() - 1))
    bx, by = view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
    _over_text, it = view.get_iter_at_location(bx, by)
    return it.get_offset()


@dataclass
class _Drag:
    row: object          # the row where the left button went down
    view: object         # its text view under the pointer
    offset: int          # where in that text
    items: bool = False  # selecting items (the pointer has been over another row)
    point: tuple = (0, 0)  # the pointer, in the outline's own coordinates
    time: int = 0        # frame time of the last autoscroll step


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
        if self.sel and self.cur_view is not None and self.cur_view.has_selection():
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

    # -- selecting items by dragging across them ---------------------------------------------
    # A left-button drag begins as GtkTextView's own text selection in the row where it was
    # pressed. Once the pointer is over another row, it selects whole items instead, from
    # that row to the row under the pointer (like Shift+click); back over the first row it
    # selects text again. GtkTextView's gestures claim the pointer, and a claim denies the
    # gestures of the widgets around it, so the outline follows the drag with a motion
    # controller and a legacy one (for the release), which a claim can't stop.

    def _setup_drag_select(self):
        self._drag = None
        self._drag_tick = None
        motion = Gtk.EventControllerMotion(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        motion.connect("motion", self._drag_motion)
        self.add_controller(motion)
        release = Gtk.EventControllerLegacy(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        release.connect("event", self._drag_event)
        self.add_controller(release)

    def start_drag_select(self, row, view, x, y):
        """The left button went down at (x, y) in view, a text view of row."""
        offset = _offset_at(view, x, y)
        sel = view.get_buffer().get_selection_bounds()
        if sel and sel[0].get_offset() <= offset < sel[1].get_offset():
            self._drag = None  # pressed in selected text: GtkTextView drags that text
        else:
            self._drag = _Drag(row, view, offset)

    def _drag_motion(self, ctl, x, y):
        d = self._drag
        if d is None:
            return
        if not ctl.get_current_event_state() & Gdk.ModifierType.BUTTON1_MASK:
            self._end_drag()  # released where the outline didn't see it
            return
        d.point = (x, y)
        self._drag_to(x, y)
        if d.items and self._drag_tick is None and self._edge_speed(y):
            d.time = 0
            self._drag_tick = self.add_tick_callback(self._drag_scroll)

    def _drag_event(self, ctl, _event):
        if self._drag is not None:
            event = ctl.get_current_event()  # PyGObject passes the signal's own event as None
            if event is not None and event.get_event_type() == Gdk.EventType.BUTTON_RELEASE:
                self._end_drag()
        return False

    def _end_drag(self):
        self._drag = None
        if self._drag_tick is not None:
            self.remove_tick_callback(self._drag_tick)
            self._drag_tick = None

    def _drag_to(self, x, y):
        """Select for the pointer at (x, y) in the outline."""
        d = self._drag
        ok, p = self.compute_point(self.box, Graphene.Point().init(x, y))
        target = self._row_at(p.y) if ok else None
        if target is None:
            return
        if target is d.row:
            if d.items:  # back over the row where the drag began: select text again
                self.clear_selection()
                ok, q = self.compute_point(d.view, Graphene.Point().init(x, y))
                if ok:
                    d.view.select_range(d.offset, _offset_at(d.view, q.x, q.y))
            return
        if not d.items:
            d.items = True
            # Take the rest of the drag from GtkTextView, which could otherwise go on
            # extending its text selection (and scrolling to it) as the pointer moves.
            ctrls = d.view.observe_controllers()
            for i in range(ctrls.get_n_items()):
                c = ctrls.get_item(i)
                if isinstance(c, Gtk.GestureDrag):
                    c.set_state(Gtk.EventSequenceState.DENIED)
        order = self._order()
        if d.row.node not in order or target.node not in order:
            return  # the chapter was rebuilt under the drag
        self.sel_anchor, self.sel_head = d.row.node, target.node
        a, b = sorted((order.index(d.row.node), order.index(target.node)))
        self.set_selection(order[a:b + 1])

    def _row_at(self, y):
        """The row at height y in the outline's box: the last one that starts at or above
        y (the first row when y is above them all)."""
        best = None
        for node in self._order():
            row = self.rows.get(node.id)
            if row is None or row.get_parent() is not self.box or not row.get_visible():
                continue
            ok, p = row.compute_point(self.box, Graphene.Point().init(0, 0))
            if not ok:
                continue
            if best is not None and p.y > y:
                break
            best = row
        return best

    def _edge_speed(self, y):
        """Autoscroll speed (px per second, negative upwards) for the pointer at height y in
        the outline: none away from the edges, faster the further it goes past one."""
        h = self.get_height()
        if y < DRAG_EDGE:
            over = y - DRAG_EDGE
        elif y > h - DRAG_EDGE:
            over = y - (h - DRAG_EDGE)
        else:
            return 0
        speed = min(DRAG_MAX_SPEED, max(60, abs(over) * 20))
        return speed if over > 0 else -speed

    def _drag_scroll(self, _widget, clock):
        d = self._drag
        speed = self._edge_speed(d.point[1]) if d is not None and d.items else 0
        if not speed:
            self._drag_tick = None
            return False
        now = clock.get_frame_time()
        if d.time:
            adj = self.get_vadjustment()
            step = speed * min(now - d.time, 100_000) / 1e6
            adj.set_value(max(0.0, min(adj.get_value() + step, adj.get_upper() - adj.get_page_size())))
            self._drag_to(*d.point)
        d.time = now
        return True

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
