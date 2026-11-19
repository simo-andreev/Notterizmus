"""Small helpers shared by the UI modules (CR48 in CODE_REVIEW.md)."""
from __future__ import annotations

import weakref

from gi.repository import GLib


def run_once(fn, *args):
    """Call fn(*args) and return GLib.SOURCE_REMOVE, so that a GLib.idle_add or
    GLib.timeout_add callback runs once: GLib.idle_add(run_once, entry.grab_focus)."""
    fn(*args)
    return GLib.SOURCE_REMOVE


def weak_handler(method):
    """A signal handler that calls `method` while its object lives, without keeping it
    alive: a widget's handler that held the widget itself would make a cycle through GTK
    that Python's garbage collector can't see (R29c)."""
    ref = weakref.WeakMethod(method)

    def handler(*args):
        m = ref()
        return None if m is None else m(*args)
    return handler


def let_go_when_closed(pop, *controllers):
    """When the popover closes, take it off its parent and take away its child and these
    controllers of ours: their handlers hold it, so it would never be freed."""
    ours = list(controllers)

    def closed(p):
        def later():
            p.unparent()
            for c in ours:
                p.remove_controller(c)
            ours.clear()  # and this handler holds them no more
            p.set_child(None)
        GLib.idle_add(run_once, later)
    pop.connect("closed", closed)


def set_class(widget, name, on):
    """Add the CSS class `name` to the widget when `on` is true, else remove it."""
    if on:
        widget.add_css_class(name)
    else:
        widget.remove_css_class(name)
