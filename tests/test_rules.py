"""Formatting rules: numbering formats, the defaults and a user's rules.toml on top of them."""
import copy
import tempfile
import tomllib
import unittest
from pathlib import Path

from notterizmus import rules
from notterizmus.rules import DEFAULTS, FORMATS, Rules

ROOT = Path(__file__).resolve().parents[1]


class NumberingTest(unittest.TestCase):
    def test_roman_numerals_up_to_twelve_are_single_characters(self):
        self.assertEqual("".join(FORMATS["roman_upper"](n) for n in range(1, 13)), "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ")
        self.assertEqual("".join(FORMATS["roman_lower"](n) for n in range(1, 13)), "ⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹⅺⅻ")
        for n in range(1, 13):
            self.assertEqual(len(FORMATS["roman_upper"](n)), 1)

    def test_larger_roman_numerals_are_composed(self):
        expected = {13: "ⅩⅢ", 14: "ⅩⅣ", 19: "ⅩⅨ", 20: "ⅩⅩ", 21: "ⅩⅩⅠ", 39: "ⅩⅩⅩⅨ", 40: "ⅩⅬ", 49: "ⅩⅬⅨ",
                    50: "Ⅼ", 90: "ⅩⅭ", 99: "ⅩⅭⅨ", 100: "Ⅽ", 400: "ⅭⅮ", 1994: "ⅯⅭⅯⅩⅭⅣ"}
        for n, numeral in expected.items():
            self.assertEqual(FORMATS["roman_upper"](n), numeral, n)
        self.assertEqual(FORMATS["roman_lower"](14), "ⅹⅳ")
        self.assertEqual(FORMATS["roman_lower"](1994), "ⅿⅽⅿⅹⅽⅳ")

    def test_letters_continue_after_z(self):
        self.assertEqual([FORMATS["alpha_lower"](n) for n in (1, 26, 27, 52, 53, 702, 703)],
                         ["a", "z", "aa", "az", "ba", "zz", "aaa"])
        self.assertEqual(FORMATS["alpha_upper"](28), "AB")

    def test_labels_use_one_format_per_depth_and_repeat_the_last(self):
        r = Rules()
        self.assertEqual(r.label([2]), "Ⅱ)")
        self.assertEqual(r.label([2, 10, 3, 4]), "Ⅱ.10.c.ⅳ)")
        self.assertEqual(r.label([1, 2, 3, 4, 5, 6]), "Ⅰ.2.c.ⅳ.ⅴ.ⅵ)", "deeper levels use the last format")

    def test_separator_suffix_and_levels_can_be_changed(self):
        r = Rules()
        r.data["numbering"].update(levels=["arabic"], separator="-", suffix=".")
        self.assertEqual(r.label([3, 4, 5]), "3-4-5.")
        r.data["numbering"]["levels"] = ["alpha_upper", "no_such_format"]
        self.assertEqual(r.label([2, 7]), "B-7.", "an unknown format falls back to plain numbers")


class MarkersTest(unittest.TestCase):
    def test_default_markers_and_their_typing_triggers(self):
        r = Rules()
        self.assertEqual([r.marker_symbol(m) for m in ("dot", "plus", "minus", "important", "question")],
                         ["•", "+", "-", "!", "?"])
        self.assertEqual(r.triggers(), {"#": ("heading", None), "*": ("bullet", "dot"),
                                        "+": ("bullet", "plus"), "-": ("bullet", "minus"),
                                        "!": ("bullet", "important"), "?": ("bullet", "question")})

    def test_an_unknown_marker_is_shown_as_a_plain_bullet(self):
        self.assertEqual(Rules().marker_symbol("from-a-newer-version"), "•")

    def test_a_marker_without_a_trigger_cannot_be_typed(self):
        r = Rules()
        r.data["markers"]["idea"] = {"symbol": "→", "label": "Idea"}
        r.data["markers"]["plus"]["trigger"] = ""
        self.assertEqual(set(r.triggers()), {"#", "*", "-", "!", "?"})
        self.assertEqual(r.marker_symbol("idea"), "→")

    def test_each_rules_object_has_its_own_copy_of_the_defaults(self):
        before = copy.deepcopy(DEFAULTS)
        r = Rules()
        r.data["numbering"]["suffix"] = "."
        r.data["markers"]["dot"]["symbol"] = "*"
        r.data["numbering"]["levels"].append("arabic")
        self.assertEqual(DEFAULTS, before)
        self.assertEqual(Rules().label([1]), "Ⅰ)")


class LoadTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "rules.toml"

    def load(self, text):
        self.path.write_text(text, encoding="utf-8")
        return Rules.load(self.path)

    def test_without_a_file_the_defaults_apply(self):
        r = Rules.load(self.path)
        self.assertIsNone(r.error)
        self.assertEqual(r.data, DEFAULTS)

    def test_a_file_changes_only_what_it_names(self):
        r = self.load('[numbering]\nsuffix = "."\n[tree]\nspacer_lines = false\n')
        self.assertIsNone(r.error)
        self.assertEqual(r.label([1, 2]), "Ⅰ.2.")
        self.assertFalse(r["tree"]["spacer_lines"])
        self.assertEqual(r["numbering"]["levels"], DEFAULTS["numbering"]["levels"])
        self.assertEqual(r["tree"]["branch"], "├ ")
        self.assertEqual(r["markers"], DEFAULTS["markers"])

    def test_your_own_marker_is_added_to_the_built_in_ones(self):
        r = self.load('[markers.idea]\nsymbol = "→"\ntrigger = ">"\nlabel = "Idea"\n')
        self.assertEqual(list(r["markers"]), ["dot", "plus", "minus", "important", "question", "idea"])
        self.assertEqual(r.triggers()[">"], ("bullet", "idea"))
        self.assertEqual(r.marker_symbol("idea"), "→")

    def test_a_question_marker_from_an_older_rules_file_changes_the_built_in_one(self):
        # Before 1.6 the template suggested [markers.question]; it is now built in.
        r = self.load('[markers.question]\nsymbol = "?"\ntrigger = "?"\nlabel = "Open question"\n')
        self.assertEqual(list(r["markers"]), ["dot", "plus", "minus", "important", "question"])
        self.assertEqual(r["markers"]["question"], {"symbol": "?", "trigger": "?", "label": "Open question"})

    def test_changing_one_field_of_a_built_in_marker_keeps_the_others(self):
        r = self.load('[markers.dot]\nsymbol = "→"\n')
        self.assertEqual(r["markers"]["dot"], {"symbol": "→", "trigger": "*", "label": "Bullet"})

    def test_loading_never_changes_the_defaults(self):
        before = copy.deepcopy(DEFAULTS)
        self.load('[numbering]\nlevels = ["arabic"]\n[markers.dot]\nsymbol = "→"\n[markers.x]\nsymbol = "x"\n')
        self.assertEqual(DEFAULTS, before)

    def test_a_file_that_is_not_toml_is_reported_and_the_defaults_apply(self):
        r = self.load("this is not toml")
        self.assertIn("rules.toml", r.error)
        self.assertEqual(r.data, DEFAULTS)

    def test_the_example_in_a_report_is_written_as_toml(self):
        self.assertIn("such as false", self.load("[numbering]\nbold_label = 1\n").error)
        self.assertIn('such as "."', self.load("[numbering]\nseparator = 1\n").error)

    def test_a_file_with_the_wrong_shape_is_reported_and_the_defaults_apply(self):
        # Each of these used to stop the app from starting, or from drawing a chapter.
        for text in ('[markers]\nstar = "★"\n',            # a marker must be a table
                     "numbering = 5\n",                     # so must a section
                     "[numbering]\nlevels = []\n",          # at least one level
                     '[numbering]\nlevels = "arabic"\n',    # a list, not one name
                     '[markers.q]\nlabel = "No symbol"\n',  # a marker needs its symbol
                     "[bullets]\nindent = \"wide\"\n",      # a number
                     "[tree]\nspacer_lines = 1\n",          # true or false
                     '[heading]\ntrigger = 7\n'):
            with self.subTest(text=text):
                r = self.load(text)
                self.assertTrue(r.error, "the mistake is reported")
                self.assertIn("rules.toml", r.error)
                self.assertEqual(r.data, DEFAULTS, "and nothing of the file is used")
                self.assertEqual(r.label([1, 2]), "Ⅰ.2)")

    def test_settings_this_version_does_not_know_are_kept(self):
        r = self.load('[numbering]\nfuture = "x"\n[drawings]\nscale = 2\n')
        self.assertIsNone(r.error)
        self.assertEqual(r["numbering"]["future"], "x")
        self.assertEqual(r["drawings"], {"scale": 2})

    def test_an_unreadable_file_is_reported(self):
        self.path.mkdir()  # a folder where the file should be
        r = Rules.load(self.path)
        self.assertTrue(r.error)
        self.assertEqual(r.data, DEFAULTS)

    def test_the_users_file_is_in_the_config_folder(self):
        import os
        saved = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = "/cfg"
        try:
            self.assertEqual(rules.user_rules_path(), Path("/cfg/notterizmus/rules.toml"))
        finally:
            if saved is None:
                del os.environ["XDG_CONFIG_HOME"]
            else:
                os.environ["XDG_CONFIG_HOME"] = saved


class ExampleFileTest(unittest.TestCase):
    """rules.example.toml is what "Edit Formatting Rules" hands the user to start from."""

    def test_the_example_spells_out_exactly_the_defaults(self):
        with open(ROOT / "notterizmus" / "rules.example.toml", "rb") as f:
            self.assertEqual(tomllib.load(f), DEFAULTS)

    def test_the_example_loads_without_complaint(self):
        r = Rules.load(ROOT / "notterizmus" / "rules.example.toml")
        self.assertIsNone(r.error)
        self.assertEqual(r.data, DEFAULTS)


if __name__ == "__main__":
    unittest.main()
