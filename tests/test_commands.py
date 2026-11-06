import unittest

from notterizmus.commands import Command, search

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


if __name__ == "__main__":
    unittest.main()
