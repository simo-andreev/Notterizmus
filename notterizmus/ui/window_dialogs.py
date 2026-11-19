"""The window's other dialogs (CR38 in CODE_REVIEW.md): Search Commands, Earlier
Versions, Plain Text, the formatting rules and notes folder, About and Keyboard Shortcuts.

Uses the window's doc, editor, rules, toast() and _is_guide(), and WindowSaving's
_flush_save(), _backup() and _backup_folder()."""
from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk

from .. import APP_ID, APP_NAME, VERSION, backups, paths
from ..commands import SHORTCUTS, shortcut_keys
from ..export import to_plain
from ..layout import layout
from ..model import Document
from ..rules import Rules, user_rules_path
from . import command_search
from .helpers import notes_root, run_once
from .versions import VersionsDialog

RULES_TEMPLATE = Path(__file__).resolve().parent.parent / "rules.example.toml"


class WindowDialogs:
    def on_commands(self, *_):
        """Search Commands (Ctrl+Shift+P)."""
        # The search field takes the primary selection, which collapses the chapter's
        # selection; remember it so Bold, Italic and the like still apply to it.
        view = self.editor.cur_view
        sel = view.selection_offsets() if view is not None else None

        def restore():
            if view is not None and sel and view.get_root() is not None:
                view.grab_focus()
                view.select_range(*sel)
        dlg = command_search.CommandSearch(command_search.build(self), before_run=restore)
        dlg.present(self)
        GLib.idle_add(run_once, dlg.entry.grab_focus)

    def on_versions(self, *_):
        """Earlier Versions: pick a kept copy of this chapter, preview it, restore it."""
        if not self.doc or self._is_guide() or not self.doc.path:
            self.toast("Open a chapter of a book first")
            return
        self._flush_save()
        found = backups.list_backups(self._backup_folder())
        VersionsDialog(found, self.doc.path, self.rules, self.restore_version).present(self)

    def restore_version(self, path):
        """Put an earlier version's content in the editor; Ctrl+Z takes it back."""
        try:
            earlier = Document.load(path)
        except (OSError, ValueError) as e:
            self.toast(f"Could not read that version: {e}")
            return
        self._flush_save()
        self._backup(force=True)  # what you had a moment ago is kept too
        self.editor.replace_content(earlier.root)
        self.toast("Earlier version restored. Ctrl+Z takes it back.")

    def on_show_plain(self, *_):
        text = to_plain(layout(self.doc.root, self.rules))
        dlg = Adw.Dialog(title="Plain Text", content_width=900, content_height=650)
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        view = Gtk.TextView(editable=False, monospace=True, left_margin=16, right_margin=16,
                            top_margin=12, bottom_margin=12)
        view.get_buffer().set_text(text)
        sw = Gtk.ScrolledWindow(child=view, vexpand=True)
        tv.set_content(sw)
        dlg.set_child(tv)
        dlg.present(self)

    def on_edit_rules(self, *_):
        p = user_rules_path()
        if not p.exists():
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(RULES_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError as e:  # (CR27)
                self.toast(f"Could not create {p}: {e.strerror or e}")
                return
        Gtk.FileLauncher.new(Gio.File.new_for_path(str(p))).launch(self, None, None)
        self.toast("Edit, save, then use “Reload Formatting Rules”")

    def on_reload_rules(self, *_):
        self.rules = Rules.load()
        self.editor.set_rules(self.rules)
        self.toast(f"Rules error: {self.rules.error}" if self.rules.error else "Formatting rules reloaded")

    def on_open_folder(self, *_):
        root = notes_root()
        root.mkdir(parents=True, exist_ok=True)
        Gtk.FileLauncher.new(Gio.File.new_for_path(str(root))).launch(self, None, None)

    def on_about(self, *_):
        notes_version, notes = paths.latest_release(APP_ID)
        dlg = Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon=APP_ID,
            version=VERSION,
            comments="Outline editor for book chapter notes, formatted for pasting into TopCoding.",
            license_type=Gtk.License.GPL_3_0,
        )
        if notes:  # written once, in data/dev.simo.Notterizmus.metainfo.xml
            dlg.set_release_notes_version(notes_version or VERSION)
            dlg.set_release_notes(notes)
        dlg.present(self)

    def on_shortcuts(self, *_):
        trig = {v.get("label", k): (v.get("trigger", ""), v["symbol"]) for k, v in self.rules["markers"].items()}
        dlg = Adw.ShortcutsDialog()
        for title, items in SHORTCUTS:  # CR37: keys from the one command table
            sec = Adw.ShortcutsSection(title=title)
            for label, keys in items:
                sec.add(Adw.ShortcutsItem(title=label, accelerator=" ".join(shortcut_keys(keys))))
            dlg.add(sec)
        types = Adw.ShortcutsSection(title="Item type: type at the start of an item, then Space")
        types.add(Adw.ShortcutsItem(title=f"Numbered item — “{self.rules['heading']['trigger']}”", accelerator=""))
        for label, (t, sym) in trig.items():
            types.add(Adw.ShortcutsItem(title=f"{label} {sym} — “{t}”", accelerator=""))
        dlg.add(types)
        dlg.present(self)
