"""Closing the window when the chapter can't be saved (RV1 in PLAN.md, C1 in REVIEW.md):
it used to close anyway, and everything typed since the last save that worked was lost."""
import errno
import os
from pathlib import Path

from notterizmus import paths
from notterizmus.guide import h
from notterizmus.model import Document

from . import support as ui


class UnsavedOnCloseTest(ui.UITestCase):
    def setUp(self):
        super().setUp()
        self.doc = ui.open_chapter([h("Intro")], title="Read-only", book="Read-only book")
        self.path = Path(self.doc.path)
        self.folder = self.path.parent
        self.addCleanup(self.writable)
        self.closed = []
        self.win._close_now = lambda: self.closed.append(True)  # the shared window stays
        self.addCleanup(lambda: self.win.__dict__.pop("_close_now", None))
        self.addCleanup(self.close_dialogs)

    def writable(self, on=True):
        os.chmod(self.folder, 0o755 if on else 0o555)

    def close_dialogs(self):
        while (dlg := self.win.get_visible_dialog()) is not None:
            dlg.force_close()
            ui.wait_for(lambda: self.win.get_visible_dialog() is not dlg, "a dialog to close")

    def type(self, text):
        ui.type_text(ui.focus(self.win.doc.root.children[0]).view, text)

    def on_disk(self):
        return Document.load(self.path).root.children[0].text

    def aside(self):
        """The texts of the copies written aside for this chapter, oldest first."""
        folder = paths.unsaved_dir() / self.folder.name
        return [Document.load(p).root.children[0].text
                for p in sorted(folder.glob(f"{self.path.stem} *.notz"))]

    def question(self):
        ui.wait_for(lambda: self.win.get_visible_dialog() is not None, "the question")
        dlg = self.win.get_visible_dialog()
        self.assertEqual(dlg.get_heading(), "Not Saved")
        return dlg

    def answer(self, response):
        dlg = self.question()
        dlg.emit("response", response)
        dlg.force_close()
        ui.wait_for(lambda: self.win.get_visible_dialog() is not dlg, "the question to close")

    def close_unsaved(self):
        """Type, make the book folder read-only, and close: the last save fails."""
        self.type(" typed")
        self.writable(False)
        self.assertTrue(self.win._on_close(), "the window stays open")

    def test_a_failed_save_keeps_the_window_open_and_writes_the_edits_aside(self):
        self.close_unsaved()
        dlg = self.question()
        self.assertIn(str(paths.unsaved_dir()), dlg.get_body(), "it says where the copy is")
        self.assertEqual(self.closed, [])
        self.assertEqual(self.on_disk(), "Intro")
        self.assertEqual(self.aside(), ["Intro typed"])

    def test_retry_saves_and_closes_once_the_folder_can_be_written(self):
        self.close_unsaved()
        self.writable()
        self.answer("retry")
        self.assertEqual(self.on_disk(), "Intro typed")
        self.assertEqual(self.closed, [True])

    def test_a_retry_that_fails_again_asks_again(self):
        self.close_unsaved()
        self.answer("retry")
        self.question()
        self.assertEqual(self.closed, [])
        self.assertEqual(self.on_disk(), "Intro")

    def test_quit_without_saving_closes_and_the_copy_aside_stays(self):
        self.close_unsaved()
        self.answer("discard")
        self.assertEqual(self.closed, [True])
        self.assertEqual(self.on_disk(), "Intro")
        self.assertEqual(self.aside(), ["Intro typed"])

    def test_keep_open_closes_nothing_and_autosave_carries_on(self):
        self.close_unsaved()
        self.answer("cancel")
        self.assertIsNone(self.win.get_visible_dialog())
        self.writable()
        self.type(" more")
        ui.wait_for(lambda: self.on_disk() == "Intro typed more", "the autosave")
        self.assertEqual(self.closed, [])

    def test_save_a_copy_writes_the_chapter_there_and_closes(self):
        self.close_unsaved()
        copy = Path(os.environ["NOTTERIZMUS_UI_SCRATCH"]) / "Saved elsewhere.notz"
        self.addCleanup(lambda: copy.unlink(missing_ok=True))
        self.win._save_copy_to(copy)
        self.assertEqual(Document.load(copy).root.children[0].text, "Intro typed")
        self.assertEqual(self.closed, [True])

    def test_closing_again_while_asked_shows_the_same_question(self):
        self.close_unsaved()
        dlg = self.question()
        self.assertTrue(self.win._on_close())
        ui.frames(3)
        self.assertIs(self.win.get_visible_dialog(), dlg)
        self.assertEqual(len(self.aside()), 1, "one copy aside, not one per try")

    def test_a_save_that_works_closes_as_before(self):
        self.type(" typed")
        self.assertFalse(self.win._on_close())
        self.assertEqual(self.on_disk(), "Intro typed")
        self.assertIsNone(self.win.get_visible_dialog())
        self.assertEqual(self.aside(), [])


class FailedAutosaveTest(ui.UITestCase):
    """A failed autosave was a 3-second toast naming a hidden temporary file, and nothing
    else (RV2 in PLAN.md, C2 in REVIEW.md); opening another chapter then dropped the edits
    without a word (RV34)."""

    def setUp(self):
        super().setUp()
        self.doc = ui.open_chapter([h("Intro")], title="Banner", book="Banner book")
        self.path = Path(self.doc.path)
        self.folder = self.path.parent
        self.addCleanup(lambda: os.chmod(self.folder, 0o755))
        self.toasts = []
        self.win.toast = lambda msg, button=None, cb=None: self.toasts.append(msg)
        self.addCleanup(lambda: self.win.__dict__.pop("toast", None))

    def on_disk(self, path=None):
        return Document.load(path or self.path).root.children[0].text

    def fail_autosave(self):
        """Make the book folder read-only and type: the autosave fails."""
        os.chmod(self.folder, 0o555)
        ui.type_text(ui.focus(self.win.doc.root.children[0]).view, " typed")
        ui.wait_for(lambda: self.win.save_banner.get_revealed(), "the banner")

    def test_a_failed_autosave_shows_a_banner_and_marks_the_title(self):
        self.fail_autosave()
        title = self.win.save_banner.get_title()
        self.assertIn("“Banner”", title)
        self.assertIn(os.strerror(errno.EACCES), title, "the reason, in words")
        self.assertNotIn(".tmp", title, "not the temporary file's name")
        self.assertTrue(self.win.wtitle.get_title().startswith("• "))
        self.assertTrue(self.win.get_title().startswith("• "))
        self.assertEqual(self.toasts, [], "the banner says it; no toast as well")

    def test_retry_saves_and_the_banner_and_the_mark_go(self):
        self.fail_autosave()
        os.chmod(self.folder, 0o755)
        self.win.save_banner.emit("button-clicked")
        self.assertEqual(self.on_disk(), "Intro typed")
        self.assertFalse(self.win.save_banner.get_revealed())
        self.assertFalse(self.win.wtitle.get_title().startswith("•"))
        self.assertFalse(self.win.get_title().startswith("•"))

    def test_it_retries_by_itself(self):
        self.fail_autosave()
        os.chmod(self.folder, 0o755)
        ui.wait_for(lambda: not self.win.save_banner.get_revealed(), "a retry that works", timeout=15)
        self.assertEqual(self.on_disk(), "Intro typed")

