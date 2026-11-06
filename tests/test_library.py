import tempfile
import unittest
from pathlib import Path

from notterizmus.library import find, neighbor, parse_name, scan


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, book, *names):
        d = self.root / book
        d.mkdir(parents=True, exist_ok=True)
        for n in names:
            (d / n).write_text("{}", encoding="utf-8")
        return d

    def test_parses_chapter_file_names(self):
        self.assertEqual(parse_name("03 The Title"), (3, "The Title"))
        self.assertEqual(parse_name("12"), (12, ""))
        self.assertEqual(parse_name("notes"), (None, "notes"))

    def test_books_by_name_and_chapters_by_number(self):
        self.make("Чиста архитектура", "10 Ten.notz", "2 Two.notz", "01.notz")
        self.make("clean code", "01 Intro.notz")
        books = scan(self.root)
        self.assertEqual([b.name for b in books], ["clean code", "Чиста архитектура"])
        self.assertEqual([c.label for c in books[1].chapters], ["Chapter 1", "Two", "Ten"])

    def test_skips_hidden_files_other_files_and_empty_books(self):
        self.make("Book", "01 A.notz", ".01 A.notz.tmp", ".hidden.notz", "readme.txt")
        self.make("Empty")
        self.make(".trash", "01 X.notz")
        books = scan(self.root)
        self.assertEqual([(b.name, [c.label for c in b.chapters]) for b in books], [("Book", ["A"])])

    def test_missing_root_is_empty(self):
        self.assertEqual(scan(self.root / "nope"), [])

    def test_neighbors_stay_in_the_book(self):
        d = self.make("Book", "01 A.notz", "02 B.notz", "03 C.notz")
        self.make("Other", "01 X.notz")
        books = scan(self.root)
        self.assertEqual(neighbor(books, d / "02 B.notz", 1).label, "C")
        self.assertEqual(neighbor(books, d / "02 B.notz", -1).label, "A")
        self.assertIsNone(neighbor(books, d / "03 C.notz", 1))
        self.assertIsNone(neighbor(books, d / "01 A.notz", -1))
        self.assertIsNone(neighbor(books, self.root / "elsewhere.notz", 1))

    def test_find_matches_equivalent_paths(self):
        d = self.make("Book", "01 A.notz")
        book, i = find(scan(self.root), d / ".." / "Book" / "01 A.notz")
        self.assertEqual((book.name, i), ("Book", 0))


if __name__ == "__main__":
    unittest.main()
