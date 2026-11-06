import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from notterizmus import backups
from notterizmus.paths import backups_dir, data_dir

T0 = datetime(2026, 11, 6, 12, 0, 0)


class BackupsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.notes, self.root = base / "Notterizmus", base / "backups"
        self.chapter = self.notes / "Book" / "01 Intro.notz"
        self.chapter.parent.mkdir(parents=True)
        self.write("v1")
        self.folder = backups.folder_for(self.chapter, self.notes, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text):
        self.chapter.write_text(text, encoding="utf-8")

    def contents(self):
        return [b.path.read_text(encoding="utf-8") for b in backups.list_backups(self.folder)]

    def test_folder_follows_book_and_chapter(self):
        self.assertEqual(self.folder, self.root / "Book" / "01 Intro")
        other = backups.folder_for(Path(self.tmp.name) / "elsewhere" / "x.notz", self.notes, self.root)
        self.assertEqual(other.parent, self.root / "_elsewhere")
        self.assertTrue(other.name.startswith("x-"))

    def test_one_copy_per_interval_unless_forced(self):
        self.assertIsNotNone(backups.backup(self.chapter, self.folder, now=T0))
        self.write("v2")
        self.assertIsNone(backups.backup(self.chapter, self.folder, now=T0 + timedelta(minutes=5)))
        self.assertIsNotNone(backups.backup(self.chapter, self.folder, now=T0 + timedelta(minutes=5), force=True))
        self.write("v3")
        self.assertIsNotNone(backups.backup(self.chapter, self.folder, now=T0 + timedelta(minutes=16)))
        self.assertEqual(self.contents(), ["v3", "v2", "v1"])

    def test_an_unchanged_file_is_not_copied_again(self):
        backups.backup(self.chapter, self.folder, now=T0)
        self.assertIsNone(backups.backup(self.chapter, self.folder, now=T0 + timedelta(hours=1), force=True))
        self.assertEqual(self.contents(), ["v1"])

    def test_keeps_only_the_newest(self):
        for i in range(25):
            self.write(f"v{i}")
            backups.backup(self.chapter, self.folder, now=T0 + timedelta(minutes=11 * i))
        got = self.contents()
        self.assertEqual(len(got), backups.KEEP)
        self.assertEqual(got[0], "v24")
        self.assertEqual(got[-1], f"v{25 - backups.KEEP}")

    def test_missing_chapter_is_skipped(self):
        self.chapter.unlink()
        self.assertIsNone(backups.backup(self.chapter, self.folder, now=T0))

    def test_copies_follow_a_renamed_or_moved_chapter(self):
        backups.backup(self.chapter, self.folder, now=T0)
        new = self.notes / "Other book" / "03 Renamed.notz"
        backups.move({self.chapter: new}, self.notes, self.root)
        moved = backups.folder_for(new, self.notes, self.root)
        self.assertEqual([b.path.read_text(encoding="utf-8") for b in backups.list_backups(moved)], ["v1"])
        self.assertFalse((self.root / "Book").exists(), "empty folders are cleaned up")

    def test_paths(self):
        self.assertEqual(data_dir({"XDG_DATA_HOME": "/d"}), Path("/d/notterizmus"))
        self.assertEqual(backups_dir({"XDG_DATA_HOME": "/d"}), Path("/d/notterizmus/backups"))


if __name__ == "__main__":
    unittest.main()
