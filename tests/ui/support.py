"""Helpers for the GTK UI tests: drive the real app with key presses and check what it draws.

Run the tests with scripts/ui-tests.sh. It starts a private Broadway display (no window
appears on your screen), points the config, data and Documents folders at a scratch
directory and fails if GTK printed any warnings. A plain
`python3 -m unittest discover -s tests -t .` skips these tests.

Real mouse drags: real_drag() presses, moves and releases the left button through
Broadway, so the app's own gestures and GtkTextView's run as for a real mouse.

Two ways to press keys:
- real_key() / real_type(): real key events through Broadway (tests/ui/broadway_input.py),
  so GTK's whole dispatch runs: app shortcuts, capture/bubble, the focused widget. Use
  these for anything about which widget gets a key (Escape, shortcuts, typing).
- press(): emits "key-pressed" on one widget's own controller; quicker for driving the
  editor's key handling directly.
"""
from __future__ import annotations

import itertools
import os
import time
import unittest
from pathlib import Path

ENABLED = os.environ.get("NOTTERIZMUS_UI_TESTS") == "1"
# Frame-by-frame checks need a display that draws at a normal rate: Broadway with our
# input client connected (it answers the frame roundtrips) or Weston.
FRAMES = os.environ.get("NOTTERIZMUS_UI_FRAMES") == "1"
BROADWAY_PORT = os.environ.get("NOTTERIZMUS_UI_BROADWAY_PORT")

if ENABLED:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Graphene", "1.0")
    from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gtk, Pango  # noqa: F401

_app = None
_keyboard = None
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
        global _keyboard
        if BROADWAY_PORT and _keyboard is None:  # before the window: it answers frame roundtrips
            from .broadway_input import BroadwayInput
            _keyboard = BroadwayInput(int(BROADWAY_PORT))
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


def real_key(name, ctrl=False, shift=False, alt=False, wait=0.15):
    """Press a key for real (Broadway): it goes to whatever has keyboard focus, through
    GTK's full event dispatch. Key names as in Gdk.keyval_from_name ("Escape", "f", "Tab")."""
    if _keyboard is None:
        raise unittest.SkipTest("real key presses need the Broadway display (the default runner)")
    if shift and len(name) == 1 and name.isalpha():
        name = name.upper()  # what the keymap gives for Shift+letter
    elif shift and name == "Tab":
        name = "ISO_Left_Tab"
    keyval = Gdk.keyval_from_name(name)
    if keyval in (0, 0xFFFFFF):
        raise ValueError(f"unknown key name {name!r}")
    _keyboard.key(keyval, ctrl=ctrl, shift=shift, alt=alt)
    pump(wait)


def real_type(text, wait=0.05):
    """Type text for real, one key per character."""
    if _keyboard is None:
        raise unittest.SkipTest("real key presses need the Broadway display (the default runner)")
    for ch in text:
        _keyboard.key(Gdk.unicode_to_keyval(ord(ch)), shift=ch.isupper())
        pump(wait)
    pump(0.1)


def surface_point(widget, x, y):
    """(x, y) in the widget -> the same point in its window's surface."""
    native = widget.get_native()
    ok, p = widget.compute_point(native, Graphene.Point().init(x, y))
    if not ok:
        raise AssertionError(f"{widget} isn't in a window")
    tx, ty = native.get_surface_transform()
    return p.x + tx, p.y + ty


def real_drag(*points, steps=6, wait=0.02, hold=False):
    """Drag with the left mouse button for real (Broadway): press at the first point, move
    through the others in small steps, release at the last (unless hold). Each point is
    (widget, x, y), resolved when the pointer gets there, or (x, y) in the window surface."""
    if _keyboard is None:
        raise unittest.SkipTest("real mouse input needs the Broadway display (the default runner)")

    def where(p):
        return surface_point(*p) if len(p) == 3 else p

    x, y = where(points[0])
    _keyboard.enter(x, y)
    _keyboard.move(x, y)
    pump(wait)
    _keyboard.button(x, y, True)
    pump(0.05)
    for p in points[1:]:
        tx, ty = where(p)
        for i in range(1, steps + 1):
            _keyboard.move(x + (tx - x) * i / steps, y + (ty - y) * i / steps)
            pump(wait)
        x, y = tx, ty
    if not hold:
        release_mouse()


def release_mouse():
    """Release the left button where the pointer is (if it's held)."""
    if _keyboard is not None and _keyboard.buttons:
        _keyboard.button(*_keyboard.pos, False)
        pump(0.1)


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
