"""Small helpers shared by the UI modules (CR48 in CODE_REVIEW.md)."""
from __future__ import annotations

from gi.repository import GLib


def run_once(fn, *args):
    """Call fn(*args) and return GLib.SOURCE_REMOVE, so that a GLib.idle_add or
    GLib.timeout_add callback runs once: GLib.idle_add(run_once, entry.grab_focus)."""
    fn(*args)
    return GLib.SOURCE_REMOVE


def set_class(widget, name, on):
    """Add the CSS class `name` to the widget when `on` is true, else remove it."""
    if on:
        widget.add_css_class(name)
    else:
        widget.remove_css_class(name)
