import unittest

from notterizmus.find import clean_replacement, find_all


class FindTest(unittest.TestCase):
    def test_ignores_case_unless_asked(self):
        self.assertEqual(find_all("Scale scale SCALE", "scale"), [(0, 5), (6, 11), (12, 17)])
        self.assertEqual(find_all("Scale scale SCALE", "scale", case=True), [(6, 11)])

    def test_whole_words(self):
        self.assertEqual(find_all("cat concat cat's cats", "cat", whole=True), [(0, 3), (11, 14)])

    def test_cyrillic_words_and_case(self):
        text = "Код и кодът, КОД."
        self.assertEqual(find_all(text, "код"), [(0, 3), (6, 9), (13, 16)])
        self.assertEqual(find_all(text, "код", whole=True), [(0, 3), (13, 16)])

    def test_special_characters_are_literal(self):
        self.assertEqual(find_all("a.b a*b (x)", "a.b"), [(0, 3)])
        self.assertEqual(find_all("a.b a*b (x)", "(x)"), [(8, 11)])

    def test_matches_do_not_overlap(self):
        self.assertEqual(find_all("aaaa", "aa"), [(0, 2), (2, 4)])

    def test_empty_query_finds_nothing(self):
        self.assertEqual(find_all("text", ""), [])

    def test_replacement_stays_on_one_line(self):
        self.assertEqual(clean_replacement("two\nlines"), "two lines")
        self.assertEqual(clean_replacement(""), "")


if __name__ == "__main__":
    unittest.main()
