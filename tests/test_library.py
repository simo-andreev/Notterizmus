import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from notterizmus.library import (find, neighbor, parse_name, rename_book, renumber, reorder, restore_stranded,
                                 safe_name, scan, set_chapter, stranded)
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



class ChaptersCase(unittest.TestCase):
    """Chapters saved in a temporary notes folder."""

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


class ChangeTest(ChaptersCase):
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


class NamesTest(unittest.TestCase):
    def test_numbers_and_titles_in_file_names(self):
        self.assertEqual(parse_name("  7   Spaced  title "), (7, "Spaced  title"))
        self.assertEqual(parse_name("007 Bond"), (7, "Bond"))
        self.assertEqual(parse_name("3rd chapter"), (None, "3rd chapter"), "the number must stand alone")
        self.assertEqual(parse_name("12.5 x"), (None, "12.5 x"))

    def test_what_the_list_shows_for_a_chapter(self):
        from notterizmus.library import Chapter
        self.assertEqual(Chapter(4, "Title", Path("/b/04 Title.notz")).label, "Title")
        self.assertEqual(Chapter(4, "", Path("/b/04.notz")).label, "Chapter 4")
        self.assertEqual(Chapter(None, "", Path("/b/notes.notz")).label, "notes")

    def test_book_names_as_folder_names(self):
        self.assertEqual(safe_name(" a/b\\c "), "a_b_c")
        self.assertEqual(safe_name("Чиста архитектура"), "Чиста архитектура")
        self.assertEqual(safe_name("   "), "Unsorted")
        self.assertEqual(safe_name(""), "Unsorted")

    def test_a_book_name_never_becomes_a_hidden_folder_or_leaves_the_notes_folder(self):
        """".NET in Action" became a hidden folder the list skips, and the books "." and ".."
        put chapters loose in the notes folder or in Documents (CR7)."""
        self.assertEqual(safe_name(".NET in Action"), "_NET in Action")
        for name in (".", "..", " .. "):
            self.assertEqual(safe_name(name), "Unsorted")
        self.assertEqual(safe_name("..."), "_..")
        self.assertEqual(safe_name("a.b"), "a.b")

    def test_long_names_fit_the_file_name_limit(self):
        """A file name has at most 255 bytes, so New Chapter failed for a title of about 128
        Cyrillic letters (CR15). The name is shortened; the title inside stays whole."""
        title = "Архитектура " * 20  # 240 letters, 460 bytes
        for number in (7, 100):
            name = chapter_filename(number, title)
            self.assertLessEqual(len(name.encode()), 255)
            shown = parse_name(name[:-len(".notz")])
            self.assertEqual(shown[0], number)
            self.assertTrue(title.startswith(shown[1]))
        self.assertLessEqual(len(safe_name("Книга " * 60).encode()), 255)
        self.assertEqual(chapter_filename(7, "short"), "07 short.notz", "short names are as they were")

    def test_a_chapter_file_name_round_trips_through_the_list(self):
        for number, title in ((1, "Intro"), (12, "Чиста архитектура"), (7, ""), (3, "a: b? c!"), (100, "x")):
            name = chapter_filename(number, title)
            self.assertEqual(parse_name(name[:-len(".notz")]), (number, title))


class ScanOrderTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def make(self, book, *names):
        d = self.root / book
        d.mkdir(parents=True, exist_ok=True)
        for n in names:
            (d / n).write_text("{}", encoding="utf-8")
        return d

    def test_unnumbered_files_come_last_and_equal_numbers_sort_by_title(self):
        self.make("Book", "notes.notz", "02 b.notz", "02 A.notz", "1 x.notz", "appendix.notz")
        self.assertEqual([c.path.name for c in scan(self.root)[0].chapters],
                         ["1 x.notz", "02 A.notz", "02 b.notz", "appendix.notz", "notes.notz"])

    def test_a_folder_named_like_a_chapter_and_files_in_the_root_are_ignored(self):
        d = self.make("Book", "01 A.notz")
        (d / "02 Folder.notz").mkdir()
        (self.root / "00 stray.notz").write_text("{}", encoding="utf-8")
        books = scan(self.root)
        self.assertEqual([(b.name, [c.label for c in b.chapters]) for b in books], [("Book", ["A"])])

    def test_books_sort_without_regard_to_case(self):
        for name in ("beta", "Alpha", "gamma", "Delta"):
            self.make(name, "01.notz")
        self.assertEqual([b.name for b in scan(self.root)], ["Alpha", "beta", "Delta", "gamma"])

    def test_finding_a_chapter_that_is_not_there(self):
        self.make("Book", "01 A.notz")
        books = scan(self.root)
        self.assertEqual(find(books, None), (None, None))
        self.assertEqual(find(books, self.root / "Book" / "09 Gone.notz"), (None, None))
        self.assertEqual(find([], self.root / "Book" / "01 A.notz"), (None, None))

    def test_neighbors_step_over_more_than_one(self):
        d = self.make("Book", "01 A.notz", "02 B.notz", "03 C.notz")
        books = scan(self.root)
        self.assertEqual(neighbor(books, d / "01 A.notz", 2).label, "C")
        self.assertIsNone(neighbor(books, d / "01 A.notz", 3))


class MoreChangesTest(ChangeTest):
    def test_changing_nothing_changes_nothing(self):
        p = self.chapter("Book", 3, "C", "c")
        before = p.read_bytes()
        self.assertEqual(set_chapter(p, 3, "C"), {p: p})
        self.assertEqual(self.state(), [("03 C.notz", 3, "C", "Book", "c")])
        self.assertEqual(json.loads(p.read_text(encoding="utf-8")), json.loads(before))

    def test_a_swap_and_a_new_title_in_one_step(self):
        a = self.chapter("Book", 1, "A", "a")
        b = self.chapter("Book", 2, "B", "b")
        moved = set_chapter(a, 2, "A renamed")
        self.assertEqual(self.state(), [("01 B.notz", 1, "B", "Book", "b"), ("02 A renamed.notz", 2, "A renamed", "Book", "a")])
        self.assertEqual(moved, {a: self.root / "Book" / "02 A renamed.notz", b: self.root / "Book" / "01 B.notz"})

    def test_a_rename_never_overwrites_another_chapters_file(self):
        x = self.chapter("Book", 1, "X", "x text")
        self.chapter("Book", 1, "Y", "y text")  # two chapters with the same number, e.g. copied in by hand
        with self.assertRaises(FileExistsError):
            set_chapter(x, 1, "Y")
        self.assertEqual(self.state(), [("01 X.notz", 1, "X", "Book", "x text"), ("01 Y.notz", 1, "Y", "Book", "y text")])

    def test_a_long_title_is_shortened_only_in_the_file_name(self):
        title = " ".join(["Архитектура"] * 20)
        p = self.chapter("Book", 1, "Short", "notes")
        moved = set_chapter(p, 2, title)
        new = moved[p]
        self.assertTrue(new.exists())
        self.assertEqual(Document.load(new).chapter_title, title)
        self.assertEqual(set_chapter(new, 3, title)[new].name, chapter_filename(3, title), "and it can change again")

    def test_removing_the_title_leaves_just_the_number(self):
        p = self.chapter("Book", 4, "Titled", "t")
        set_chapter(p, 4, "")
        self.assertEqual(self.state(), [("04.notz", 4, "", "Book", "t")])

    def test_moving_to_a_book_that_does_not_exist_yet_creates_it(self):
        p = self.chapter("Book", 3, "C", "c")
        moved = set_chapter(p, 3, "C", self.root / "Fresh")
        self.assertEqual(moved, {p: self.root / "Fresh" / "03 C.notz"})
        self.assertEqual(self.state("Fresh"), [("03 C.notz", 3, "C", "Fresh", "c")])
        self.assertEqual(self.state(), [])

    def test_a_chapter_moved_to_a_book_gets_the_books_stored_name(self):
        a = self.chapter("Book", 1, "A")
        self.chapter("Other / Two", 1, "X")
        set_chapter(a, 2, "A", self.root / safe_name("Other / Two"))
        self.assertEqual(Document.load(self.root / "Other _ Two" / "02 A.notz").book, "Other / Two",
                         "not the folder's name, which lost its slash")

    def test_the_stored_book_name_falls_back_to_the_folder(self):
        from notterizmus.library import book_name
        d = self.root / "Odd"
        d.mkdir()
        (d / "01 broken.notz").write_text("{not json", encoding="utf-8")
        self.assertEqual(book_name(d), "Odd")
        (d / "02 fine.notz").write_text(json.dumps({"book": "Real / Name", "content": []}), encoding="utf-8")
        self.assertEqual(book_name(d), "Real / Name", "the unreadable chapter is skipped")

    def test_renumbering_a_chapter_alone(self):
        a = self.chapter("Book", 1, "A", "a")
        self.assertEqual(renumber({a: 7}), {a: self.root / "Book" / "07 A.notz"})
        self.assertEqual(self.state(), [("07 A.notz", 7, "A", "Book", "a")])
        self.assertEqual(renumber({self.root / "Book" / "07 A.notz": 7}), {}, "already there: nothing moves")

    def test_two_chapters_with_the_same_title_can_swap(self):
        a = self.chapter("Book", 1, "Same", "first")
        b = self.chapter("Book", 2, "Same", "second")
        renumber({a: 2, b: 1})
        self.assertEqual(self.state(), [("01 Same.notz", 1, "Same", "Book", "second"),
                                        ("02 Same.notz", 2, "Same", "Book", "first")])

    def test_a_chapter_that_cannot_be_read_stops_a_renumbering_before_anything_moves(self):
        a = self.chapter("Book", 1, "A", "a")
        b = self.chapter("Book", 2, "B", "b")
        broken = self.root / "Book" / "03 Broken.notz"
        broken.write_text("[]", encoding="utf-8")
        before = sorted(f.name for f in (self.root / "Book").iterdir())
        with self.assertRaises(ValueError):
            renumber({a: 3, b: 1, broken: 2})
        with self.assertRaises(ValueError):
            reorder([c for name in ("03 Broken.notz", "01 A.notz", "02 B.notz")
                     for c in scan(self.root)[0].chapters if c.path.name == name])
        self.assertEqual(sorted(f.name for f in (self.root / "Book").iterdir()), before,
                         "no chapter is left under a hidden staging name")
        self.assertEqual([(d.chapter_no, d.chapter_title, d.root.children[0].text)
                          for d in (Document.load(a), Document.load(b))], [(1, "A", "a"), (2, "B", "b")])

    def test_renaming_a_book_takes_an_unreadable_chapter_along_untouched(self):
        self.chapter("Old", 1, "A", "a")
        (self.root / "Old" / "02 Broken.notz").write_text("{not json", encoding="utf-8")
        (self.root / "Old" / "03 Odd.notz").write_text("[]", encoding="utf-8")
        moved = rename_book(self.root / "Old", "New")
        new = self.root / "New"
        self.assertEqual(sorted(f.name for f in new.iterdir()), ["01 A.notz", "02 Broken.notz", "03 Odd.notz"])
        self.assertEqual(Document.load(new / "01 A.notz").book, "New")
        self.assertEqual((new / "02 Broken.notz").read_text(encoding="utf-8"), "{not json")
        self.assertEqual((new / "03 Odd.notz").read_text(encoding="utf-8"), "[]")
        self.assertEqual(moved[self.root / "Old" / "03 Odd.notz"], new / "03 Odd.notz")

    def test_renaming_a_book_goes_on_past_a_chapter_it_cannot_write(self):
        from unittest import mock
        from notterizmus import library
        self.chapter("Old", 1, "A")
        self.chapter("Old", 2, "B")
        real = library._rewrite

        def rewrite(path, new_path, **fields):
            if Path(path).name.startswith("01"):
                raise OSError("disk full")
            return real(path, new_path, **fields)

        failed = []
        with mock.patch.object(library, "_rewrite", rewrite):
            moved = rename_book(self.root / "Old", "New", failed)
        new = self.root / "New"
        self.assertEqual(failed, [new / "01 A.notz"])
        self.assertEqual(sorted(moved.values()), [new / "01 A.notz", new / "02 B.notz"])
        self.assertEqual([Document.load(new / n).book for n in ("01 A.notz", "02 B.notz")], ["Old", "New"])

    def test_renumbering_leaves_no_staging_files(self):
        a = self.chapter("Book", 1, "A")
        b = self.chapter("Book", 2, "B")
        c = self.chapter("Book", 3, "C")
        renumber({a: 3, b: 1, c: 2})
        self.assertEqual(sorted(f.name for f in (self.root / "Book").iterdir()), ["01 B.notz", "02 C.notz", "03 A.notz"])

    def test_reorder_leaves_unnumbered_files_alone(self):
        a = self.chapter("Book", 1, "A")
        b = self.chapter("Book", 2, "B")
        loose = self.root / "Book" / "notes.notz"
        loose.write_text(json.dumps({"book": "Book", "content": []}), encoding="utf-8")
        chapters = scan(self.root)[0].chapters
        by_name = {c.path.name: c for c in chapters}
        reorder([by_name["notes.notz"], by_name["02 B.notz"], by_name["01 A.notz"]])
        self.assertEqual(sorted(f.name for f in (self.root / "Book").iterdir()), ["01 B.notz", "02 A.notz", "notes.notz"])
        self.assertTrue(a.name != b.name)

    def test_reordering_into_the_same_order_moves_nothing(self):
        self.chapter("Book", 1, "A")
        self.chapter("Book", 2, "B")
        self.assertEqual(reorder(scan(self.root)[0].chapters), {})

    def test_renaming_a_book_to_its_own_name_keeps_everything(self):
        p = self.chapter("Book", 1, "A", "a")
        self.assertEqual(rename_book(self.root / "Book", "Book"), {p: p})
        self.assertEqual(self.state(), [("01 A.notz", 1, "A", "Book", "a")])

    def test_renaming_a_book_skips_hidden_files(self):
        self.chapter("Old", 1, "A")
        hidden = self.root / "Old" / ".moving-12345678.notz"
        hidden.write_text("not a chapter", encoding="utf-8")
        rename_book(self.root / "Old", "New")
        self.assertEqual((self.root / "New" / ".moving-12345678.notz").read_text(encoding="utf-8"), "not a chapter")

    def test_the_chapter_with_a_number(self):
        from notterizmus.library import chapter_numbered
        a = self.chapter("Book", 1, "A")
        b = self.chapter("Book", 2, "B")
        folder = self.root / "Book"
        self.assertEqual(chapter_numbered(folder, 2).path, b)
        self.assertIsNone(chapter_numbered(folder, 2, exclude=b))
        self.assertIsNone(chapter_numbered(folder, 9))
        self.assertEqual(chapter_numbered(folder, 1, exclude=b).path, a)
        self.assertIsNone(chapter_numbered(self.root / "No such book", 1))


class InterruptedChangeTest(ChaptersCase):
    """A renumbering put things back only when a file was in the way. When the second
    chapter's write failed (a full disk, say), the first was left under a hidden staging
    name and vanished from the chapter list (CR6 in CODE_REVIEW.md)."""

    def setUp(self):
        super().setUp()
        self.a = self.chapter("Book", 1, "A", "a")
        self.b = self.chapter("Book", 2, "B", "b")
        self.c = self.chapter("Book", 3, "C", "c")
        self.before = self.state()

    def hidden(self):
        return sorted(f.name for f in (self.root / "Book").iterdir() if f.name.startswith("."))

    def failing(self, owner, name, at, then_all=False):
        """Patch owner.name so that its at-th call (and with then_all, every later one) fails
        as on a full disk."""
        real, calls = getattr(owner, name), []

        def call(*args, **kwargs):
            calls.append(1)
            if len(calls) == at or (then_all and len(calls) > at):
                raise OSError(errno.ENOSPC, "No space left on device")
            return real(*args, **kwargs)
        return mock.patch.object(owner, name, call)

    def assert_put_back(self):
        self.assertEqual(self.state(), self.before)
        self.assertEqual([c.path.name for c in scan(self.root)[0].chapters], ["01 A.notz", "02 B.notz", "03 C.notz"])
        self.assertEqual(self.hidden(), [])

    def test_a_write_that_fails_halfway_puts_every_chapter_back(self):
        for at in (1, 2, 3):
            with self.subTest(write=at), self.failing(Document, "save", at), self.assertRaises(OSError):
                renumber({self.a: 2, self.b: 3, self.c: 1})
            self.assert_put_back()

    def test_a_final_rename_that_fails_puts_every_chapter_back(self):
        for at in (1, 2, 3):
            with self.subTest(rename=at), self.failing(Path, "rename", at), self.assertRaises(OSError):
                renumber({self.a: 2, self.b: 3, self.c: 1})
            self.assert_put_back()

    def test_with_the_disk_still_full_the_names_at_least_come_back(self):
        with self.failing(Document, "save", 2, then_all=True), self.assertRaises(OSError):
            reorder(scan(self.root)[0].chapters[::-1])  # C and A swap (B keeps 2): C's write, A's fails
        self.assertEqual([c.path.name for c in scan(self.root)[0].chapters], ["01 A.notz", "02 B.notz", "03 C.notz"])
        self.assertEqual(self.hidden(), [])

    def test_a_number_two_chapters_share_is_refused_before_anything_moves(self):
        x = self.chapter("Twice", 3, "X")
        self.chapter("Twice", 5, "A")
        self.chapter("Twice", 5, "B")
        before = self.state("Twice")
        with self.assertRaises(FileExistsError):
            set_chapter(x, 5, "X")
        self.assertEqual(self.state("Twice"), before)

    def test_a_new_title_that_fails_after_a_swap_undoes_the_swap(self):
        with self.failing(Document, "save", 3), self.assertRaises(OSError):
            set_chapter(self.a, 2, "New")  # swaps numbers with B (writes 1 and 2), then renames A (3)
        self.assertEqual(self.state(), self.before)
        self.assertEqual(self.hidden(), [])

    def test_a_chapter_left_hidden_by_a_crash_gets_its_name_back(self):
        """A crash or power cut halfway leaves a chapter under its staging name, with its
        new number already inside."""
        doc = Document.load(self.b)
        doc.chapter_no = 4
        doc.save(self.root / "Book" / ".moving-0123abcd.notz")
        self.b.unlink()
        lost = stranded(self.root)
        self.assertEqual([p.name for p in lost], [".moving-0123abcd.notz"])
        self.assertEqual(restore_stranded(lost[0]), self.root / "Book" / "04 B.notz")
        self.assertEqual(self.state()[-1], ("04 B.notz", 4, "B", "Book", "b"))
        self.assertEqual((stranded(self.root), self.hidden()), ([], []))

    def test_a_stranded_chapter_whose_name_is_taken_is_restored_beside_it(self):
        Document.load(self.c).save(self.root / "Book" / ".moving-0123abcd.notz")  # a copy of 03 C
        restored = restore_stranded(stranded(self.root)[0])
        self.assertEqual(restored.name, "03 C (restored).notz")
        self.assertEqual(Document.load(restored).chapter_title, "C (restored)")
        self.assertEqual(Document.load(self.c).chapter_title, "C", "the chapter with that name is untouched")


class ConflictPathTest(unittest.TestCase):
    """Where this version of a chapter goes when the other one can't be kept (RV4 in PLAN.md)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.chapter = Path(self.tmp.name) / "03 Глава.notz"

    def test_beside_the_chapter_with_the_day(self):
        from datetime import date
        from notterizmus.library import conflict_path
        self.assertEqual(conflict_path(self.chapter, date(2026, 11, 27)),
                         self.chapter.with_name("03 Глава (conflict 2026-11-27).notz"))

    def test_never_a_name_that_is_taken(self):
        from datetime import date
        from notterizmus.library import conflict_path
        day = date(2026, 11, 27)
        first = conflict_path(self.chapter, day)
        first.write_text("x")
        self.assertEqual(conflict_path(self.chapter, day), self.chapter.with_name("03 Глава (conflict 2026-11-27 2).notz"))

    def test_a_long_name_still_fits(self):
        from datetime import date
        from notterizmus.library import conflict_path
        from notterizmus.model import NAME_MAX, chapter_filename
        long = self.chapter.with_name(chapter_filename(3, "Дълго заглавие " * 30))
        path = conflict_path(long, date(2026, 11, 27))
        self.assertLessEqual(len(path.name.encode()), NAME_MAX)
        self.assertTrue(path.name.endswith(" (conflict 2026-11-27).notz"))
        self.assertEqual(parse_name(path.stem)[0], 3, "still numbered as the chapter")


if __name__ == "__main__":
    unittest.main()
