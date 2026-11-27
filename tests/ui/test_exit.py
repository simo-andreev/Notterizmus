"""Saving when the app is ended rather than closed, and while typing never pauses (RV3 in
PLAN.md, C3 in REVIEW.md): a logout, a shutdown or a signal dropped the waiting autosave,
and an autosave restarted its 800 ms wait on every change, for as long as typing went on."""
import os
import signal
from pathlib import Path

from notterizmus import paths
from notterizmus.guide import h
from notterizmus.model import Document

from . import support as ui


class ExitTest(ui.UITestCase):
    def setUp(self):
        super().setUp()
        self.doc = ui.open_chapter([h("Intro")], title="Exit", book="Exit book")
        self.path = Path(self.doc.path)
        self.addCleanup(lambda: os.chmod(self.path.parent, 0o755))
        self.quits = []
        self.app.quit = lambda: self.quits.append(True)  # the shared app stays
        self.addCleanup(lambda: self.app.__dict__.pop("quit", None))

    def on_disk(self):
        return Document.load(self.path).root.children[0].text

    def type(self, text, wait=0.05):
        ui.type_text(ui.focus(self.win.doc.root.children[0]).view, text, wait)

    def due_in(self):
        """Seconds until the waiting autosave runs: 0 once it has."""
        if self.win._save_src is None:
            return 0.0
        src = ui.GLib.MainContext.default().find_source_by_id(self.win._save_src)
        return (src.get_ready_time() - ui.GLib.get_monotonic_time()) / 1e6

    def test_an_autosave_waits_no_longer_than_the_maximum_while_typing_goes_on(self):
        from notterizmus.ui import window_saving  # here: the unit suite runs without PyGObject too
        clock = [1000.0]
        self.addCleanup(setattr, window_saving, "_now", window_saving._now)
        window_saving._now = lambda: clock[0]
        self.type("x")  # the first change not yet saved
        clock[0] += 0.3
        self.type("x")
        self.assertGreater(self.due_in(), 0.5, "a change puts the autosave off")
        clock[0] += window_saving.SAVE_MAX_WAIT
        self.type("x")
        self.assertLess(self.due_in(), 0.1, "but not past the maximum wait")
        ui.wait_for(lambda: self.on_disk() == "Introxxx", "the autosave")

    def test_sigterm_saves_and_quits(self):
        self.type(" typed")
        os.kill(os.getpid(), signal.SIGTERM)
        ui.wait_for(lambda: self.quits, "the app to quit")
        self.assertEqual(self.on_disk(), "Intro typed")

    def test_the_session_ending_saves_without_quitting(self):
        self.type(" typed")
        self.assertTrue(self.app.get_property("register-session"), "the session manager knows the app")
        self.app.emit("query-end")
        self.assertEqual(self.on_disk(), "Intro typed")
        self.assertEqual(self.quits, [])

    def test_when_the_chapter_cannot_be_saved_at_exit_it_is_written_aside(self):
        self.type(" typed")
        os.chmod(self.path.parent, 0o555)
        self.win.save_for_exit()
        aside = sorted((paths.unsaved_dir() / self.path.parent.name).glob(f"{self.path.stem} *.notz"))
        self.assertEqual([Document.load(p).root.children[0].text for p in aside], ["Intro typed"])
        self.assertIsNone(self.win.get_visible_dialog(), "nothing is asked: no one may be there to answer")
        os.chmod(self.path.parent, 0o755)
        self.win.save_banner.emit("button-clicked")  # leave it saved for the next test
