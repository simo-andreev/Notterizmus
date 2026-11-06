"""Helpers for the GTK UI tests: drive the real app with key presses and check what it draws.

Run the tests with scripts/ui-tests.sh. It starts a private Broadway display (no window
appears on your screen), points the config, data and Documents folders at a scratch
directory and fails if GTK printed any warnings. A plain
`python3 -m unittest discover -s tests -t .` skips these tests.
"""
from __future__ import annotations

import itertools
import os
import time
import unittest
from pathlib import Path

ENABLED = os.environ.get("NOTTERIZMUS_UI_TESTS") == "1"
# Frame-by-frame checks need a display that draws at a normal rate (Weston). Broadway
# without a browser attached draws about once a second, so they're skipped there.
FRAMES = os.environ.get("NOTTERIZMUS_UI_FRAMES") == "1"

if ENABLED:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Graphene", "1.0")
    from gi.repository import Gdk, Gio, GLib, Graphene, Gtk  # noqa: F401

_app = None
_chapter_no = itertools.count(1)


def _check_scratch():
    scratch = os.environ.get("NOTTERIZMUS_UI_SCRATCH")
    if not scratch:
        raise RuntimeError("UI tests must run through scripts/ui-tests.sh (no scratch folder set)")
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        if not os.environ.get(var, "").startswith(scratch):
            raise RuntimeError(f"{var} must point inside {scratch}, so your own settings stay untouched")


def app():
    """The app under test, started once per test run."""
    global _app
    if _app is None:
        _check_scratch()
        from notterizmus.ui.app import App
        a = App()
        a.set_flags(a.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
        a.register(None)
        a.activate()
        _app = a
        pump(1.0)
    return _app


class UITestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENABLED:
            raise unittest.SkipTest("UI tests run with scripts/ui-tests.sh")
        cls.app = app()
        cls.win = cls.app.win
        cls.ed = cls.win.editor

    def setUp(self):
        close_popovers()
        self.ed.clear_carets()


# -- main loop --------------------------------------------------------------------------

def pump(seconds=0.1):
    ctx = GLib.MainContext.default()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.003)


def pump_until(cond, timeout=4.0):
    ctx = GLib.MainContext.default()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        if cond():
            return True
        time.sleep(0.003)
    return cond()


# -- chapters -----------------------------------------------------------------------------

def open_chapter(nodes, title="Test", book="Book"):
    """Save a chapter with these top-level nodes in the scratch notes folder and open it."""
    from notterizmus.model import Document, Node, chapter_filename
    from notterizmus.ui.window import notes_root
    win = app().win
    no = next(_chapter_no)
    doc = Document(Node("root", children=nodes), book, no, title,
                   notes_root() / book / chapter_filename(no, title), lang="en_US")
    doc.save()
    win.open_path(doc.path)
    settle()
    return win.doc


def settle(extra=0.35):
    """Wait until every text view has a real width, then a few more frames."""
    ed = app().win.editor
    pump_until(lambda: all(v.get_width() > 1 for v in ed.all_views()) and ed._focus_wait is None)
    pump(extra)


def row(node):
    return app().win.editor.rows[node.id]


def focus(node, offset=-1):
    r = row(node)
    r.focus(offset)
    pump(0.15)
    return r


# -- keys and text ----------------------------------------------------------------------------

_MODS = {"ctrl": "CONTROL_MASK", "shift": "SHIFT_MASK", "alt": "ALT_MASK"}


def key_controller(widget):
    ctrls = widget.observe_controllers()
    for i in range(ctrls.get_n_items()):
        c = ctrls.get_item(i)
        if isinstance(c, Gtk.EventControllerKey):
            return c
    raise AssertionError(f"{widget} has no key controller")


def press(widget, name, ctrl=False, shift=False, alt=False, wait=0.12):
    """Emit a key press on the widget's own key controller, as GTK would. Returns True
    if the app handled it (unhandled keys do nothing here; type text with type_text)."""
    if shift and len(name) == 1 and name.isalpha():
        name = name.upper()  # GTK reports Shift+z as "Z"
    elif shift and name == "Tab":
        name = "ISO_Left_Tab"
    state = Gdk.ModifierType(0)
    for flag, on in (("ctrl", ctrl), ("shift", shift), ("alt", alt)):
        if on:
            state |= getattr(Gdk.ModifierType, _MODS[flag])
    handled = key_controller(widget).emit("key-pressed", Gdk.keyval_from_name(name), 0, state)
    pump(wait)
    return handled


def type_text(view, text, wait=0.12):
    view.grab_focus()
    view.get_buffer().insert_interactive_at_cursor(text, -1, True)
    pump(wait)


# -- what's on screen ------------------------------------------------------------------------------

def point_in(widget, target, x=0, y=0):
    ok, p = widget.compute_point(target, Graphene.Point().init(x, y))
    return (p.x, p.y) if ok else None


def row_positions():
    """y of every row and spacer label in the outline, keyed by widget."""
    box = app().win.editor.box
    out = {}
    c = box.get_first_child()
    while c is not None:
        if c.get_visible():
            p = point_in(c, box)
            if p:
                out[c] = round(p[1])
        c = c.get_next_sibling()
    return out


def record_frames(action, frames=12):
    """Run action(), then return the row positions as drawn in each of the next frames."""
    if not FRAMES:
        raise unittest.SkipTest("frame-by-frame checks need Weston (sudo apt install weston)")
    win = app().win
    clock = win.get_frame_clock()
    seen = []
    hid = clock.connect("after-paint", lambda _c: seen.append(row_positions()))
    tick = win.editor.add_tick_callback(lambda *_: True)  # keep frames coming
    try:
        action()
        pump_until(lambda: len(seen) >= frames, 6)
    finally:
        clock.disconnect(hid)
        win.editor.remove_tick_callback(tick)
    return seen


def cursor_in_view(view):
    """True if the text cursor of view is fully inside the visible part of the outline."""
    sw = app().win.editor
    r = view.cursor_rect()
    top = point_in(view, sw, r.x, r.y)
    return top is not None and top[1] >= 0 and top[1] + r.height <= sw.get_height()


def walk(widget):
    yield widget
    c = widget.get_first_child()
    while c is not None:
        yield from walk(c)
        c = c.get_next_sibling()


def open_popovers():
    return [w for w in walk(app().win) if isinstance(w, Gtk.Popover) and w.get_visible()]


def close_popovers():
    for p in open_popovers():
        p.popdown()
    pump(0.05)


def menu_choices(pop):
    """[(number, label, row)] for the numbered rows of one of the app's popup menus."""
    out = []
    for w in walk(pop):
        if isinstance(w, Gtk.ListBoxRow) and getattr(w, "_choice", False):
            labels = [x for x in walk(w) if isinstance(x, Gtk.Label)]
            num = next((x.get_text() for x in labels if x.has_css_class("menu-num")), "")
            text = next((x.get_text() for x in labels if not x.has_css_class("menu-num") and x.get_text()), "")
            out.append((num, text, w))
    return out


def clipboard(mime):
    """Read the app's own clipboard as text for one MIME type."""
    cb = app().win.get_clipboard()
    box = {}

    # Read asynchronously: the app itself writes its own clipboard data from the main
    # loop, so a blocking read here would wait forever.
    def spliced(out, res):
        try:
            out.splice_finish(res)
            box["text"] = out.steal_as_bytes().get_data().decode("utf-8")
        except GLib.Error as e:
            box["error"] = e.message

    def opened(_cb, res):
        try:
            stream, _mime = cb.read_finish(res)
        except GLib.Error as e:
            box["error"] = e.message
            return
        out = Gio.MemoryOutputStream.new_resizable()
        flags = Gio.OutputStreamSpliceFlags.CLOSE_SOURCE | Gio.OutputStreamSpliceFlags.CLOSE_TARGET
        out.splice_async(stream, flags, GLib.PRIORITY_DEFAULT, None, spliced)

    cb.read_async([mime], GLib.PRIORITY_DEFAULT, None, opened)
    pump_until(lambda: box, 3)
    if "error" in box:
        raise AssertionError(f"clipboard read failed: {box['error']}")
    return box.get("text")


def scratch():
    return Path(os.environ["NOTTERIZMUS_UI_SCRATCH"])
