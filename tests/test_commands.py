import re
import unittest
from pathlib import Path

from notterizmus.commands import COMMANDS, SHORTCUTS, Command, command, key_label, search, shortcut_keys

ROOT = Path(__file__).resolve().parents[1]

CMDS = [
    Command("New Chapter", accel="<Control>n", order=0),
    Command("Chapter Properties…", keywords="rename number move book", order=1),
    Command("Earlier Versions…", keywords="backup restore history undo", order=2),
    Command("Copy for TopCoding", keywords="export html paste", order=3),
    Command("Move Item Up", section="Item", order=4),
    Command("Spelling Language: Bulgarian", keywords="dictionary", order=5),
]


def titles(query):
    return [c.title for c in search(query, CMDS)]


class CommandsTest(unittest.TestCase):
    def test_nothing_typed_lists_everything_in_order(self):
        self.assertEqual(titles(""), [c.title for c in CMDS])

    def test_title_start_ranks_first(self):
        self.assertEqual(titles("chap")[0], "Chapter Properties…")
        self.assertEqual(titles("new")[0], "New Chapter")

    def test_every_word_must_match_in_any_order(self):
        self.assertEqual(titles("up move"), ["Move Item Up"])
        self.assertEqual(titles("move zzz"), [])

    def test_keywords_find_commands_after_title_matches(self):
        self.assertEqual(titles("rename"), ["Chapter Properties…"])
        self.assertEqual(titles("backup"), ["Earlier Versions…"])
        self.assertEqual(titles("move")[0], "Move Item Up")  # title before keywords
        self.assertIn("Chapter Properties…", titles("move"))

    def test_case_and_alphabet(self):
        self.assertEqual(titles("TOPCODING"), ["Copy for TopCoding"])
        self.assertEqual(titles("bulg"), ["Spelling Language: Bulgarian"])


class RankingTest(unittest.TestCase):
    def test_a_word_at_the_start_of_the_title_beats_one_further_in(self):
        cmds = [Command("Show Chapter List"), Command("Chapter Properties…")]
        self.assertEqual([c.title for c in search("chap", cmds)], ["Chapter Properties…", "Show Chapter List"])

    def test_a_word_start_beats_a_match_inside_a_word(self):
        cmds = [Command("Unindent Item"), Command("Indent Item")]
        self.assertEqual([c.title for c in search("indent", cmds)], ["Indent Item", "Unindent Item"])

    def test_the_shorter_title_wins_a_tie_and_then_the_list_order(self):
        cmds = [Command("Find and Replace"), Command("Find"), Command("Find Next"), Command("Find Prev")]
        self.assertEqual([c.title for c in search("find", cmds)], ["Find", "Find Next", "Find Prev", "Find and Replace"])

    def test_the_section_name_finds_its_commands(self):
        cmds = [Command("Bold", section="Text"), Command("Larger Text"), Command("Save", section="Chapter")]
        self.assertEqual([c.title for c in search("text", cmds)], ["Larger Text", "Bold"])

    def test_keywords_match_from_the_start_of_a_word_only(self):
        cmds = [Command("Earlier Versions…", keywords="backup restore history")]
        self.assertEqual(search("story", cmds), [])
        self.assertEqual(len(search("hist", cmds)), 1)

    def test_dots_and_slashes_in_titles_do_not_get_in_the_way(self):
        cmds = [Command("Open Chapter…"), Command("Cut/Copy Items")]
        self.assertEqual([c.title for c in search("chapter", cmds)], ["Open Chapter…"])
        self.assertEqual([c.title for c in search("copy", cmds)], ["Cut/Copy Items"])

    def test_spaces_around_what_is_typed_do_not_matter(self):
        self.assertEqual(titles("  new   chap  "), ["New Chapter"])
        self.assertEqual(titles("   "), [c.title for c in CMDS])

    def test_cyrillic_and_other_case_rules(self):
        cmds = [Command("Език: Български"), Command("STRASSE")]
        self.assertEqual([c.title for c in search("БЪЛГ", cmds)], ["Език: Български"])
        self.assertEqual([c.title for c in search("straße", cmds)], ["STRASSE"])


if __name__ == "__main__":
    unittest.main()


def in_text(label, text):
    """label written in text as a whole key: "Ctrl+S" is not found in "Ctrl+Shift+Z"."""
    return re.search(r"(?<![\w+])" + re.escape(label) + r"(?![\w])", text) is not None


def table_keys():
    """Every key the command table and the Shortcuts dialog show, as accelerators."""
    keys = {c.key for c in COMMANDS if c.key}
    for _section, items in SHORTCUTS:
        for _label, ks in items:
            keys.update(shortcut_keys(ks))
    return keys


# Keys README.md describes in words instead: the multi-cursor gesture, and the Menu key as
# right-click.
DESCRIBED = {"<Ctrl>Up", "<Ctrl>Down", "Menu"}


class TableTest(unittest.TestCase):
    """CR37: one command table; README.md and the guide are checked against it."""

    def test_every_key_is_in_the_readme(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        missing = sorted(key_label(k) for k in table_keys() - DESCRIBED if not in_text(key_label(k), readme))
        self.assertEqual(missing, [], "keys of the command table missing from README.md")

    def test_whole_key_match(self):
        self.assertTrue(in_text("Ctrl+S", "save: Ctrl+S."))
        self.assertFalse(in_text("Ctrl+S", "Ctrl+Shift+Z"))
        self.assertFalse(in_text("Ctrl+Z", "Ctrl+Shift+Z"))

    def test_key_labels(self):
        self.assertEqual(key_label("<Ctrl><Shift>p"), "Ctrl+Shift+P")
        self.assertEqual(key_label("<Shift><Control>z"), "Ctrl+Shift+Z")
        self.assertEqual(key_label("<Alt>Up"), "Alt+↑")
        self.assertEqual(key_label("<Ctrl>Page_Down"), "Ctrl+PgDn")
        self.assertEqual(key_label("<Ctrl>question"), "Ctrl+?")
        self.assertEqual(key_label("F2"), "F2")

    def test_every_shortcut_names_a_command(self):
        for _section, items in SHORTCUTS:
            for _label, ks in items:
                self.assertTrue(all(shortcut_keys(ks)), ks)

    def test_each_key_belongs_to_one_command(self):
        seen = {}
        for c in COMMANDS:
            for k in c.accels or (c.shown,) if c.key else ():
                self.assertNotIn(k, seen, f"{k}: {seen.get(k)} and {c.title}")
                seen[k] = c.title

    def test_commands_are_found_by_action(self):
        self.assertEqual(command("win.find").title, "Find")
        self.assertEqual(command("ed.add", "next").key, "<Ctrl>Return")
