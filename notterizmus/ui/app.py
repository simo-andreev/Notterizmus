from __future__ import annotations

import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from .. import APP_ID, APP_NAME  # noqa: E402
from .window import Window  # noqa: E402

CSS = Path(__file__).with_name("style.css")
ICONS = Path(__file__).resolve().parents[2] / "data" / "icons"


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
        # icon works straight from the checkout; install.sh also puts it in the user icon theme
        Gtk.IconTheme.get_for_display(display).add_search_path(str(ICONS))
        Gtk.Window.set_default_icon_name(APP_ID)
        for action, accels in (("win.new", ["<Ctrl>n"]), ("win.open", ["<Ctrl>o"]), ("win.save", ["<Ctrl>s"]),
                               ("win.copy", ["<Ctrl><Shift>c"]), ("win.shortcuts", ["<Ctrl>question"]),
                               ("win.guide", ["F1"]), ("win.sidebar", ["F9"]), ("win.rename", ["F2"]),
                               ("win.commands", ["<Ctrl><Shift>p"]),
                               ("win.prev-chapter", ["<Ctrl>Page_Up"]), ("win.next-chapter", ["<Ctrl>Page_Down"]),
                               ):
            self.set_accels_for_action(action, accels)
        q = Gio.SimpleAction.new("quit", None)
        q.connect("activate", lambda *_: self.win.close() if self.win else self.quit())
        self.add_action(q)
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])

    def do_activate(self):
        if not self.win:
            self.win = Window(self)
        self.win.present()
        snap = os.environ.get("NOTTERIZMUS_SNAPSHOT")
        if snap:
            GLib.timeout_add(1500, self._snapshot, snap)

    def do_open(self, files, _n, _hint):
        self.do_activate()
        if files:
            self.win.open_path(files[0].get_path())

    def _snapshot(self, path):
        """Debug helper: render the window content to a PNG and quit."""
        w = self.win.get_content()
        paintable = Gtk.WidgetPaintable.new(w)
        snap = Gtk.Snapshot()
        from gi.repository import Graphene
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
