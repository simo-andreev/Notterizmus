"""Excalidraw inside the app: the drawing window, and previews of drawings.

Excalidraw runs in a WebKitGTK view on the page built into notterizmus/drawing_web (see
web/drawing and scripts/build-drawing-editor.sh). The page is served from those files
through a URI scheme of the app's own and may not reach the network.

The rest of the app uses only edit(), render() and available(); the UI tests replace
them, so nothing else here may be imported elsewhere.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path

import gi
from gi.repository import Adw, Gio, GLib, Gtk

from .. import drawing

try:
    gi.require_version("WebKit", "6.0")
    from gi.repository import WebKit
except (ValueError, ImportError):  # the typelib (gir1.2-webkit-6.0) isn't installed
    WebKit = None

SCHEME = "notterizmus-draw"
PAGE = f"{SCHEME}://app/index.html"
WEB_DIR = Path(__file__).resolve().parents[1] / "drawing_web"
MISSING = "Drawings need WebKitGTK: install the package gir1.2-webkit-6.0"
RENDER_TIMEOUT = 30    # seconds for one preview
IDLE_CLOSE = 60        # seconds the hidden preview page is kept after its last job

# Waits for the page's script, then calls into it (see web/drawing/main.jsx).
_JS_READY = "while (!window.ntz) { await new Promise((r) => setTimeout(r, 20)); }\n"
_JS_OPEN = _JS_READY + "return await window.ntz.open(JSON.parse(scene), JSON.parse(options));"
_JS_SAVE = _JS_READY + "return await window.ntz.save();"
_JS_CHANGED = _JS_READY + "return window.ntz.changed();"
_JS_RENDER = _JS_READY + "return await window.ntz.render(JSON.parse(scene), JSON.parse(options));"

# The web context of every page here. It is the module's own, not WebKit's default: a C exit
# handler frees the default one after Python has stopped, and that also frees the URI
# scheme handler below, a Python function, so the app crashed as it quit.
_context = None


def available():
    return WebKit is not None and (WEB_DIR / "index.html").is_file()


def _serve(request):
    """Answer a request for one of the page's files."""
    rel = (request.get_path() or "/").lstrip("/") or "index.html"
    path = (WEB_DIR / rel).resolve()
    try:
        if WEB_DIR not in path.parents or not path.is_file():
            raise FileNotFoundError(rel)
        data = path.read_bytes()
    except OSError:
        request.finish_error(GLib.Error.new_literal(Gio.io_error_quark(), f"no such file: {rel}",
                                                    Gio.IOErrorEnum.NOT_FOUND))
        return
    mime = {".js": "text/javascript", ".woff2": "font/woff2"}.get(path.suffix) \
        or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    request.finish(Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data)), len(data), mime)


def _new_view():
    global _context
    if _context is None:
        _context = WebKit.WebContext.new()
        _context.register_uri_scheme(SCHEME, _serve)
        security = _context.get_security_manager()
        security.register_uri_scheme_as_secure(SCHEME)
        security.register_uri_scheme_as_cors_enabled(SCHEME)
    # Ephemeral: the page keeps nothing on disk (the drawing lives in the chapter file).
    view = WebKit.WebView(web_context=_context, network_session=WebKit.NetworkSession.new_ephemeral())
    settings = view.get_settings()
    settings.set_javascript_can_access_clipboard(True)
    debug = bool(os.environ.get("NOTTERIZMUS_WEB_DEBUG"))
    settings.set_enable_developer_extras(debug)
    settings.set_enable_write_console_messages_to_stdout(debug)
    view.connect("decide-policy", _decide_policy)
    view.connect("context-menu", lambda *_: True)  # Excalidraw has its own
    view.ntz_loaded = False
    view.ntz_waiting = []
    view.connect("load-changed", _load_changed)
    view.connect("load-failed", _load_failed)
    view.load_uri(PAGE)
    return view


def _decide_policy(_view, decision, kind):
    """The view shows the drawing page and nothing else: links in it go nowhere."""
    if kind in (WebKit.PolicyDecisionType.NAVIGATION_ACTION, WebKit.PolicyDecisionType.NEW_WINDOW_ACTION):
        uri = decision.get_navigation_action().get_request().get_uri() or ""
        if not uri.startswith(f"{SCHEME}://app/"):
            decision.ignore()
            return True
    return False


def _call(view, body, done, **args):
    """Run an async JavaScript function body in the page; done(value, error) gets its
    result as text (or None and the error message); args are passed as text. Waits for the page to have loaded:
    a call made before that is dropped by WebKit when the page arrives."""
    if not view.ntz_loaded:
        view.ntz_waiting.append((body, done, args))
        return
    variant = GLib.Variant("a{sv}", {k: GLib.Variant("s", v) for k, v in args.items()})

    def finished(v, res):
        try:
            value = v.call_async_javascript_function_finish(res)
        except GLib.Error as e:
            done(None, e.message)
            return
        done(value.to_string(), None)

    view.call_async_javascript_function(body, -1, variant, None, None, None, finished)


def _load_changed(view, event):
    if event == WebKit.LoadEvent.FINISHED and not view.ntz_loaded:
        view.ntz_loaded = True
        waiting, view.ntz_waiting = view.ntz_waiting, []
        for body, done, args in waiting:
            _call(view, body, done, **args)


def _load_failed(view, _event, _uri, error):
    waiting, view.ntz_waiting = view.ntz_waiting, []
    for _body, done, _args in waiting:
        done(None, error.message)
    return False


def _page_options(**more):
    """Options for the page's open() and render(): `preview` is the largest preview PNG."""
    return json.dumps({"preview": list(drawing.PREVIEW_PIXELS), **more})


def _shot(reply):
    """(png bytes, width, height) from the page's answer."""
    return base64.b64decode(reply.get("png") or ""), int(reply.get("width") or 0), int(reply.get("height") or 0)


# --- previews --------------------------------------------------------------------

class _Renderer:
    """Makes previews on a page that is never shown, one drawing at a time."""

    def __init__(self):
        self.view = None
        self.jobs = []
        self.busy = False
        self._timeout = None
        self._idle = None

    def render(self, data, done):
        self.jobs.append((data, done))
        self._next()

    def _next(self):
        if self.busy or not self.jobs:
            return
        if self._idle is not None:
            GLib.source_remove(self._idle)
            self._idle = None
        if self.view is None:
            self.view = _new_view()
            self.view.connect("web-process-terminated", lambda *_: self._finish(None))
        self.busy = True
        data, _done = self.jobs[0]
        self._timeout = GLib.timeout_add_seconds(RENDER_TIMEOUT, self._timed_out)
        _call(self.view, _JS_RENDER, self._rendered, scene=drawing.scene_json(data), options=_page_options())

    def _rendered(self, text, error):
        png = None
        if error is None:
            try:
                png = _shot(json.loads(text))[0] or None
            except (ValueError, TypeError, AttributeError):
                png = None
        self._finish(png)

    def _timed_out(self):
        self._timeout = None
        self._finish(None, reset=True)
        return False

    def _finish(self, png, reset=False):
        if not self.busy:
            return
        self.busy = False
        if self._timeout is not None:
            GLib.source_remove(self._timeout)
            self._timeout = None
        data, done = self.jobs.pop(0)
        if png is None or reset:
            self.view = None  # start from a fresh page next time
        if png:
            drawing.store_preview(data, png)
        done(png)
        if self.jobs:
            self._next()
        elif self.view is not None:
            self._idle = GLib.timeout_add_seconds(IDLE_CLOSE, self._close_idle)

    def _close_idle(self):
        self._idle = None
        if not self.busy:
            self.view = None
        return False


_renderer = _Renderer()


def render(data, done):
    """Make the preview PNG of a drawing and put it in the cache; done(png bytes or None)
    is called later, from the main loop."""
    if not available() or drawing.is_empty(data):
        GLib.idle_add(lambda: (done(None), False)[1])
        return
    _renderer.render(data, done)


# --- the drawing window --------------------------------------------------------------

class DrawingWindow(Adw.Window):
    """Excalidraw on one drawing. Done hands the scene back; Cancel (or closing the window)
    drops the changes, after asking if there are any."""

    def __init__(self, parent, data, on_done):
        w, h = (parent.get_width(), parent.get_height()) if parent is not None else (0, 0)
        super().__init__(transient_for=parent, modal=True, title="Drawing",
                         default_width=max(w - 80, 900), default_height=max(h - 60, 640))
        self._on_done = on_done
        self._closing = False
        self._ready = False
        self.view = _new_view()
        self.view.set_vexpand(True)
        self._crash_handler = self.view.connect("web-process-terminated", self._crashed)
        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        header.pack_start(cancel)
        self.done_btn = Gtk.Button(label="Done", sensitive=False, tooltip_text="Keep the drawing")
        self.done_btn.add_css_class("suggested-action")
        self.done_btn.connect("clicked", lambda _b: self.finish())
        header.pack_end(self.done_btn)
        tv = Adw.ToolbarView()
        tv.add_top_bar(header)
        self.toasts = Adw.ToastOverlay(child=self.view)
        tv.set_content(self.toasts)
        self.set_content(tv)
        self.connect("close-request", self._close_request)
        dark = Adw.StyleManager.get_default().get_dark()
        _call(self.view, _JS_OPEN, self._opened, scene=drawing.scene_json(data),
              options=_page_options(dark=dark))

    def _opened(self, _text, error):
        if self.view is None:  # closed meanwhile
            return
        if error is not None:
            self.toasts.add_toast(Adw.Toast(title=f"The drawing editor didn't start: {error}", timeout=0))
            return
        self._ready = True
        self.done_btn.set_sensitive(True)
        self.view.grab_focus()

    def _crashed(self, *_):
        self._ready = False
        self.done_btn.set_sensitive(False)
        self.toasts.add_toast(Adw.Toast(title="The drawing editor stopped working. Cancel and open it again.",
                                        timeout=0))

    def finish(self):
        """Done: take the scene and its preview from the page, then close."""
        self.done_btn.set_sensitive(False)
        _call(self.view, _JS_SAVE, self._saved)

    def _saved(self, text, error):
        if self.view is None:  # closed meanwhile
            return
        try:
            if error is not None:
                raise ValueError(error)
            reply = json.loads(text)
            data = drawing.decode(reply["scene"])
            png = _shot(reply)[0]
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            self.done_btn.set_sensitive(True)
            self.toasts.add_toast(Adw.Toast(title=f"The drawing couldn't be read: {e}"))
            return
        if png:
            drawing.store_preview(data, png)
        self._closing = True
        self.close()
        self._on_done(data)

    def _close_request(self, _w):
        if self._closing or not self._ready:  # nothing to lose before the editor is up
            self._release()
            return False
        _call(self.view, _JS_CHANGED, self._ask_discard)
        return True

    def _release(self):
        """The window is going. End its web process now: WebKit keeps it until the view
        is freed. Then drop the window's widgets. The handlers on its buttons hold the
        window, and that cycle runs through GTK, where Python's garbage collector can't
        see it. GTK hides a closed window without disposing of it, which would have
        broken the cycle, so without this the window and everything in it would stay
        until the app quits. The window also keeps its focus widget after the widget
        is taken out, which would keep the content alive, so focus is cleared first."""
        if self.view is None:
            return
        view, self.view = self.view, None
        view.disconnect(self._crash_handler)  # ending it on purpose isn't a crash
        view.terminate_web_process()
        self.set_focus(None)
        self.set_content(None)
        self.toasts = self.done_btn = None

    def _ask_discard(self, text, error):
        if self.view is None:  # closed meanwhile
            return
        if error is not None or text != "true":
            self._closing = True
            self.close()
            return
        dlg = Adw.AlertDialog(heading="Discard Changes?", body="The changes to this drawing will be lost.")
        dlg.add_response("keep", "Keep Editing")
        dlg.add_response("discard", "Discard")
        dlg.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("keep")
        dlg.set_close_response("keep")

        def answered(_d, response):
            if response == "discard":
                self._closing = True
                self.close()

        dlg.connect("response", answered)
        dlg.present(self)


def shutdown():
    """Let go of the hidden preview page (and with it WebKit's helper processes)."""
    _renderer.jobs.clear()
    _renderer.busy = False
    for source in (_renderer._timeout, _renderer._idle):
        if source is not None:
            GLib.source_remove(source)
    _renderer._timeout = _renderer._idle = None
    _renderer.view = None


def edit(parent, data, on_done):
    """Open the drawing window on a scene; on_done(new data) is called if the user keeps
    it. Returns the window, or None if drawings can't be edited here."""
    if not available():
        return None
    win = DrawingWindow(parent, data, on_done)
    win.present()
    return win
