"""The chapter list's width (CR38 in CODE_REVIEW.md): the drag handle over its edge, and
the breakpoint that turns it into an overlay when the text no longer fits beside it.

Uses the window's split, handle, _overlay, _collapse and state; keeps _sidebar_w and
_drag_from."""
from __future__ import annotations

from gi.repository import Adw, GLib, Gtk

from .helpers import save_state

SIDEBAR_DEFAULT, SIDEBAR_MIN, SIDEBAR_MAX = 260, 180, 520  # chapter list width, px
TEXT_ROOM = 20  # spare px beside the text column's minimum width


class WindowSizing:
    def _text_min_width(self):
        return self.split.get_content().measure(Gtk.Orientation.HORIZONTAL, -1)[0]

    def set_sidebar_width(self, width, save=False):
        w = int(max(SIDEBAR_MIN, min(SIDEBAR_MAX, width)))
        self._sidebar_w = w
        self.split.set_min_sidebar_width(w)
        self.split.set_max_sidebar_width(w)
        self._collapse.set_condition(
            Adw.BreakpointCondition.parse(f"max-width: {w + self._text_min_width() + TEXT_ROOM}px"))
        self._update_handle()
        if save:
            self.state["sidebar_width"] = w
            save_state(self.state)

    def _update_handle(self):
        self.handle.set_visible(self.split.get_show_sidebar() and not self.split.get_collapsed())
        rtl = self.get_direction() == Gtk.TextDirection.RTL
        edge = max(0, self._sidebar_w - 3)  # 6 px wide, centred on the edge
        self.handle.set_halign(Gtk.Align.END if rtl else Gtk.Align.START)
        self.handle.set_margin_start(0 if rtl else edge)
        self.handle.set_margin_end(edge if rtl else 0)

    def _handle_drag_begin(self, gesture, x, y):
        ok, box = self.handle.compute_bounds(self._overlay)
        if not (self.handle.get_visible() and ok and box.origin.x - 2 <= x <= box.origin.x + box.size.width + 2):
            gesture.set_state(Gtk.EventSequenceState.DENIED)  # not on the handle
            return
        # Claim only once the pointer moves (in _handle_drag_update): claiming on press
        # would cancel the handle's own click gesture, so double-click couldn't reset.
        self._drag_from = self._sidebar_w

    def _handle_drag_update(self, gesture, dx, _dy):
        if self._drag_from is None:
            return
        if not self.handle.has_css_class("dragging"):
            if abs(dx) < 3:
                return
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.handle.add_css_class("dragging")
        if self.get_direction() == Gtk.TextDirection.RTL:
            dx = -dx
        # never collapse while dragging ("max-width: N" includes N, hence the extra pixel)
        room = self.get_width() - self._text_min_width() - TEXT_ROOM - 1
        self.set_sidebar_width(min(self._drag_from + dx, room))

    def _handle_drag_end(self, *_):
        dragged = self.handle.has_css_class("dragging")
        self._drag_from = None
        self.handle.remove_css_class("dragging")
        if dragged:
            self.set_sidebar_width(self._sidebar_w, save=True)

    def _on_sidebar_shown(self, split, _pspec):
        self._update_handle()
        on = split.get_show_sidebar()
        self.lookup_action("sidebar").set_state(GLib.Variant.new_boolean(on))
        if not split.get_collapsed():  # an overlay closing by itself isn't a preference
            self.state["sidebar"] = on
            save_state(self.state)
        if on:
            self._reload_sidebar()
