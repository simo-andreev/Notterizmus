from __future__ import annotations

import os
import sys
from pathlib import Path

from .. import gpu

gpu.prefer_gpu()  # before GTK loads: GTK and WebKit read what it sets once, at the start

from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gtk  # noqa: E402  (their versions: __init__.py)

from .. import APP_ID, APP_NAME  # noqa: E402
from . import drawing_web  # noqa: E402
from .window import Window  # noqa: E402

CSS = Path(__file__).with_name("style.css")
ICONS = Path(__file__).resolve().parents[2] / "data" / "icons"


def use_hinted_text(settings):
    """GTK's "automatic" font rendering draws text unhinted, so a thin horizontal stroke
    that falls between two pixel rows is drawn half-bright on each and almost vanishes:
    the top bar of "=" looked like "-". With "manual", GTK follows the desktop's own
    hinting setting (Ubuntu's default is slight) and rounds glyph metrics to whole pixels.
    A desktop already on "manual" is left as it is."""
    if settings.get_property("gtk-font-rendering") == Gtk.FontRendering.AUTOMATIC:
        settings.set_property("gtk-font-rendering", Gtk.FontRendering.MANUAL)
        settings.set_property("gtk-hint-font-metrics", True)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        GLib.set_application_name(APP_NAME)
        self.win = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        prov = Gtk.CssProvider()
        prov.load_from_path(str(CSS))
        display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(display, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        use_hinted_text(Gtk.Settings.get_default())
        # icon works straight from the checkout; install.sh also puts it in the user icon theme
        Gtk.IconTheme.get_for_display(display).add_search_path(str(ICONS))
        Gtk.Window.set_default_icon_name(APP_ID)
        for action, accels in (("win.new", ["<Ctrl>n"]), ("win.open", ["<Ctrl>o"]), ("win.save", ["<Ctrl>s"]),
                               ("win.copy", ["<Ctrl><Shift>c"]), ("win.shortcuts", ["<Ctrl>question"]),
                               ("win.guide", ["F1"]), ("win.sidebar", ["F9"]), ("win.rename", ["F2"]),
                               ("win.commands", ["<Ctrl><Shift>p"]),
                               ("win.zoom-in", ["<Ctrl>equal", "<Ctrl>plus", "<Ctrl>KP_Add"]),
                               ("win.zoom-out", ["<Ctrl>minus", "<Ctrl>KP_Subtract"]),
                               ("win.zoom-reset", ["<Ctrl>0", "<Ctrl>KP_0"]),
                               ("win.find", ["<Ctrl>f"]), ("win.replace", ["<Ctrl>h", "<Ctrl>r"]),
                               ("win.find-next", ["<Ctrl>g"]), ("win.find-prev", ["<Ctrl><Shift>g"]),
                               ("win.prev-chapter", ["<Ctrl>Page_Up"]), ("win.next-chapter", ["<Ctrl>Page_Down"]),
                               ):
            self.set_accels_for_action(action, accels)
        q = Gio.SimpleAction.new("quit", None)
        q.connect("activate", lambda *_: self.win.close() if self.win else self.quit())
        self.add_action(q)
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])

    def do_shutdown(self):
        drawing_web.shutdown()  # the hidden preview page, and WebKit's processes with it
        Adw.Application.do_shutdown(self)

    def do_activate(self):
        if not self.win:
            self.win = Window(self)
        self.win.present()
        snap = os.environ.get("NOTTERIZMUS_SNAPSHOT")
        if snap:
            GLib.timeout_add(1500, self._snapshot, snap)

    def do_open(self, files, _n, _hint):
        self.do_activate()
        if not files:
            return
        drawing = self.win.editor.drawing_window()
        if drawing is not None:  # the drawing would go back into the other chapter (CR19)
            drawing.present()
            toasts = getattr(drawing, "toasts", None)
            if toasts is not None:
                toasts.add_toast(Adw.Toast(title=f"{files[0].get_basename()} wasn't opened: finish the drawing first",
                                           use_markup=False))
            return
        path = files[0].get_path()
        if path is None:  # not a file on this computer (CR27)
            self.win.toast(f"{files[0].get_basename() or files[0].get_uri()} isn't on this computer, so it can't be opened")
            return
        self.win.open_path(path)

    def _snapshot(self, path):
        """Debug helper: render the window content to a PNG and quit."""
        w = self.win.get_content()
        paintable = Gtk.WidgetPaintable.new(w)
        snap = Gtk.Snapshot()
        bg = Gdk.RGBA()
        bg.parse("#222226" if Adw.StyleManager.get_default().get_dark() else "#fafafb")
        snap.append_color(bg, Graphene.Rect().init(0, 0, w.get_width(), w.get_height()))
        paintable.snapshot(snap, w.get_width(), w.get_height())
        node = snap.to_node()
        if node:
            tex = self.win.get_renderer().render_texture(node, None)
            tex.save_to_png(path)
        self.quit()
        return False


def main():
    return App().run(sys.argv)
