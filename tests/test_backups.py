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

    def test_old_copies_are_thinned_by_age(self):
        now = datetime(2026, 11, 13, 12, 0)
        self.folder.mkdir(parents=True)
        when = now - timedelta(days=120)
        made = 0
        while when <= now:  # a copy every 10 minutes for 120 days
            (self.folder / f"{when:%Y-%m-%dT%H-%M-%S}.notz").write_text("x", encoding="utf-8")
            when += timedelta(minutes=10)
            made += 1
        backups.thin(self.folder, now)
        kept = [b.when for b in backups.list_backups(self.folder)]
        last_day = [w for w in kept if now - w < timedelta(days=1)]
        week = [w for w in kept if timedelta(days=1) <= now - w < timedelta(days=7)]
        months = [w for w in kept if timedelta(days=7) <= now - w < timedelta(days=90)]
        older = [w for w in kept if now - w >= timedelta(days=90)]
        self.assertEqual(len(last_day), 144, "every copy of the last day")
        self.assertEqual(len({w.strftime("%Y-%m-%d %H") for w in week}), len(week), "one per hour")
        self.assertGreaterEqual(len(week), 6 * 24 - 1)
        self.assertEqual(len({w.date() for w in months}), len(months), "one per day")
        self.assertEqual(len({w.isocalendar()[:2] for w in older}), len(older), "one per week")
        self.assertLess(len(kept), made // 20)
        self.assertEqual(kept[0], now, "the newest copy stays")

    def test_each_slot_keeps_its_newest_copy(self):
        now = datetime(2026, 11, 13, 12, 0)
        self.folder.mkdir(parents=True)
        hour = now - timedelta(days=3)
        for minute in (5, 25, 45):
            (self.folder / f"{hour.replace(minute=minute):%Y-%m-%dT%H-%M-%S}.notz").write_text("x")
        backups.thin(self.folder, now)
        self.assertEqual([b.when.minute for b in backups.list_backups(self.folder)], [45])

    def test_a_new_copy_thins_the_old_ones(self):
        for i in range(30):
            self.write(f"v{i}")
            backups.backup(self.chapter, self.folder, now=T0 - timedelta(days=5) + timedelta(minutes=11 * i))
        self.write("now")
        backups.backup(self.chapter, self.folder, now=T0)
        got = backups.list_backups(self.folder)
        self.assertEqual(got[0].path.read_text(encoding="utf-8"), "now")
        self.assertEqual(len({b.when.strftime("%Y-%m-%d %H") for b in got[1:]}), len(got) - 1)

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
