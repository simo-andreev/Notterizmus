"""The window's remembered state, state.json (CR22 in CODE_REVIEW.md): a broken file can't
stop the app from starting."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from notterizmus import state


class StateTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "notterizmus" / "state.json"
        self.path.parent.mkdir()

    def load(self, text):
        self.path.write_text(text, encoding="utf-8")
        return state.load(self.path)

    def test_a_good_file_is_read_as_it_is(self):
        st = {"last_file": "/n/01 A.notz", "last_book": "B", "spell_lang": "en_US", "spell": True,
              "sidebar": False, "sidebar_width": 260, "zoom": 120, "from a newer version": [1]}
        self.assertEqual(self.load(json.dumps(st)), st)

    def test_a_file_that_is_not_an_object_gives_the_defaults(self):
        for text in ("[]", "5", '"x"', "null", '{"zoom": 1', "", "\xff"):
            with self.subTest(text=text):
                self.assertEqual(self.load(text), {})
        self.assertEqual(state.load(self.path.with_name("missing.json")), {})

    def test_a_value_of_the_wrong_kind_gives_that_setting_its_default(self):
        """Window.__init__ raised on these, and the app didn't start."""
        self.assertEqual(self.load('{"zoom": "big", "last_file": 5, "sidebar": "yes", "spell": 1, '
                                   '"sidebar_width": true, "last_book": "kept"}'), {"last_book": "kept"})

    def test_saving_replaces_the_file_in_one_step(self):
        state.save({"zoom": 110}, self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"zoom": 110})
        with mock.patch("os.replace", side_effect=OSError(28, "No space left on device")), \
                self.assertRaises(OSError):
            state.save({"zoom": 200}, self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"zoom": 110}, "the old file stays")
        self.assertEqual(sorted(os.listdir(self.path.parent)), ["state.json"])


if __name__ == "__main__":
    unittest.main()
