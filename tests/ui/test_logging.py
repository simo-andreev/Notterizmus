"""Failures that used to pass without a trace (RV7 in PLAN.md, REVIEW.md §4.5): Earlier
Versions that stopped being kept, settings that couldn't be written, and a chapter that
couldn't be kept anywhere at exit. Each is logged now; Earlier Versions also says so once."""
import os
from pathlib import Path

from notterizmus import backups, paths
from notterizmus.guide import h
from notterizmus.model import Document, Run

from . import support as ui


class LoggedFailuresTest(ui.UITestCase):
    def setUp(self):
        super().setUp()
        self.doc = ui.open_chapter([h("Logged")], title="Logged", book="Logged book")
        self.path = Path(self.doc.path)
        self.toasts = []
        self.win.toast = lambda msg, button=None, cb=None: self.toasts.append(msg)
        self.addCleanup(lambda: self.win.__dict__.pop("toast", None))
        self.win._versions_warned = False  # once per session: this test's session starts here

    def read_only(self, folder):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        os.chmod(folder, 0o555)
        self.addCleanup(os.chmod, folder, 0o755)

    def versions(self):
        from notterizmus.ui.window import notes_root
        return backups.folder_for(self.path, notes_root(), paths.backups_dir())

    def reopen_changed(self, text):
        """Change the chapter on disk and open it again: opening takes a copy of it."""
        doc = Document.load(self.path)
        doc.root.children[0].runs = [Run(text)]
        doc.save()
        self.win.open_path(self.path)

    def test_earlier_versions_that_cannot_be_kept_are_logged_and_said_once(self):
        for copy in self.versions().glob("*.notz"):  # taken this second: a copy in the same second is skipped
            copy.unlink()
        self.read_only(self.versions())
        with self.assertLogs("notterizmus.ui", "WARNING") as logged:
            self.reopen_changed("Second")
            self.reopen_changed("Third")
        self.assertEqual(len(logged.output), 2, "each failure is logged")
        said = [t for t in self.toasts if "Earlier Versions" in t]
        self.assertEqual(len(said), 1, self.toasts)

    def test_earlier_versions_that_cannot_follow_a_rename_are_logged_and_said(self):
        self.read_only(self.versions().parent)  # the book's versions folder
        with self.assertLogs("notterizmus.ui", "WARNING"):
            self.win.apply_chapter_props(self.path, self.path.parent, self.win.doc.chapter_no, "Renamed")
        self.assertTrue(any("Earlier Versions" in t for t in self.toasts), self.toasts)

    def test_settings_that_cannot_be_saved_are_logged(self):
        from notterizmus.ui.helpers import save_state
        self.read_only(paths.config_dir())
        with self.assertLogs("notterizmus.ui.helpers", "WARNING"):
            save_state(self.win.state)

    def test_a_chapter_that_cannot_be_kept_anywhere_at_exit_is_logged(self):
        ui.type_text(ui.focus(self.win.doc.root.children[0]).view, " typed")
        self.read_only(self.path.parent)
        self.read_only(paths.unsaved_dir())
        with self.assertLogs("notterizmus.ui.window_saving", "ERROR") as logged:
            self.win.save_for_exit()
        self.assertTrue(any(self.path.name in line for line in logged.output), logged.output)
        os.chmod(self.path.parent, 0o755)
        self.win.save_banner.emit("button-clicked")  # leave it saved for the next test
