"""Helpers for the GTK UI tests: drive the real app with key presses and check what it draws.

Run the tests with scripts/ui-tests.sh. It starts a private Broadway display (no window
appears on your screen), points the config, data and Documents folders at a scratch
directory and fails if GTK or Python printed any warnings. A plain
`python3 -m unittest discover -s tests -t .` skips these tests.

Waiting: the app does much of its work a moment later (focus in an idle callback, layout
in the next frames, input through the display server), so nothing here assumes how long
that takes. The helpers wait for what they started: press(), type_text() and focus() until
the editor has put the cursor where it wants it, real_key() and real_drag() until the
app has received the input, settle() until the outline has stopped moving. In a test,
wait for a condition with wait_for(), settle() or frames() rather than for a time with
pump(); a fixed pause passes on a fast machine and fails on a busy one, and
tests/test_ui_waits.py fails on one (CR50).

Every test starts from the same window state (UITestCase.setUp), fails if the app raised
an exception in one of its callbacks (GTK only prints those), and is stopped with a
traceback if it hangs.

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

import collections
import faulthandler
import itertools
import os
import sys
import time
import traceback
import unittest
from pathlib import Path

ENABLED = os.environ.get("NOTTERIZMUS_UI_TESTS") == "1"
# Frame-by-frame checks need a display that draws at a normal rate: Broadway with our
# input client connected (it answers the frame roundtrips) or Weston.
FRAMES = os.environ.get("NOTTERIZMUS_UI_FRAMES") == "1"
# The Broadway server's socket for input (real keys and mouse); unset on Weston.
BROADWAY = os.environ.get("NOTTERIZMUS_UI_BROADWAY")
REAL_INPUT = bool(BROADWAY)
# A test that takes longer than this is hung: the run stops with every thread's traceback.
TEST_TIMEOUT = float(os.environ.get("NOTTERIZMUS_UI_TEST_TIMEOUT", "180"))

_INPUT_EVENTS = ()

if ENABLED:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Graphene", "1.0")
    from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gtk, Pango  # noqa: F401

    _INPUT_EVENTS = (Gdk.EventType.KEY_PRESS, Gdk.EventType.BUTTON_PRESS, Gdk.EventType.BUTTON_RELEASE,
                     Gdk.EventType.MOTION_NOTIFY)

_app = None
_keyboard = None
_chapter_no = collections.defaultdict(lambda: itertools.count(1))  # the next chapter number, per book
_app_errors = []  # exceptions the app raised in callbacks since the current test began
# Real input: the time stamp of the newest event the app has received, and how far the
# stamps the app sees are from the ones sent (see _watch_input).
_input = {"seen": 0, "offset": 0, "pressed": 0.0}


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
        if BROADWAY and _keyboard is None:  # before the window: it answers frame roundtrips
            from .broadway_input import BroadwayInput
            _keyboard = BroadwayInput(BROADWAY)
        _watch_exceptions()
        a = App()
        a.set_flags(a.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
        a.register(None)
        a.activate()
        _app = a
        _watch_input(a.win)
        if not pump_until(lambda: a.win.get_mapped() and a.win.get_width() > 0, 15):
            raise RuntimeError("the app's window never appeared on the test display")
        pump(0.5)
        if _keyboard is not None:
            # Broadway hands events on with their time stamps moved by a fixed amount:
            # measure it with one pointer movement, the only input so far.
            _keyboard.enter(5, 5)
            stamp = _keyboard.move(5, 5)
            if not pump_until(lambda: _input["seen"], 15):
                raise RuntimeError("real input sent through Broadway doesn't reach the app")
            _input["offset"] = stamp - _input["seen"]
    return _app


def _watch_exceptions():
    """PyGObject prints an exception raised in a signal handler, idle or timeout callback
    and carries on, so the test that caused it would pass. Collect them instead."""
    printed = sys.excepthook

    def hook(etype, value, tb):
        _app_errors.append("".join(traceback.format_exception(etype, value, tb)))
        printed(etype, value, tb)

    sys.excepthook = hook


def _watch_input(widget):
    """Note the time stamp of each real key press and pointer event as `widget` receives
    it, before any widget inside can take it: real_key() and real_drag() wait for the
    stamps of the events they sent (broadway_input.send), so they know the app has
    handled them. Watched on the window and, while they are open, on its dialog and
    popups (_watch_modals): those get the events first-hand, and the window never sees
    them."""
    widget._input_watched = True
    ctl = Gtk.EventControllerLegacy(propagation_phase=Gtk.PropagationPhase.CAPTURE)

    def event(ctl, _event):
        ev = ctl.get_current_event()  # PyGObject passes the signal's own event as None
        if ev is not None and ev.get_event_type() in _INPUT_EVENTS:
            _input["seen"] = max(_input["seen"], ev.get_time())
        return False

    ctl.connect("event", event)
    widget.add_controller(ctl)


def _arrived(stamp, what):
    """Wait until the app has received the real input event sent with this time stamp.
    It has then handled it as well: an event is dispatched in one go."""
    wait_for(lambda: _input["seen"] + _input["offset"] >= stamp, f"{what} to reach the app")


class UITestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENABLED:
            raise unittest.SkipTest("UI tests run with scripts/ui-tests.sh")
        cls.app = app()
        cls.win = cls.app.win
        cls.ed = cls.win.editor

    def setUp(self):
        """Subclasses that define setUp must call this first (super().setUp())."""
        faulthandler.dump_traceback_later(TEST_TIMEOUT, exit=True)
        self.addCleanup(faulthandler.cancel_dump_traceback_later)
        reset_window()
        del _app_errors[:]
        self.addCleanup(self._no_app_errors)

    def _no_app_errors(self):
        pump(0.05)  # what the test left for the main loop still counts as its own
        errors, _app_errors[:] = list(_app_errors), []
        if errors:
            self.fail(f"the app raised {len(errors)} exception(s) in its callbacks during this test; "
                      "the first:\n" + errors[0])


def reset_window():
    """Bring the window back to the state every test starts from, whatever the test before
    left behind: no dialog, popup, find bar, selection, extra cursors or held mouse
    button; normal text size; the chapter list shown at its default width."""
    win = app().win
    ed = win.editor
    release_mouse()
    while (dlg := win.get_visible_dialog()) is not None:
        dlg.force_close()
        wait_for(lambda: win.get_visible_dialog() is not dlg, "a dialog to close")
    close_popovers()
    if win.findbar.get_search_mode():
        win.findbar.set_search_mode(False)
    ed.clear_carets()
    ed.clear_selection()
    if win._zoom != 100:
        win.set_zoom(100, save=True, announce=False)
    if not win.split.get_show_sidebar():
        win.split.set_show_sidebar(True)
    if win._sidebar_w != 260:
        win.set_sidebar_width(260, save=True)


# -- main loop --------------------------------------------------------------------------

def pump(seconds=0.1):
    ctx = GLib.MainContext.default()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.003)


def pump_until(cond, timeout=10.0):
    """Run the main loop until cond() is true; False if it still isn't after timeout
    seconds (generous, since it only matters when something is wrong or the machine busy)."""
    if _keyboard is not None:
        _keyboard._check()  # without the display nothing is drawn: say so rather than time out
    ctx = GLib.MainContext.default()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        if cond():
            return True
        time.sleep(0.003)
    return bool(cond())


def wait_for(cond, what="the expected state", timeout=10.0):
    """pump_until() that fails the test when the condition never comes."""
    if not pump_until(cond, timeout):
        raise AssertionError(f"timed out after {timeout:g} s waiting for {what}")


def child_processes():
    """{pid: name} of the processes this one started, and theirs (WebKit's and its sandboxes)."""
    procs = {}
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                stat = Path(f"/proc/{d}/stat").read_text()
            except OSError:
                continue
            procs[int(d)] = (int(stat[stat.rindex(")") + 2:].split()[1]), stat[stat.index("(") + 1:stat.rindex(")")])
    me = os.getpid()

    def ours(pid):
        for _ in range(20):
            pid = procs.get(pid, (0, ""))[0]
            if pid == me:
                return True
            if pid <= 1:
                return False
        return False

    return {pid: name for pid, (_parent, name) in procs.items() if pid != me and ours(pid)}


def web_processes():
    """How many WebKit web processes (one per page) the app has running."""
    return sum(1 for name in child_processes().values() if name.startswith("WebKitWebProc"))


def _editor_busy():
    """True while the editor still has the cursor to place or to scroll to."""
    ed = app().win.editor
    return ed._focus_hint is not None or ed._focus_wait is not None or ed._ensure_tick is not None


def wait_editor(pause=0.03):
    """After something that changes the outline: let the editor finish what it deferred
    (it focuses the new item from an idle callback, then scrolls to the cursor)."""
    pump(pause)
    pump_until(lambda: not _editor_busy())


# -- chapters -----------------------------------------------------------------------------

def open_chapter(nodes, title="Test", book="Book"):
    """Save a chapter with these top-level nodes in the scratch notes folder and open it.
    It gets the next number in its book (the default book has well over a hundred by the
    end of a run: a chapter number isn't always two digits)."""
    from notterizmus.model import Document, Node, chapter_filename
    from notterizmus.ui.window import notes_root
    win = app().win
    no = next(_chapter_no[book])
    doc = Document(Node("root", children=nodes), book, no, title,
                   notes_root() / book / chapter_filename(no, title), lang="en_US")
    doc.save()
    win.open_path(doc.path)
    settle()
    return win.doc


def _geometry():
    """Where every row of the outline is drawn and how tall it is, and the scroll position."""
    ed = app().win.editor
    out = [round(ed.get_vadjustment().get_value())]
    c = ed.box.get_first_child()
    while c is not None:
        p = point_in(c, ed.box)
        out.append((round(p[1]) if p else None, c.get_height()))
        c = c.get_next_sibling()
    return out


def settle(extra=0.05, frames=4, timeout=10.0):
    """Wait until the outline is laid out and still: every text view has a real width,
    the cursor is where the editor wants it, and no row has moved or changed height over
    several frames in a row. (Rows are measured again 20-30 ms after they're added, and
    once more when their text turns out to wrap differently, each a frame or two apart.)"""
    win = app().win
    ed = win.editor
    pump(0.06)  # past the editor's own short timers
    state = {"last": None, "same": 0}

    def painted(_clock):
        now = _geometry() if not _editor_busy() and all(v.get_width() > 1 for v in ed.all_views()) else None
        state["same"] = state["same"] + 1 if now is not None and now == state["last"] else 0
        state["last"] = now

    clock = win.get_frame_clock()
    hid = clock.connect("after-paint", painted)
    tick = ed.add_tick_callback(lambda *_: True)  # keep frames coming while we watch
    try:
        pump_until(lambda: state["same"] >= frames, timeout)
    finally:
        clock.disconnect(hid)
        ed.remove_tick_callback(tick)
    pump(extra)


def frames(n=3, timeout=10.0):
    """Wait until n more frames have been painted: the layout of a change just made (a
    width, a widget shown) is done then, where no state says so, and a check that nothing
    changed has given it the chance to."""
    win = app().win
    count = [0]
    clock = win.get_frame_clock()
    hid = clock.connect("after-paint", lambda _clock: count.__setitem__(0, count[0] + 1))
    tick = win.add_tick_callback(lambda *_: True)  # keep frames coming while we count
    try:
        pump_until(lambda: count[0] >= n, timeout)
    finally:
        clock.disconnect(hid)
        win.remove_tick_callback(tick)


def row(node):
    return app().win.editor.rows[node.id]


def focus(node, offset=-1):
    r = row(node)
    r.focus(offset)
    wait_editor(0.05)
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
    wait_editor(wait)
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
    _press(keyval, ctrl=ctrl, shift=shift, alt=alt)
    wait_editor(wait)


def _press(keyval, **mods):
    """Press one real key and wait until the app has handled the press."""
    _keys_to_window()
    _watch_modals()
    _arrived(_keyboard.key(keyval, **mods), "a real key press")


def _keys_to_window():
    """Make sure Broadway sends real keys to the app's window. The server sends a key to
    the surface it last gave keyboard focus, which only a mouse press, a modal window or a
    present() changes. A window of our own that was presented and then destroyed (one
    with no transient parent, as test_drawings.EvenSizeTest makes) keeps the focus after
    it is gone, and every key after it reached nothing until a real click. So when the
    window isn't active and no other window of ours is open to take the keys, it asks for
    the focus again, as the app does when it starts (gdk_toplevel_focus)."""
    win = app().win
    if win.is_active() or any(w is not win and w.get_visible() for w in Gtk.Window.list_toplevels()):
        return
    win.present()
    wait_for(win.is_active, "the window to get the keyboard back")


def _watch_modals():
    """Before sending real input: also watch for it on the dialog and popups open now."""
    for w in [app().win.get_visible_dialog(), *open_popovers()]:
        if w is not None and not getattr(w, "_input_watched", False):
            _watch_input(w)


def real_type(text, wait=0.05):
    """Type text for real, one key per character. wait=0 sends the keys without letting
    the app run in between, as a fast typist's arrive: together with the key after them."""
    if _keyboard is None:
        raise unittest.SkipTest("real key presses need the Broadway display (the default runner)")
    _keys_to_window()
    _watch_modals()
    for ch in text:
        if wait:
            _press(Gdk.unicode_to_keyval(ord(ch)), shift=ch.isupper())
            pump(wait)
        else:
            _keyboard.key(Gdk.unicode_to_keyval(ord(ch)), shift=ch.isupper())
    if wait:
        wait_editor(0.05)


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

    def move(px, py):
        _arrived(_keyboard.move(px, py), "the pointer movement")
        pump(wait)

    _watch_modals()
    x, y = where(points[0])
    _keyboard.enter(x, y)
    move(x, y)
    _arrived(_keyboard.button(x, y, True), "the mouse button press")
    _input["pressed"] = time.monotonic()  # GTK's double-click timer started by now
    pump(0.05)
    for p in points[1:]:
        tx, ty = where(p)  # resolved now: the outline may have scrolled under the drag
        for i in range(1, steps + 1):
            move(x + (tx - x) * i / steps, y + (ty - y) * i / steps)
        x, y = tx, ty
    if not hold:
        release_mouse()


def past_double_click():
    """Wait until a press is a click of its own, not the second of a double click: GTK
    counts a press within its double-click time (gtk-double-click-time) of the one before
    together with it. Only what is left of that time since the last real press."""
    ms = Gtk.Settings.get_default().get_property("gtk-double-click-time")
    wait_for(lambda: time.monotonic() - _input["pressed"] >= ms / 1000, "the double-click time to pass")
    pump_until(lambda: True)  # and GTK's timer, due by now, has run


def release_mouse():
    """Release the left button where the pointer is (if it's held)."""
    if _keyboard is not None and _keyboard.buttons:
        _watch_modals()
        _arrived(_keyboard.button(*_keyboard.pos, False), "the mouse button release")
        pump(0.05)


def type_text(view, text, wait=0.05):
    view.grab_focus()
    view.get_buffer().insert_interactive_at_cursor(text, -1, True)
    wait_editor(wait)


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


def chapter_rows():
    """[(label, path, selected)] of the chapter rows the sidebar shows; a chapter row's
    last label is its title."""
    return [([w for w in walk(r) if isinstance(w, Gtk.Label)][-1].get_text(), r._path, r.is_selected())
            for r in app().win.sidebar.rows() if r._path is not None]


def open_popovers():
    return [w for w in walk(app().win) if isinstance(w, Gtk.Popover) and w.get_visible()]


def close_popovers():
    pops = open_popovers()
    for p in pops:
        p.popdown()
    if pops:
        pump_until(lambda: not open_popovers())
        pump(0.05)  # the app's menus unparent themselves from an idle callback


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
    wait_for(lambda: box, f"the clipboard's {mime}")
    if "error" in box:
        raise AssertionError(f"clipboard read failed: {box['error']}")
    return box["text"]


def scratch():
    return Path(os.environ["NOTTERIZMUS_UI_SCRATCH"])
