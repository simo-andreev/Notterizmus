"""The app's log: warnings to stderr, which reaches the journal (RV7 in PLAN.md)."""
import io
import logging
import unittest

from notterizmus import logs


class LogsTest(unittest.TestCase):
    def setUp(self):
        root = logging.getLogger("notterizmus")
        saved = root.level, root.handlers[:], root.propagate
        self.addCleanup(lambda: (setattr(root, "level", saved[0]), setattr(root, "handlers", saved[1]),
                                 setattr(root, "propagate", saved[2])))

    def test_warnings_go_to_stderr_with_the_module_named(self):
        out = io.StringIO()
        logs.setup({}, stream=out)
        logging.getLogger("notterizmus.backups").warning("can't copy %s", "x")
        logging.getLogger("notterizmus.backups").info("not shown")
        self.assertEqual(out.getvalue(), "notterizmus.backups: WARNING: can't copy x\n")

    def test_notterizmus_debug_shows_everything(self):
        out = io.StringIO()
        logs.setup({"NOTTERIZMUS_DEBUG": "1"}, stream=out)
        logging.getLogger("notterizmus.drawing").debug("pruned")
        self.assertIn("pruned", out.getvalue())

    def test_setting_up_twice_adds_no_second_handler(self):
        out = io.StringIO()
        logs.setup({}, stream=out)
        logs.setup({}, stream=out)
        logging.getLogger("notterizmus.x").warning("once")
        self.assertEqual(out.getvalue().count("once"), 1)
