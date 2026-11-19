"""The window's text zoom (CR38 in CODE_REVIEW.md): only the chapter text changes size,
through one CSS provider for the whole app.

Uses the window's editor, state, toasts and zoom_label; keeps _zoom, _zoom_css,
_zoom_toast and _scroll_zoom."""
from __future__ import annotations

from gi.repository import Adw, Gtk

from .helpers import save_state

ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, TEXT_PT = 60, 250, 10, 11  # chapter text zoom, % and base size


class WindowZoom:
    def set_zoom(self, percent, save=True, announce=True):
        """Size of the chapter text, in % of normal (11 pt); the rest of the window keeps its size."""
        pct = int(max(ZOOM_MIN, min(ZOOM_MAX, round(percent / ZOOM_STEP) * ZOOM_STEP)))
        changed = pct != self._zoom
        self._zoom = pct
        size = TEXT_PT * pct / 100
        self._zoom_css.load_from_string(
            f".outline .prefix, .outline textview.rt, .outline textview.rt text {{ font-size: {size:.2f}pt; }}")
        self.zoom_label.set_label(f"{pct}%")
        self.lookup_action("zoom-in").set_enabled(pct < ZOOM_MAX)
        self.lookup_action("zoom-out").set_enabled(pct > ZOOM_MIN)
        if changed:
            self.editor.text_size_changed()
        if save:
            self.state["zoom"] = pct
            save_state(self.state)
        if announce:
            if self._zoom_toast is not None:
                self._zoom_toast.dismiss()
            self._zoom_toast = Adw.Toast(title=f"Text size {pct}%", timeout=1, use_markup=False)
            self.toasts.add_toast(self._zoom_toast)

    def scroll_zoom(self, ctrl, dy):
        """Ctrl + scroll wheel zooms (up: larger). Returns True when it used the scroll."""
        if not ctrl:
            return False
        self._scroll_zoom -= dy
        steps = int(self._scroll_zoom)
        if steps:
            self._scroll_zoom -= steps
            self.set_zoom(self._zoom + steps * ZOOM_STEP)
        return True


_ZOOM_PROVIDER = None


def _zoom_provider(display):
    global _ZOOM_PROVIDER
    if _ZOOM_PROVIDER is None:
        _ZOOM_PROVIDER = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(display, _ZOOM_PROVIDER, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    return _ZOOM_PROVIDER
