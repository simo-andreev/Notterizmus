import tempfile
import unittest
from pathlib import Path

from notterizmus.library import (find, neighbor, parse_name, rename_book, renumber, reorder, safe_name, scan,
                                 set_chapter)
from notterizmus.model import Document, Node, chapter_filename


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



class ChangeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def chapter(self, book, number, title, text=None):
        doc = Document(Node("root", children=[Node("heading")]), book, number, title,
                       self.root / safe_name(book) / chapter_filename(number, title))
        doc.root.children[0].runs = []
        if text:
            from notterizmus.model import Run
            doc.root.children[0].runs = [Run(text)]
        doc.save()
        return doc.path

    def state(self, book="Book"):
        """[(file name, number, title, book, text)] of a book folder."""
        out = []
        for f in sorted((self.root / safe_name(book)).glob("*.notz")):
            d = Document.load(f)
            out.append((f.name, d.chapter_no, d.chapter_title, d.book, d.root.children[0].text))
        return out

    def test_rename_keeps_the_content(self):
        p = self.chapter("Book", 1, "Old", "notes")
        moved = set_chapter(p, 1, "New")
        self.assertEqual(self.state(), [("01 New.notz", 1, "New", "Book", "notes")])
        self.assertEqual(moved, {p: self.root / "Book" / "01 New.notz"})

    def test_a_taken_number_swaps_within_the_book(self):
        a = self.chapter("Book", 1, "A", "a")
        self.chapter("Book", 2, "B", "b")
        moved = set_chapter(a, 2, "A")
        self.assertEqual(self.state(), [("01 B.notz", 1, "B", "Book", "b"), ("02 A.notz", 2, "A", "Book", "a")])
        self.assertEqual(moved[a], self.root / "Book" / "02 A.notz")
        self.assertEqual(moved[self.root / "Book" / "02 B.notz"], self.root / "Book" / "01 B.notz")

    def test_moving_to_another_book_takes_its_name_and_refuses_a_taken_number(self):
        a = self.chapter("Book", 1, "A", "a")
        self.chapter("Other / Two", 1, "X")
        with self.assertRaises(FileExistsError):
            set_chapter(a, 1, "A", self.root / safe_name("Other / Two"))
        set_chapter(a, 4, "A", self.root / safe_name("Other / Two"))
        self.assertEqual(self.state("Other / Two")[1], ("04 A.notz", 4, "A", "Other / Two", "a"))
        self.assertEqual(self.state(), [])

    def test_reorder_hands_out_the_existing_numbers(self):
        a = self.chapter("Book", 1, "A")
        b = self.chapter("Book", 2, "B")
        c = self.chapter("Book", 5, "C")
        reorder([ch for p in (c, a, b) for ch in scan(self.root)[0].chapters if ch.path == p])
        self.assertEqual([(n, t) for _f, n, t, _b, _x in self.state()], [(1, "C"), (2, "A"), (5, "B")])
        self.assertEqual([f for f, *_ in self.state()], ["01 C.notz", "02 A.notz", "05 B.notz"])

    def test_renumber_puts_everything_back_if_a_file_is_in_the_way(self):
        a = self.chapter("Book", 1, "A", "a")
        self.chapter("Book", 3, "A")  # "03 A.notz" blocks moving A to 3
        before = self.state()
        with self.assertRaises(FileExistsError):
            renumber({a: 3})
        self.assertEqual(self.state(), before)
        self.assertEqual([f.name for f in (self.root / "Book").iterdir() if f.name.startswith(".")], [])

    def test_rename_book_renames_the_folder_and_the_stored_name(self):
        self.chapter("Old", 1, "A", "a")
        self.chapter("Old", 2, "B")
        self.chapter("Taken", 1, "X")
        with self.assertRaises(FileExistsError):
            rename_book(self.root / "Old", "taken")
        moved = rename_book(self.root / "Old", "New: a/b")
        self.assertFalse((self.root / "Old").exists())
        self.assertEqual([(f, b) for f, _n, _t, b, _x in self.state("New: a/b")],
                         [("01 A.notz", "New: a/b"), ("02 B.notz", "New: a/b")])
        self.assertEqual(moved[self.root / "Old" / "01 A.notz"], self.root / "New: a_b" / "01 A.notz")

    def test_changing_only_the_case_of_a_book_name_is_allowed(self):
        self.chapter("book", 1, "A")
        rename_book(self.root / "book", "Book")
        self.assertEqual([d.name for d in self.root.iterdir()], ["Book"])


if __name__ == "__main__":
    unittest.main()
