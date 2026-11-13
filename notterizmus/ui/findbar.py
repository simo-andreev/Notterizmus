"""Find (Ctrl+F) and replace (Ctrl+H or Ctrl+R) in the open chapter: items and table cells."""
from __future__ import annotations

from gi.repository import Adw, Gdk, GLib, GObject, Gtk

from ..find import clean_replacement, find_all
from ..model import display_order


class FindBar(Gtk.SearchBar):
    __gtype_name__ = "NtzFindBar"

    def __init__(self, editor, toast):
        super().__init__(show_close_button=True)
        self.editor = editor
        self.toast = toast
        self.matches = []        # [(view, start, end)] in outline order
        self.current = -1
        self._refresh_src = None
        self._anchor = None      # (view, offset) where the cursor was when the search began
        self._found_for = None   # the query the matches are for

        self.entry = Gtk.SearchEntry(placeholder_text="Find in this chapter", hexpand=True, search_delay=0)
        self.count = Gtk.Label(width_chars=10, xalign=1)
        self.count.add_css_class("dim-label")
        self.count.add_css_class("numeric")
        prev_btn = Gtk.Button(icon_name="go-up-symbolic", tooltip_text="Previous match (Shift+Enter, Ctrl+Shift+G)")
        next_btn = Gtk.Button(icon_name="go-down-symbolic", tooltip_text="Next match (Enter, Ctrl+G)")
        self.case = Gtk.ToggleButton(label="Aa", tooltip_text="Match case")
        self.whole = Gtk.ToggleButton(label="Whole Words", tooltip_text="Match whole words only")
        self.replacing = Gtk.ToggleButton(icon_name="edit-find-replace-symbolic", tooltip_text="Replace (Ctrl+H or Ctrl+R)")
        for b in (prev_btn, next_btn, self.case, self.whole, self.replacing):
            b.add_css_class("flat")
        row1 = Gtk.Box(spacing=6)
        for w in (self.entry, self.count, prev_btn, next_btn, self.case, self.whole, self.replacing):
            row1.append(w)

        self.replace_entry = Gtk.Entry(placeholder_text="Replace with", hexpand=True)
        replace_btn = Gtk.Button(label="Replace")
        replace_all = Gtk.Button(label="Replace All")
        row2 = Gtk.Box(spacing=6, margin_top=6)
        for w in (self.replace_entry, replace_btn, replace_all):
            row2.append(w)
        self.replace_row = Gtk.Revealer(child=row2)
        self.replacing.bind_property("active", self.replace_row, "reveal-child",
                                     GObject.BindingFlags.SYNC_CREATE)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(row1)
        box.append(self.replace_row)
        self.set_child(Adw.Clamp(maximum_size=820, child=box))
        self.connect_entry(self.entry)

        self.entry.connect("search-changed", lambda *_: self.refresh(after=self._anchor))
        self.entry.connect("activate", lambda *_: self._activate())
        self.entry.connect("stop-search", lambda *_: self.close())
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._entry_key)
        self.entry.add_controller(keys)
        prev_btn.connect("clicked", lambda *_: self.step(-1))
        next_btn.connect("clicked", lambda *_: self.step(1))
        self.case.connect("toggled", lambda *_: self.refresh())
        self.whole.connect("toggled", lambda *_: self.refresh())
        self.replacing.connect("toggled", lambda b: b.get_active() and self.replace_entry.grab_focus())
        self.replace_entry.connect("activate", lambda *_: self.replace_current())
        replace_btn.connect("clicked", lambda *_: self.replace_current())
        replace_all.connect("clicked", lambda *_: self.replace_all())
        self.connect("notify::search-mode-enabled", self._mode_changed)
        # Escape closes the bar from anywhere in it: only the search field has its own
        # Escape (stop-search), not the replace field or the buttons.
        esc = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        esc.connect("key-pressed", self._bar_key)
        self.add_controller(esc)

    # -- opening and closing ------------------------------------------------------------------

    def open(self, replace=False, prefill=None):
        # Where to search from: taken before the search field gets focus, because selecting
        # its text takes the primary selection from the chapter, which collapses the
        # chapter's selection to its end (the match after the selected word would win).
        self._anchor = self._cursor_point()
        if prefill:
            self.entry.set_text(prefill)
        if replace:
            self.replacing.set_active(True)
        self.set_search_mode(True)
        self.entry.grab_focus()
        self.entry.select_region(0, -1)
        self.refresh(after=self._anchor)

    def _cursor_point(self):
        """(view, offset) of the text cursor, or the start of the selection."""
        view = self.editor.cur_view
        if view is None or view.get_root() is None:
            return None
        sel = view.get_buffer().get_selection_bounds()
        return (view, sel[0].get_offset() if sel else view.cursor_offset())

    def close(self, focus_match=True):
        """Hide the bar. focus_match: put the cursor in the text at the current match
        (from the bar); otherwise leave it where it is (Escape in the text)."""
        target = self.matches[self.current][0] if 0 <= self.current < len(self.matches) else None
        self.set_search_mode(False)
        view = (target or self.editor.cur_view) if focus_match else None
        if view is not None:
            view.grab_focus()

    def _bar_key(self, _ctl, keyval, _code, _state):
        if Gdk.keyval_name(keyval) == "Escape" and self.get_search_mode():
            self.close()
            return True
        return False

    def _mode_changed(self, *_):
        if not self.get_search_mode():
            self._clear()
            self.matches, self.current = [], -1

    def _activate(self):
        """Enter: the next match (finding first if Enter came before the search did)."""
        if self.entry.get_text() != self._found_for:
            self.refresh(after=self._anchor)
        else:
            self.step(1)

    def _entry_key(self, _ctl, keyval, _code, state):
        if Gdk.keyval_name(keyval) in ("Return", "KP_Enter") and state & Gdk.ModifierType.SHIFT_MASK:
            self.step(-1)
            return True
        return False

    # -- matching ---------------------------------------------------------------------------------

    def views(self):
        """Text views of the chapter in outline order (items, then each table's cells)."""
        doc = self.editor.doc
        if doc is None:
            return []
        out = []
        for node in display_order(doc.root):
            row = self.editor.rows.get(node.id)
            if row is not None:
                out.extend(row.views())
        return out

    def _clear(self):
        for v in self.views():
            buf = v.get_buffer()
            start, end = buf.get_bounds()
            buf.remove_tag(v.tag_found, start, end)
            buf.remove_tag(v.tag_found_current, start, end)

    def schedule_refresh(self):
        """The chapter changed while the bar is open: find again shortly."""
        if not self.get_search_mode():
            return
        if self._refresh_src:
            GLib.source_remove(self._refresh_src)
        self._refresh_src = GLib.timeout_add(200, self._refresh_later)

    def _refresh_later(self):
        self._refresh_src = None
        self.refresh(select=False)
        return False

    def refresh(self, from_cursor=False, select=True, after=None):
        """Find all matches again. from_cursor: make the first match at or after the text
        cursor current; after=(view, offset): the first match at or after that point."""
        old = self.matches[self.current] if 0 <= self.current < len(self.matches) else None
        self._clear()
        query = self.entry.get_text()
        self._found_for = query
        views = self.views()
        self.matches = []
        for v in views:
            for s, e in find_all(v.get_plain(), query, self.case.get_active(), self.whole.get_active()):
                self.matches.append((v, s, e))
                buf = v.get_buffer()
                buf.apply_tag(v.tag_found, buf.get_iter_at_offset(s), buf.get_iter_at_offset(e))
        order = {v: i for i, v in enumerate(views)}
        if after is None and from_cursor and self.editor.cur_view in order:
            after = (self.editor.cur_view, self.editor.cur_view.get_buffer().get_selection_bounds()[0].get_offset()
                     if self.editor.cur_view.has_selection() else self.editor.cur_view.cursor_offset())
        elif after is None and old is not None and old[0] in order:
            after = (old[0], old[1])
        self.current = 0 if self.matches else -1
        if after is not None and self.matches:
            key = (order.get(after[0], -1), after[1])
            self.current = next((i for i, (v, s, _e) in enumerate(self.matches) if (order[v], s) >= key), 0)
        self._show_current(select)

    def _show_current(self, select=True):
        query = self.entry.get_text()
        if not query:
            self.count.set_text("")
        elif not self.matches:
            self.count.set_text("No results")
        else:
            self.count.set_text(f"{self.current + 1} of {len(self.matches)}")
        if self.matches or not query:
            self.entry.remove_css_class("error")
        else:
            self.entry.add_css_class("error")
        for v, s, e in self.matches:
            buf = v.get_buffer()
            buf.remove_tag(v.tag_found_current, *buf.get_bounds())
        if not (0 <= self.current < len(self.matches)):
            return
        v, s, e = self.matches[self.current]
        buf = v.get_buffer()
        buf.apply_tag(v.tag_found_current, buf.get_iter_at_offset(s), buf.get_iter_at_offset(e))
        if select:
            buf.select_range(buf.get_iter_at_offset(s), buf.get_iter_at_offset(e))
            self.editor.ensure_visible(v)

    def step(self, delta):
        """Next (+1) or previous (-1) match, wrapping around."""
        if not self.get_search_mode():
            self.open()
            return
        if not self.matches:
            return
        self.current = (self.current + delta) % len(self.matches)
        self._show_current()

    # -- replacing -----------------------------------------------------------------------------------

    def replace_current(self):
        if not (0 <= self.current < len(self.matches)):
            return
        view, s, e = self.matches[self.current]
        text = clean_replacement(self.replace_entry.get_text())
        with self.editor._op():
            view.replace_range(s, e, text)
        self.refresh(after=(view, s + len(text)))

    def replace_all(self):
        if not self.matches:
            return
        text = clean_replacement(self.replace_entry.get_text())
        count = len(self.matches)
        with self.editor._op():  # one undo step for all of them
            for view, s, e in sorted(self.matches, key=lambda m: -m[1]):
                view.replace_range(s, e, text)
        self.refresh(select=False)
        self.toast(f"Replaced {count} match{'es' if count != 1 else ''}")
