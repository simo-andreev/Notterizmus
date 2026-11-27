"""The GTK user interface. Every module here loads GTK, so the versions of the libraries
they import are declared here, once, before any of them is imported. Otherwise a module
imported on its own, by a test or a script, leaves PyGObject to pick a version, and it
warns (CR42 in CODE_REVIEW.md). A library newly imported from gi.repository needs a line
here (tests/test_gi_versions.py checks), except GLib, GObject and Gio, which need none,
and WebKit, which drawing_web.py loads only where it is installed."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
gi.require_version("Graphene", "1.0")
gi.require_version("GLibUnix", "2.0")
