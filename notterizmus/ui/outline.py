"""The outline editor: renders the document as rows and handles structure, history,
selection, clipboard, menus and multi-cursor editing."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Graphene, Gtk

from ..completion import BookWords, complete, count_words, dictionary_words, node_texts
from ..export import runs_html, to_html, to_plain
from ..importer import html_items, join_lines, parse, text_items
from ..layout import layout
from ..model import (Node, Run, can_contain, display_order, enclosing_heading, fresh_ids,
                     heading_numbers, indent, is_text, leaf_insert_index, move, new_table_data,
                     normalize_runs, outdent, remove_promote, runs_from_json, runs_text,
                     runs_to_json, set_kind)
from ..spell import should_check
from .richtext import SPELL
from .rows import TableRow, TextRow, _mods, _prefix_markup, row_type

NODES_MIME = "application/x-notterizmus-nodes+json"
RUNS_MIME = "application/x-notterizmus-runs+json"
TEXT_MIMES = ["text/plain;charset=utf-8", "text/plain"]
DOUBLE_CTRL = 0.4  # seconds between two Ctrl taps
COALESCE = 1.5     # seconds: typing in one item within this gap is one undo step
MODIFIER_KEYS = {"Shift_L", "Shift_R", "Alt_L", "Alt_R", "Super_L", "Super_R", "Meta_L", "Meta_R",
                 "ISO_Level3_Shift", "Caps_Lock"}


def _bytes(s):
    return GLib.Bytes.new(s.encode("utf-8"))


def _decode(raw):
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(raw) > 1 and raw[1:2] == b"\x00"):
        return raw.decode("utf-16", errors="replace").rstrip("\x00")
    return raw.decode("utf-8", errors="replace").rstrip("\x00")


def _mi(label, action=None, target=None, accel=None):
    item = Gio.MenuItem.new(label, None)
    if action:
        if target is None:
            item.set_action_and_target_value(action, None)
        else:
            item.set_action_and_target_value(action, GLib.Variant.new_string(target))
    if accel:
        item.set_attribute_value("accel", GLib.Variant.new_string(accel))
    return item


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


def _digit(keyval):
    """Digit keys (top row or keypad) as menu numbers: 1–9 → 1–9, 0 → 10; else None."""
    name = Gdk.keyval_name(keyval) or ""
    if name.startswith("KP_"):
        name = name[3:]
    return (int(name) or 10) if len(name) == 1 and name.isdigit() else None


def _number_rows(lb):
    """Put 1–9, 0 in front of the first ten choices of a menu list; returns {number: row}.
    Greyed-out choices get a blank in the number column so the text stays aligned."""
    numbered = {}
    r = lb.get_first_child()
    while r is not None:
        if isinstance(r, Gtk.ListBoxRow) and getattr(r, "_choice", False):
            n = len(numbered) + 1
            on = r.get_sensitive() and n <= 10
            num = Gtk.Label(label=str(n % 10) if on else "", width_chars=1, css_classes=["menu-num"])
            child = r.get_child()
            r.set_child(None)
            child.set_hexpand(True)
            box = Gtk.Box(spacing=10)
            box.append(num)
            box.append(child)
            r.set_child(box)
            if on:
                numbered[n] = r
        r = r.get_next_sibling()
    return numbered


class OutlineEditor(Gtk.ScrolledWindow):
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
        self.doc = None
        self.current = None
        self.cur_view = None
        self._menu_node = None
        # item selection
        self.sel = []
        self.sel_anchor = self.sel_head = None
        self._wstack = []
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
        return display_order(self.doc.root)

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
        if node.children or prev is None or not is_text(prev):
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
        if nxt is None or not is_text(nxt) or nxt.children:
            return True
        with self._op():
            join = len(node.text)
            node.runs = normalize_runs(node.runs + nxt.runs)
            row.reload()
            nxt.detach()
            self.refresh(focus=node, offset=join)
        return True

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

    # -- clipboard -----------------------------------------------------------------------

    def _set_clipboard(self, pairs):
        provider = Gdk.ContentProvider.new_union(
            [Gdk.ContentProvider.new_for_bytes(mime, _bytes(data)) for mime, data in pairs])
        self.get_clipboard().set_content(provider)

    def copy_items(self, cut=False):
        nodes = _top_level(self.sel or ([self.current] if self.current else []))
        if not nodes:
            return
        ids = {n.id for top in nodes for n in top.walk()}
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
        data = json.dumps({"nodes": [n.to_json() for n in nodes]}, ensure_ascii=False)
        self._set_clipboard([(NODES_MIME, data),
                             ("text/html", to_html(keep, code_prefix=self.rules["export"]["code_prefix"])),
                             *[(m, to_plain(keep)) for m in TEXT_MIMES]])
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
        order = TEXT_MIMES if plain else [NODES_MIME, RUNS_MIME, "text/html"] + TEXT_MIMES
        mime = next((m for m in order if formats.contain_mime_type(m)), None)
        ctx = (row.node.id, view.cursor_offset(), view.selection_offsets())
        if mime is None:
            cb.read_text_async(None, self._on_clip_text, (ctx, plain))
            return
        cb.read_async([mime], GLib.PRIORITY_DEFAULT, None, self._on_clip_stream, (ctx, plain))

    def _on_clip_text(self, cb, res, data):
        ctx, plain = data
        try:
            text = cb.read_text_finish(res)
        except GLib.Error:
            return
        if text:
            self._pasted(ctx, "text/plain", text, plain)

    def _on_clip_stream(self, cb, res, data):
        ctx, plain = data
        try:
            stream, mime = cb.read_finish(res)
        except GLib.Error as e:
            self.emit("message", f"Paste failed: {e.message}")
            return
        out = Gio.MemoryOutputStream.new_resizable()
        out.splice_async(stream, Gio.OutputStreamSpliceFlags.CLOSE_SOURCE | Gio.OutputStreamSpliceFlags.CLOSE_TARGET,
                         GLib.PRIORITY_DEFAULT, None, self._on_clip_data, (ctx, plain, mime))

    def _on_clip_data(self, out, res, data):
        ctx, plain, mime = data
        try:
            out.splice_finish(res)
        except GLib.Error as e:
            self.emit("message", f"Paste failed: {e.message}")
            return
        self._pasted(ctx, mime, _decode(out.steal_as_bytes().get_data() or b""), plain)

    def _pasted(self, ctx, mime, text, plain):
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
        has_table = any(it[0] == "table" for it in items)
        if len(lines) <= 1 and not has_table:
            with self._op():
                v.insert_runs(lines[0] if lines else [])
            return
        forest = parse(items, self.rules)
        if forest is None:
            # plain paragraphs: keep them together in this item (formatting kept)
            with self._op():
                v.insert_runs(join_lines(lines))
            paras, cur = [], []
            for l in lines + [[]]:
                if runs_text(l).strip():
                    cur.append(l)
                elif cur:
                    paras.append(join_lines(cur))
                    cur = []
            if len(paras) > 1:
                self.emit("toast", f"Pasted {len(paras)} paragraphs into one item", "One Item per Paragraph",
                          lambda: self._resplit(ctx, paras))
            return
        count = sum(1 for top in forest for _ in top.walk())
        self.insert_forest(node, forest)
        plain_text = "\n".join(runs_text(l) for l in lines)
        self.emit("toast", f"Pasted {count} items as an outline", "Paste as Plain Text",
                  lambda: self._replace_with_plain(ctx, plain_text))

    def _resplit(self, ctx, lines):
        self.undo()
        row = self.rows.get(ctx[0])
        if isinstance(row, TextRow):
            row.view.set_cursor(ctx[1])
            self._paste_lines(row.node, row.view, lines)

    def _replace_with_plain(self, ctx, text):
        self.undo()
        self._pasted(ctx, "text/plain", text, True)

    def _paste_lines(self, node, v, lines):
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
            self.refresh(focus=prev, offset=-1)

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

    # -- menus -----------------------------------------------------------------------------

    def _kind_section(self, node):
        cur = "heading" if node.kind == "heading" else f"bullet:{node.marker}"
        self.actions.lookup_action("set-kind").set_state(GLib.Variant.new_string(cur))
        m = Gio.Menu()
        for kind, marker, label, trig in self.kind_options():
            m.append_item(_mi(f"{label}      {trig}␣" if trig else label, "ed.set-kind",
                              "heading" if kind == "heading" else f"bullet:{marker}"))
        return m

    def add_menu_model(self, node):
        h = enclosing_heading(node)
        label = self.rules.label
        m = Gio.Menu()
        s1 = Gio.Menu()
        if h is not None:
            nums = heading_numbers(h)
            s1.append_item(_mi(f"Next Item   {label(nums[:-1] + [nums[-1] + 1])}", "ed.add", "next",
                               "<Control>Return"))
            nchild = sum(1 for c in h.children if c.kind == "heading")
            s1.append_item(_mi(f"Sub-item   {label(nums + [nchild + 1])}", "ed.add", "child"))
            if h.parent.kind == "heading":
                pn = heading_numbers(h.parent)
                s1.append_item(_mi(f"Parent-level Item   {label(pn[:-1] + [pn[-1] + 1])}", "ed.add", "parent"))
        else:
            n = sum(1 for c in self.doc.root.children if c.kind == "heading")
            s1.append_item(_mi(f"Numbered Item   {label([n + 1])}", "ed.add", "next", "<Control>Return"))
        m.append_section(None, s1)
        s2 = Gio.Menu()
        for name, spec in self.rules["markers"].items():
            s2.append_item(_mi(f"{spec['symbol']}   {spec.get('label', name)}", "ed.add", f"bullet:{name}"))
        m.append_section(None, s2)
        s3 = Gio.Menu()
        s3.append_item(_mi("Table", "ed.add", "table", "<Control>t"))
        m.append_section(None, s3)
        return m

    def popup_menu(self, model, parent, rect=None):
        """Show a Gio.Menu as the app's numbered popup list (also used by the sidebar)."""
        self._popup(model, parent, rect)

    def _popup(self, model, parent, rect=None, node=None):
        """Show a Gio.Menu as a plain list popover. (GtkPopoverMenu mis-measures its
        height here and adds a scrollbar; a ListBox never scrolls.)"""
        pop = Gtk.Popover(has_arrow=False)
        pop.add_css_class("menu")
        pop.add_css_class("ntz-menu")
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, activate_on_single_click=True)
        first = []

        def stateful(menu):
            for i in range(menu.get_n_items()):
                sec = menu.get_item_link(i, "section")
                if sec is not None and stateful(sec):
                    return True
                a = menu.get_item_attribute_value(i, "action", GLib.VariantType.new("s"))
                ga = self.actions.lookup_action(a.unpack()[3:]) if a and a.unpack().startswith("ed.") else None
                if ga is not None and ga.get_state() is not None:
                    return True
            return False
        show_marks = stateful(model)

        def add_rows(menu):
            for i in range(menu.get_n_items()):
                sec = menu.get_item_link(i, "section")
                if sec is not None:
                    last = lb.get_last_child()
                    if last is not None and not (last.has_css_class("head") or last.has_css_class("sep")):
                        sep = Gtk.ListBoxRow(activatable=False, selectable=False, can_focus=False)
                        sep.set_child(Gtk.Separator())
                        sep.add_css_class("sep")
                        lb.append(sep)
                    head = menu.get_item_attribute_value(i, "label", GLib.VariantType.new("s"))
                    if head is not None:
                        hr = Gtk.ListBoxRow(activatable=False, selectable=False, can_focus=False)
                        hl = Gtk.Label(label=head.unpack(), xalign=0)
                        hl.add_css_class("heading")
                        hl.add_css_class("dim-label")
                        hr.set_child(hl)
                        hr.add_css_class("head")
                        lb.append(hr)
                    add_rows(sec)
                    continue
                label = menu.get_item_attribute_value(i, "label", GLib.VariantType.new("s"))
                action = menu.get_item_attribute_value(i, "action", GLib.VariantType.new("s"))
                target = menu.get_item_attribute_value(i, "target", None)
                accel = menu.get_item_attribute_value(i, "accel", GLib.VariantType.new("s"))
                act = action.unpack() if action else None
                ga = self.actions.lookup_action(act[3:]) if act and act.startswith("ed.") else None
                checked = bool(ga and ga.get_state() is not None and target is not None
                               and ga.get_state().equal(target))
                row = Gtk.ListBoxRow()
                box = Gtk.Box(spacing=10)
                if show_marks:
                    mark = Gtk.Image.new_from_icon_name("object-select-symbolic")
                    mark.set_opacity(1 if checked else 0)
                    box.append(mark)
                box.append(Gtk.Label(label=label.unpack() if label else "", xalign=0, hexpand=True))
                if accel:
                    ok, key, mods = Gtk.accelerator_parse(accel.unpack())
                    al = Gtk.Label(label=Gtk.accelerator_get_label(key, mods) if ok else "")
                    al.add_css_class("dim-label")
                    al.set_margin_start(24)
                    box.append(al)
                row.set_child(box)
                row.set_sensitive(ga is None or ga.get_enabled())
                row._act, row._target = act, target
                row._choice = True
                lb.append(row)
                if not first and row.get_sensitive():
                    first.append(row)

        add_rows(model)
        numbered = _number_rows(lb)

        def activated(_lb, row):
            pop.popdown()

            def run():
                self._menu_node = node
                if row._act:
                    parent.activate_action(row._act, row._target)
                self._menu_node = None
                return False
            GLib.idle_add(run)

        lb.connect("row-activated", activated)

        def on_key(_c, keyval, _kc, state):
            ctrl, _shift, alt = _mods(state)
            n = None if ctrl or alt else _digit(keyval)
            if n in numbered:
                activated(lb, numbered[n])
                return True
            return False

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", on_key)
        pop.add_controller(keys)
        pop.set_child(lb)
        pop.set_parent(parent)
        pos = Gtk.PositionType.BOTTOM
        if rect is not None:
            pop.set_pointing_to(rect)
            ok, pt = parent.compute_point(self, Graphene.Point().init(rect.x, rect.y))
            if ok and pt.y > self.get_height() * 0.5:
                pos = Gtk.PositionType.TOP
        pop.set_position(pos)
        pop.connect("closed", lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        pop.popup()
        if first:
            GLib.idle_add(lambda: (first[0].grab_focus(), False)[1])
        return pop

    def show_add_menu(self, row, view):
        self._popup(self.add_menu_model(row.node), view, view.cursor_rect(), node=row.node)

    def show_item_menu(self, row):
        self.clear_carets()
        node = row.node
        m = Gio.Menu()
        if is_text(node):
            m.append_section("Item Type", self._kind_section(node))
            m.append_section("Add", self.add_menu_model(node))
            d = Gio.Menu()
            d.append_item(_mi("Delete Item", "ed.delete-item"))
            m.append_section(None, d)
        else:
            d = Gio.Menu()
            d.append_item(_mi("Delete Table" if node.kind == "table" else "Delete Block", "ed.delete-item"))
            m.append_section(None, d)
        self._popup(m, row.prefix, node=node)

    def on_click(self, row, view, gesture, x, y):
        self._click_time = time.monotonic()
        self.clear_carets()
        btn = gesture.get_current_button()
        if btn == 3:
            self.set_current(row.node, view)
            self._prepare_context(row, view, (x, y))
            return
        state = gesture.get_current_event_state()
        if btn == 1 and state & Gdk.ModifierType.SHIFT_MASK and self.current is not None \
                and self.current is not row.node:
            order = self._order()
            self.sel_anchor = self.sel_anchor if self.sel else self.current
            self.sel_head = row.node
            a, b = sorted((order.index(self.sel_anchor), order.index(row.node)))
            self.set_selection(order[a:b + 1])
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            return
        self.clear_selection()

    def _prepare_context(self, row, view, point):
        """Fill the text view's right-click menu (shown below GTK's cut/copy/paste)."""
        menu = Gio.Menu()
        it = view.iter_at_widget_point(*point) if point else view.cursor_iter()
        self._ctx = None
        sp = SPELL["speller"]
        if SPELL["enabled"] and sp is not None and it is not None:
            hit = view.misspelled_at(it)
            if hit:
                (s, e), word = hit
                self._ctx = (view, s, e)
                sec = Gio.Menu()
                sugg = sp.suggest(word)
                for w in sugg:
                    sec.append_item(_mi(w, "ed.spell-replace", w))
                if not sugg:
                    sec.append_item(_mi("No Suggestions", "ed.noop"))
                sec.append_item(_mi(f"Add “{word}” to Dictionary", "ed.spell-add", word))
                sec.append_item(_mi("Ignore", "ed.spell-ignore", word))
                menu.append_section(None, sec)
        if self.sel:
            s = Gio.Menu()
            s.append_item(_mi("Copy Items", "ed.copy-items", accel="<Control>c"))
            s.append_item(_mi("Cut Items", "ed.cut-items", accel="<Control>x"))
            s.append_item(_mi("Delete Items", "ed.delete-items", accel="Delete"))
            menu.append_section(None, s)
        f = Gio.Menu()
        f.append_item(_mi("Bold", "ed.bold", accel="<Control>b"))
        f.append_item(_mi("Italic", "ed.italic", accel="<Control>i"))
        menu.append_section(None, f)
        if isinstance(row, TextRow):
            self._menu_node = None
            s = Gio.Menu()
            s.append_submenu("Item Type", self._kind_section(row.node))
            s.append_submenu("Add", self.add_menu_model(row.node))
            menu.append_section(None, s)
            s = Gio.Menu()
            s.append_item(_mi("Expand Selection", "ed.select-scope", accel="<Control>w"))
            s.append_item(_mi("Select All Items", "ed.select-all", accel="<Control>a"))
            s.append_item(_mi("Paste as Plain Text", "ed.paste-plain", accel="<Control><Shift>v"))
            s.append_item(_mi("Delete Item", "ed.delete-item"))
            menu.append_section(None, s)
        if self.spell_menu is not None:
            sm = Gio.Menu()
            sm.append_submenu("Spelling", self.spell_menu)
            menu.append_section(None, sm)
        u = Gio.Menu()
        u.append_item(_mi("Undo", "ed.undo", accel="<Control>z"))
        u.append_item(_mi("Redo", "ed.redo", accel="<Control><Shift>z"))
        menu.append_section(None, u)
        view.set_extra_menu(menu)

    def _format_cmd(self, attr):
        if self.sel:
            self.format_items(attr)
        elif self.cur_view is not None:
            self.cur_view.toggle(attr)

    # -- spelling ------------------------------------------------------------------------

    def set_spelling(self, speller, enabled):
        SPELL["speller"] = speller
        SPELL["enabled"] = enabled
        for v in self.all_views():
            v.recheck_spelling()

    def _spell_replace(self, word):
        self._replace_word(word)

    def _replace_word(self, word):
        """Replace the word recorded in self._ctx, keeping its bold/italic."""
        if not self._ctx:
            return
        view, s, e = self._ctx
        buf = view.get_buffer()
        it = buf.get_iter_at_offset(s)
        fmt = (it.has_tag(view.tag_bold), it.has_tag(view.tag_italic))
        view.grab_focus()
        view.select_range(s, e)
        with self._op():
            view.insert_runs([Run(word, *fmt)])

    def _spell_add(self, word):
        if SPELL["speller"]:
            SPELL["speller"].add(word)
            for v in self.all_views():
                v.recheck_spelling()

    def _spell_ignore(self, word):
        if SPELL["speller"]:
            SPELL["speller"].ignore(word)
            for v in self.all_views():
                v.recheck_spelling()

    # -- Ctrl+Space: spelling fixes and word completion ------------------------------------

    def _assist_sections(self, view):
        """[(title, [(label, callback|None)])] for the word at the cursor."""
        self._ctx = None
        it = view.cursor_iter()
        wb = view.word_bounds(it)
        if wb is None:
            return []
        s, e = wb
        text = view.get_plain()
        word, prefix = text[s:e], text[s:it.get_offset()]
        self._ctx = (view, s, e)
        sp = SPELL["speller"]
        comps = []
        if prefix:
            current = count_words(node_texts(self.doc.root))
            current[word] -= 1  # the word being typed doesn't count as a source
            path = self.doc.path
            book = self._book_words.counts(path.parent, exclude=path) if path else None
            words = dictionary_words(sp.tag_for(prefix)) if sp is not None else []
            comps = complete(prefix, +current, book, words)
        sections = []
        if comps:
            sections.append(("Complete", [(c, lambda c=c: self._replace_word(c)) for c in comps]))
        # While a word is being completed it is "misspelled" only because it's unfinished,
        # so spelling fixes show when nothing completes it or the cursor is inside it.
        mid_word = it.get_offset() < e
        if (mid_word or not comps) and SPELL["enabled"] and sp is not None \
                and should_check(word) and not sp.check(word):
            sugg = sp.suggest(word)
            rows = [(w, lambda w=w: self._replace_word(w)) for w in sugg]
            if not sugg:
                rows.append(("No spelling suggestions", None))
            rows.append((f"Add “{word}” to Dictionary", lambda: self._spell_add(word)))
            rows.append(("Ignore", lambda: self._spell_ignore(word)))
            sections.insert(0, ("Spelling", rows))
        return sections

    def show_assist(self, view):
        """Popup at the cursor with spelling fixes and completions. Typing keeps going
        into the text and refilters; Enter or Tab picks, Esc closes."""
        self.clear_carets()
        pop = Gtk.Popover(has_arrow=False)
        pop.add_css_class("menu")
        pop.add_css_class("ntz-menu")
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, activate_on_single_click=True)
        pop.set_child(lb)
        pop.set_parent(view)
        self._assist_pop = pop

        def place():
            rect = view.cursor_rect()
            pop.set_pointing_to(rect)
            ok, pt = view.compute_point(self, Graphene.Point().init(rect.x, rect.y))
            pop.set_position(Gtk.PositionType.TOP if ok and pt.y > self.get_height() * 0.6
                             else Gtk.PositionType.BOTTOM)

        def add_row(child, cb=None, kind=None):
            row = Gtk.ListBoxRow(activatable=cb is not None, selectable=False,
                                 can_focus=cb is not None)
            row.set_child(child)
            if kind:
                row.add_css_class(kind)
            row._cb = cb
            row._choice = kind == "choice"
            lb.append(row)
            return row

        def fill():
            while (c := lb.get_first_child()) is not None:
                lb.remove(c)
            sections = self._assist_sections(view)
            first = None
            for title, rows in sections:
                if lb.get_first_child() is not None:
                    add_row(Gtk.Separator(), kind="sep")
                head = Gtk.Label(label=title, xalign=0, css_classes=["heading", "dim-label"])
                add_row(head, kind="head")
                for label, cb in rows:
                    r = add_row(Gtk.Label(label=label, xalign=0), cb, kind="choice")
                    r.set_sensitive(cb is not None)
                    first = first or (r if cb else None)
            if not sections:
                add_row(Gtk.Label(label="No suggestions", xalign=0, css_classes=["dim-label"]))
            numbered.clear()
            numbered.update(_number_rows(lb))
            place()
            return first, bool(sections)

        numbered = {}

        def pick(row):
            if row is None or row._cb is None:
                return
            pop.popdown()
            cb = row._cb
            GLib.idle_add(lambda: (cb(), view.grab_focus(), False)[2])

        lb.connect("row-activated", lambda _lb, row: pick(row))

        def on_key(_c, keyval, _kc, state):
            name = Gdk.keyval_name(keyval)
            ctrl, shift, alt = _mods(state)
            n = None if ctrl or alt else _digit(keyval)
            if n in numbered:
                pick(numbered[n])
                return True
            if name in ("Up", "Down", "Page_Up", "Page_Down", "Return", "KP_Enter", "space") \
                    and not ctrl:
                return False if name != "space" else self._assist_type(view, " ", pop)
            if name == "Tab":
                pick(lb.get_focus_child())
                return True
            if name == "Escape":
                pop.popdown()
                return True
            buf = view.get_buffer()
            if name == "BackSpace":
                it = view.cursor_iter()
                if it.get_offset() > 0:
                    start = it.copy()
                    start.backward_char()
                    buf.delete(start, it)
            else:
                uni = Gdk.keyval_to_unicode(keyval)
                if ctrl or alt or not uni or not chr(uni).isprintable():
                    return False
                buf.insert_interactive_at_cursor(chr(uni), -1, True)
            first, any_ = fill()
            if not any_:
                pop.popdown()
            elif first is not None:
                first.grab_focus()
            return True

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", on_key)
        pop.add_controller(keys)

        def closed(p):
            self._assist_pop = None
            view.grab_focus()
            GLib.idle_add(lambda: (p.unparent(), False)[1])

        pop.connect("closed", closed)
        first, _ = fill()
        pop.popup()
        if first is not None:
            GLib.idle_add(lambda: (first.grab_focus(), False)[1])
        return pop

    def _assist_type(self, view, ch, pop):
        """A space ends the word: type it and close the popup."""
        view.get_buffer().insert_interactive_at_cursor(ch, -1, True)
        pop.popdown()
        return True

    # -- multi-cursor (double-tap Ctrl, keep it held, then ↑/↓) ----------------------------

    def _text_views(self):
        return [self.rows[n.id].view for n in self._order()
                if isinstance(self.rows.get(n.id), TextRow)]

    def add_caret(self, view, delta):
        order = self._text_views()
        active = [v for v in [view] + self.mc_views if v in order]
        if not active:
            return
        idxs = [order.index(v) for v in active]
        t = (max(idxs) + 1) if delta > 0 else (min(idxs) - 1)
        if 0 <= t < len(order):
            target = order[t]
            target.add_caret(view.cursor_offset())
            if target not in self.mc_views:
                self.mc_views.append(target)

    def clear_carets(self):
        for v in self.mc_views:
            v.clear_carets()
        self.mc_views = []

    def _all_marks(self, view):
        marks = [(view, view.get_buffer().get_insert())]
        for v in self.mc_views:
            marks += [(v, m) for m in v.carets]
        return marks

    def _multi_key(self, view, keyval, name, ctrl, alt):
        if name == "Escape":
            self.clear_carets()
            return True
        uni = Gdk.keyval_to_unicode(keyval)
        ch = chr(uni) if uni else ""
        marks = self._all_marks(view)
        if not ctrl and not alt and ch and ch.isprintable():
            with self._op(group=("multi",)):
                for v, m in marks:
                    v.get_buffer().insert(v.get_buffer().get_iter_at_mark(m), ch)
            self._redraw_carets()
            return True
        if name in ("BackSpace", "Delete") and not ctrl:
            with self._op(group=("multi",)):
                for v, m in marks:
                    buf = v.get_buffer()
                    it = buf.get_iter_at_mark(m)
                    other = it.copy()
                    moved = other.backward_char() if name == "BackSpace" else other.forward_char()
                    if moved:
                        buf.delete(it, other)
            self._redraw_carets()
            return True
        if name in ("Left", "Right", "Home", "End") and not ctrl:
            for v, m in marks:
                buf = v.get_buffer()
                it = buf.get_iter_at_mark(m)
                if name == "Left":
                    it.backward_char()
                elif name == "Right":
                    it.forward_char()
                elif name == "Home":
                    it.set_line_offset(0)
                else:
                    it.forward_to_line_end()
                if m == buf.get_insert():
                    buf.place_cursor(it)
                else:
                    buf.move_mark(m, it)
            self._redraw_carets()
            return True
        self.clear_carets()
        return None

    def _redraw_carets(self):
        for v in self.mc_views:
            v.queue_draw()
