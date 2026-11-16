"""The outline editor: renders the document as rows and handles structure, history,
selection, clipboard, menus and multi-cursor editing.

This module keeps the widget itself: building and refreshing rows, focus and scrolling.
The rest lives in mixins next to it, one theme each: outline_undo, outline_keys,
outline_items, outline_selection, outline_clipboard, outline_menus, outline_assist and
outline_carets. They share this object's state (rows, current, sel, doc, ...)."""
from __future__ import annotations

import time

from gi.repository import Adw, Gio, GLib, GObject, Graphene, Gtk

from ..completion import BookWords
from ..layout import layout
from ..model import Node, display_order, is_text, set_kind
from .rows import TextRow, _prefix_markup, row_type
from .outline_undo import UndoMixin
from .outline_keys import KeysMixin
from .outline_items import ItemsMixin
from .outline_selection import SelectionMixin
from .outline_clipboard import ClipboardMixin
from .outline_menus import MenusMixin
from .outline_assist import AssistMixin
from .outline_carets import CaretsMixin


class OutlineEditor(UndoMixin, KeysMixin, ItemsMixin, SelectionMixin, ClipboardMixin, MenusMixin,
                    AssistMixin, CaretsMixin, Gtk.ScrolledWindow):
    __gtype_name__ = "NtzOutlineEditor"
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "message": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        # message, button label, callback
        "toast": (GObject.SignalFlags.RUN_FIRST, None, (str, str, object)),
    }

    def __init__(self, rules):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.rules = rules
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.box.add_css_class("outline")
        self.set_child(Adw.Clamp(maximum_size=1200, tightening_threshold=900, child=self.box))
        # GTK only scrolls to a newly focused widget as a whole (and not at all for rows
        # that have no position yet); ensure_visible() follows the cursor instead.
        self.get_child().set_scroll_to_focus(False)
        self._ensure_view = None
        self._ensure_tick = None
        self._focus_pending = None
        self._focus_wait = None
        self._ensure_tries = 0
        self._click_time = 0.0
        self.rows = {}
        self._labels = []  # reusable spacer/blank line labels
        self._line_h = 0   # height of one text line, once known
        self.on_escape = None  # set by the window: Escape the editor itself doesn't use
        self.doc = None
        self.current = None
        self.cur_view = None
        self._menu_node = None
        # item selection
        self.sel = []
        self.sel_anchor = self.sel_head = None
        self._wstack = []
        self._setup_drag_select()
        # history
        self._undo, self._redo = [], []
        self._cur = None
        self._last_group = None
        self._last_time = 0.0
        self._suspend = 0
        self._focus_hint = None
        self._tg = None   # current typing group (see _text_group)
        self._tg_n = 0
        # multi-cursor
        self._ctrl_time = 0.0
        self._ctrl_armed = False
        self.mc_views = []
        self._ctx = None
        self._assist_pop = None
        self.spell_menu = None  # set by the window (language list)
        self._book_words = BookWords()
        self._setup_actions()

    # -- actions --------------------------------------------------------------------

    def _setup_actions(self):
        g = Gio.SimpleActionGroup()

        def add(name, cb, ptype=None, enabled=True):
            a = Gio.SimpleAction.new(name, GLib.VariantType.new(ptype) if ptype else None)
            a.connect("activate", lambda _a, p: cb(p.unpack() if p is not None else None))
            a.set_enabled(enabled)
            g.add_action(a)

        add("bold", lambda _: self._format_cmd("bold"))
        add("italic", lambda _: self._format_cmd("italic"))
        add("add", lambda w: self.add_component(self._menu_node or self.current, w), "s")
        add("delete-item", lambda _: self.delete_node(self._menu_node or self.current))
        add("select-scope", lambda _: self.expand_selection())
        add("select-all", lambda _: self.select_all())
        add("paste-plain", lambda _: self._paste_plain_cmd())
        add("undo", lambda _: self.undo())
        add("redo", lambda _: self.redo())
        add("copy-items", lambda _: self.copy_items())
        add("cut-items", lambda _: self.copy_items(cut=True))
        add("delete-items", lambda _: self.delete_items(self.sel))
        add("spell-replace", self._spell_replace, "s")
        add("spell-add", self._spell_add, "s")
        add("spell-ignore", self._spell_ignore, "s")
        add("drawing", lambda _: None, enabled=False)
        add("noop", lambda _: None, enabled=False)
        kind = Gio.SimpleAction.new_stateful("set-kind", GLib.VariantType.new("s"), GLib.Variant.new_string(""))
        kind.connect("activate", lambda a, p: self._set_kind_cmd(p.unpack()))
        g.add_action(kind)
        self.actions = g
        self.insert_action_group("ed", g)

    # -- loading / rendering ----------------------------------------------------

    def load(self, doc):
        self._end_drag()
        self.rows = {}
        self._labels = []
        self.doc = doc
        self.current = self.cur_view = None
        self.sel, self.mc_views = [], []
        self._ensure_nonempty()
        first = next((n for n in display_order(doc.root) if is_text(n)), None)
        self.refresh(focus=first, offset=-1)
        self._undo, self._redo = [], []
        self._cur = self._snapshot()
        self._last_group = None

    def set_rules(self, rules):
        self.rules = rules
        if self.doc:
            self.refresh()

    def _ensure_nonempty(self):
        if not self.doc.root.children:
            self.doc.root.append(Node("heading"))

    def _row(self, node):
        cls = row_type(node.kind)
        row = self.rows.get(node.id)
        if row is None or type(row) is not cls:
            row = cls(self, node)
            self.rows[node.id] = row
            self.size_new_views(row.views())
        return row

    def size_new_views(self, views):
        """A new text view first estimates its line height too small and corrects it a
        frame later, nudging everything below. Start it at one real line instead."""
        if not self._line_h:
            ref = next((v for v in self.all_views() if v.get_realized()), None)
            if ref is None:
                return
            h = ref.create_pango_layout("Ag").get_pixel_size()[1]
            self._line_h = h + ref.get_top_margin() + ref.get_bottom_margin()
        for v in views:
            v.set_size_request(v.get_size_request()[0], self._line_h)

    def all_views(self):
        for row in self.rows.values():
            yield from row.views()

    def text_size_changed(self):
        """After zooming: forget the one-line height measured for the old size, and drop it
        as the rows' minimum height (they're laid out already; rows added later measure
        it again). Not re-measured here: the new font only takes effect in the frame's
        layout phase, so measuring now would give the old size."""
        self._line_h = 0
        for v in self.all_views():
            v.set_size_request(v.get_size_request()[0], -1)
        self._requeue_views()

    def refresh(self, focus=None, offset=None):
        if focus is None and self.current is not None and self.current.id in self.rows:
            row = self.rows[self.current.id]
            if isinstance(row, TextRow):
                focus, offset = self.current, row.cursor_offset()
        self.clear_carets()
        # Build the wanted widget order, reusing row widgets and spacer labels, then
        # reorder the box in place: rows never leave the window, so they keep their
        # measured heights and nothing on screen jumps.
        live = set()
        wanted = []
        nlabels = 0
        for ln in layout(self.doc.root, self.rules):
            if ln.kind in ("item", "table", "unknown"):
                row = self._row(ln.node)
                row.set_prefix(ln.prefix)
                for k in ("heading", "bullet"):
                    (row.add_css_class if ln.node.kind == k else row.remove_css_class)(f"kind-{k}")
                live.add(ln.node.id)
                wanted.append(row)
            else:
                if nlabels < len(self._labels):
                    lbl = self._labels[nlabels]
                else:
                    lbl = Gtk.Label(xalign=0)
                    lbl.add_css_class("prefix")
                    lbl._markup = None
                    self._labels.append(lbl)
                nlabels += 1
                for k in ("spacer", "blank"):
                    (lbl.add_css_class if ln.kind == k else lbl.remove_css_class)(k)
                markup = _prefix_markup(ln.prefix) or " "
                if lbl._markup != markup:
                    lbl.set_markup(markup)
                    lbl._markup = markup
                wanted.append(lbl)
        del self._labels[nlabels:]
        wanted_ids = {id(w) for w in wanted}
        c = self.box.get_first_child()
        while c is not None:
            nxt = c.get_next_sibling()
            if id(c) not in wanted_ids:
                self.box.remove(c)
            c = nxt
        prev = None
        for w in wanted:
            if w.get_parent() is self.box:
                if w.get_prev_sibling() is not prev:
                    self.box.reorder_child_after(w, prev)
            else:
                self.box.insert_child_after(w, prev)
            prev = w
        for k in [k for k in self.rows if k not in live]:
            del self.rows[k]
        self.sel = [n for n in self.sel if n.id in live]
        self._apply_sel_css()
        # New text views measure their height before they know their width (so a long
        # line wraps as if very narrow) and GTK doesn't re-measure them by itself.
        GLib.timeout_add(20, self._requeue_views)
        if focus is not None:
            self.current = focus
            self._focus_hint = (focus.id, offset)
            GLib.idle_add(self._focus_node, focus, offset)

    def _requeue_views(self):
        for v in self.all_views():
            v.queue_resize()
        return False

    def _focus_node(self, node, offset):
        row = self.rows.get(node.id)
        if row:
            views = row.views()
            if views and views[0].get_width() <= 1 and self.get_root() is not None:
                # Not laid out yet. Placing the cursor now makes GTK lay the line out at
                # zero width (one letter per line); wait for the frame that sizes it.
                self._focus_pending = (node, offset)
                if self._focus_wait is None:
                    self._focus_wait = self.add_tick_callback(self._focus_when_sized)
                return False
            row.focus(0 if offset is None else offset)
            self.current = node
            # When the focus was in this row already (undo keeps the row and its focus),
            # no focus event follows to say which view has the cursor: say it here.
            focused = next((v for v in views if v.is_focus()), None)
            if focused is not None:
                self.cur_view = focused
        self._focus_hint = None
        return False

    def _focus_when_sized(self, _widget, _clock):
        node, offset = self._focus_pending
        row = self.rows.get(node.id)
        views = row.views() if row else []
        if views and views[0].get_width() <= 1:
            return True
        self._focus_wait = None
        self._focus_node(node, offset)
        return False

    # -- notifications from rows -------------------------------------------------

    def set_current(self, node, view=None):
        self.current = node
        self.cur_view = view
        if view is not None:
            self.ensure_visible(view)

    # -- keep the cursor on screen -------------------------------------------------------

    def track_cursor(self, view):
        """Scroll to the cursor whenever it moves or the text changes in a focused view."""
        buf = view.get_buffer()
        buf.connect_after("mark-set", lambda b, _it, m: m == b.get_insert() and view.has_focus()
                          and self.ensure_visible(view))
        buf.connect_after("changed", lambda b: view.has_focus() and self.ensure_visible(view))

    def ensure_visible(self, view):
        """Scroll so `view`'s cursor is on screen. Runs on the coming frames, once pending
        layout has given new rows their size and position."""
        self._ensure_view = view
        self._ensure_tries = 0
        if self._ensure_tick is None:
            self._ensure_tick = self.add_tick_callback(self._ensure_step)

    def _ensure_step(self, _widget, _clock):
        self._ensure_tries += 1
        v = self._ensure_view
        if v is None or self._scroll_to_cursor(v) or self._ensure_tries > 12:
            self._ensure_tick = None
            return False
        return True

    def _scroll_to_cursor(self, v):
        """True once the cursor is inside the visible area or can't be measured."""
        if v.get_root() is None or not v.get_mapped():
            return True
        if v.get_height() <= 0:
            return False  # not laid out yet
        content = self.get_child().get_child()
        loc = v.get_iter_location(v.cursor_iter())
        x, y = v.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, loc.x, loc.y)
        ok, pt = v.compute_point(content, Graphene.Point().init(x, y))
        if not ok:
            return False
        # Keep some context around the cursor, except right after a mouse click, so
        # clicking near the window edge doesn't shift the text under the pointer.
        clicked = time.monotonic() - self._click_time < 0.4
        margin = 0 if clicked else max(self._line_h, 20) * 1.5
        top, bottom = pt.y - margin, pt.y + loc.height + margin
        adj = self.get_vadjustment()
        value, page, upper = adj.get_value(), adj.get_page_size(), adj.get_upper()
        if top < value:
            adj.set_value(max(0.0, top))
        elif bottom > value + page:
            want = bottom - page
            adj.set_value(min(want, upper - page))
            if want > upper - page + 0.5:
                return False  # the content hasn't grown to its new size yet
        return True

    def on_text_changed(self, row):
        if not self._suspend:
            text = row.view.get_plain()
            for trig, (kind, marker) in self.rules.triggers().items():
                if text.startswith(trig + " ") and row.view.cursor_offset() == len(trig) + 1:
                    GLib.idle_add(self._apply_trigger, row, len(trig) + 1, kind, marker)
                    break
        self._commit(self._text_group(row.node, row.view))

    def _apply_trigger(self, row, nchars, kind, marker):
        with self._op():
            buf = row.view.get_buffer()
            buf.delete(buf.get_start_iter(), buf.get_iter_at_offset(nchars))
            err = set_kind(row.node, kind, marker)
            if err:
                self.emit("message", err)
            self.refresh(focus=row.node, offset=0)
        return False
