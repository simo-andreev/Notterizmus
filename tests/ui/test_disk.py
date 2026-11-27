"""A chapter changed on disk by another program while it is open here (CR10, R16)."""
import os
from pathlib import Path

from notterizmus import backups, paths
from notterizmus.guide import h
from notterizmus.model import Document, Run

from . import support as ui


class OnDisk:
    """Helpers for a chapter open here whose file another program changes."""

    def setUp(self):
        super().setUp()
        self.path = Path(ui.open_chapter([h("Mine")], title="On disk", book="Disk").path)
        self.addCleanup(self.close_dialogs)

    def close_dialogs(self):
        while (dlg := self.win.get_visible_dialog()) is not None:
            dlg.force_close()
            ui.wait_for(lambda: self.win.get_visible_dialog() is not dlg, "a dialog to close")

    def change_on_disk(self, text="Theirs"):
        other = Document.load(self.path)
        other.root.children[0].runs = [Run(text)]
        other.save()  # a new file in its place, as sync tools write

    def on_disk(self, path=None):
        return Document.load(path or self.path).root.children[0].text

    def type(self, text):
        ui.type_text(ui.focus(self.win.doc.root.children[0]).view, text)

    def question(self):
        ui.wait_for(lambda: self.win.get_visible_dialog() is not None, "the question")
        dlg = self.win.get_visible_dialog()
        self.assertEqual(dlg.get_heading(), "Changed on Disk")
        return dlg

    def answer(self, response):
        dlg = self.question()
        dlg.emit("response", response)
        dlg.force_close()
        ui.wait_for(lambda: self.win.get_visible_dialog() is None, "the question to close")

    def earlier(self, path=None):
        from notterizmus.ui.window import notes_root
        folder = backups.folder_for(path or self.path, notes_root(), paths.backups_dir())
        return [Document.load(b.path).root.children[0].text for b in backups.list_backups(folder)]


class DiskChangeTest(OnDisk, ui.UITestCase):
    """Autosave overwrote a chapter that another program (a sync tool, a second machine)
    had changed since it was opened here (CR10 in CODE_REVIEW.md, R16)."""

    def test_a_change_on_disk_is_asked_about_and_reload_takes_that_version(self):
        self.change_on_disk()
        self.type(" typed")
        self.question()  # the autosave asks instead of writing
        self.assertEqual(self.on_disk(), "Theirs", "the other version isn't overwritten")
        self.answer("reload")
        self.assertEqual(self.win.doc.root.children[0].text, "Theirs")
        self.assertEqual(self.on_disk(), "Theirs")
        self.assertEqual(self.earlier()[0], "Mine typed", "yours is kept in Earlier Versions")
        self.ed.undo()  # and Ctrl+Z brings it back
        self.assertEqual(self.win.doc.root.children[0].text, "Mine typed")
        ui.wait_for(lambda: self.on_disk() == "Mine typed", "the autosave, without a question")
        self.assertIsNone(self.win.get_visible_dialog())

    def test_keep_mine_writes_this_version_and_keeps_the_other_in_earlier_versions(self):
        self.change_on_disk()
        self.type(" typed")
        self.answer("keep")
        self.assertEqual(self.on_disk(), "Mine typed")
        self.assertEqual(self.earlier()[0], "Theirs")
        self.type(" more")
        ui.wait_for(lambda: self.on_disk() == "Mine typed more", "the autosave, without a question")
        self.assertIsNone(self.win.get_visible_dialog())

    def test_escape_decides_nothing_and_the_next_save_asks_again(self):
        self.change_on_disk()
        self.type(" typed")
        self.answer("later")
        self.assertEqual(self.on_disk(), "Theirs")
        self.type(" more")
        self.question()
        self.assertEqual(self.on_disk(), "Theirs")

    def test_opening_another_chapter_keeps_this_version_and_the_other_in_earlier_versions(self):
        """Nothing can wait for an answer when another chapter replaces this one."""
        self.change_on_disk()
        self.type(" typed")
        ui.open_chapter([h("Elsewhere")], title="Other", book="Disk")  # before the autosave
        self.assertIsNone(self.win.get_visible_dialog())
        self.assertEqual(self.on_disk(), "Mine typed")
        self.assertEqual(self.earlier()[0], "Theirs")

    def test_a_chapter_opened_while_the_question_waits_doesnt_lose_this_version(self):
        """The question is asked by an autosave, so no autosave is waiting while it is open."""
        self.change_on_disk()
        self.type(" typed")
        self.question()
        other = ui.scratch() / "elsewhere.notz"
        Document.new("Elsewhere", 1, "Other", other).save()
        ui.app().do_open([ui.Gio.File.new_for_path(str(other))], 1, "")  # a file opened from Files
        ui.wait_for(lambda: self.win.get_visible_dialog() is None, "the question to go with its chapter")
        self.assertEqual(self.on_disk(), "Mine typed")
        self.assertEqual(self.earlier()[0], "Theirs")

    def test_reload_of_a_file_that_cannot_be_read_keeps_yours_and_says_why(self):
        """A sync tool may leave a half-written file: Reload then changes nothing here."""
        self.path.write_text("{not json", encoding="utf-8")
        self.type(" typed")
        toasts = []
        self.win.toast = lambda msg, button=None, cb=None: toasts.append(msg)
        self.addCleanup(lambda: self.win.__dict__.pop("toast", None))
        self.answer("reload")
        self.assertEqual(self.win.doc.root.children[0].text, "Mine typed")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{not json", "nothing written over it either")
        self.assertEqual(len(toasts), 1, toasts)
        self.assertTrue(toasts[0].startswith(f"Could not reload {self.path.name}"), toasts)

    def test_renaming_the_open_chapter_here_is_not_a_change_on_disk(self):
        no = self.win.doc.chapter_no
        self.win.apply_chapter_props(self.path, self.path.parent, no, "Renamed")
        ui.settle()
        self.type(" typed")
        renamed = Path(self.win.doc.path)
        self.assertNotEqual(renamed, self.path)
        ui.wait_for(lambda: self.on_disk(renamed) == "Mine typed", "the autosave, without a question")
        self.assertIsNone(self.win.get_visible_dialog())


class EarlierVersionsUnwritableTest(OnDisk, ui.UITestCase):
    """Keep Mine and Reload said the other version was in Earlier Versions even when it
    couldn't be put there, and Keep Mine then overwrote it (RV4 in PLAN.md, C4 in REVIEW.md).
    The chapter's Earlier Versions folder is read-only here."""

    def setUp(self):
        super().setUp()
        from notterizmus.ui.window import notes_root
        self.versions = backups.folder_for(self.path, notes_root(), paths.backups_dir())
        self.versions.mkdir(parents=True, exist_ok=True)
        os.chmod(self.versions, 0o555)
        self.addCleanup(os.chmod, self.versions, 0o755)
        self.toasts = []
        self.win.toast = lambda msg, button=None, cb=None: self.toasts.append(msg)
        self.addCleanup(lambda: self.win.__dict__.pop("toast", None))

    def conflict(self):
        found = sorted(self.path.parent.glob(f"{self.path.stem} (conflict *).notz"))
        self.assertEqual(len(found), 1, found)
        return found[0]

    def test_keep_mine_saves_yours_beside_the_other_and_keeps_editing_it(self):
        self.change_on_disk()
        self.type(" typed")
        self.answer("keep")
        self.assertEqual(self.on_disk(), "Theirs", "the other version isn't overwritten")
        conflict = self.conflict()
        self.assertEqual(self.on_disk(conflict), "Mine typed")
        self.assertEqual(Path(self.win.doc.path), conflict)
        self.assertTrue(any(conflict.name in t for t in self.toasts), self.toasts)
        self.assertFalse(any("is in Earlier Versions" in t for t in self.toasts), "no claim that it was kept")
        self.type(" more")
        ui.wait_for(lambda: self.on_disk(conflict) == "Mine typed more", "the autosave, into the copy")
        self.assertEqual(self.on_disk(), "Theirs")

    def test_opening_another_chapter_does_the_same_without_asking(self):
        self.change_on_disk()
        self.type(" typed")
        ui.open_chapter([h("Elsewhere")], title="Other", book="Disk")  # before the autosave
        self.assertEqual(self.on_disk(), "Theirs")
        self.assertEqual(self.on_disk(self.conflict()), "Mine typed")

    def test_reload_keeps_yours_beside_the_chapter(self):
        self.change_on_disk()
        self.type(" typed")
        self.answer("reload")
        self.assertEqual(self.win.doc.root.children[0].text, "Theirs")
        self.assertEqual(Path(self.win.doc.path), self.path, "the chapter stays the one open")
        conflict = self.conflict()
        self.assertEqual(self.on_disk(conflict), "Mine typed")
        self.assertTrue(any(conflict.name in t for t in self.toasts), self.toasts)
