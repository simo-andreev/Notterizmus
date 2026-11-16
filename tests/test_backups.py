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


class MoreBackupsTest(BackupsTest):
    def stamp(self, when):
        return f"{when:%Y-%m-%dT%H-%M-%S}.notz"

    def test_copies_are_named_by_when_they_were_taken(self):
        made = backups.backup(self.chapter, self.folder, now=T0)
        self.assertEqual(made, self.folder / "2026-11-06T12-00-00.notz")
        self.assertEqual([b.when for b in backups.list_backups(self.folder)], [T0])

    def test_a_second_copy_in_the_same_second_keeps_the_first(self):
        backups.backup(self.chapter, self.folder, now=T0)
        self.write("v2")
        self.assertIsNone(backups.backup(self.chapter, self.folder, now=T0, force=True))
        self.assertEqual(self.contents(), ["v1"])

    def test_the_interval_can_be_given_for_one_call(self):
        backups.backup(self.chapter, self.folder, now=T0)
        self.write("v2")
        self.assertIsNone(backups.backup(self.chapter, self.folder, now=T0 + timedelta(seconds=5), every=10))
        self.assertIsNotNone(backups.backup(self.chapter, self.folder, now=T0 + timedelta(seconds=10), every=10))
        self.assertEqual(self.contents(), ["v2", "v1"])

    def test_a_change_made_and_undone_is_still_one_more_copy(self):
        backups.backup(self.chapter, self.folder, now=T0)
        self.write("v2")
        backups.backup(self.chapter, self.folder, now=T0 + timedelta(hours=1))
        self.write("v1")
        backups.backup(self.chapter, self.folder, now=T0 + timedelta(hours=2))
        self.assertEqual(self.contents(), ["v1", "v2", "v1"], "only the newest copy is compared")

    def test_other_files_in_the_folder_are_neither_listed_nor_thinned(self):
        backups.backup(self.chapter, self.folder, now=T0)
        for name in ("junk.notz", "2026-13-45T99-99-99.notz", "note.txt"):
            (self.folder / name).write_text("x", encoding="utf-8")
        self.assertEqual([b.path.name for b in backups.list_backups(self.folder)], ["2026-11-06T12-00-00.notz"])
        self.assertEqual(backups.thin(self.folder, T0 + timedelta(days=400)), 0)
        self.assertEqual(len(list(self.folder.iterdir())), 4)

    def test_a_folder_that_does_not_exist_has_no_copies(self):
        self.assertEqual(backups.list_backups(self.root / "nowhere"), [])
        self.assertEqual(backups.thin(self.root / "nowhere"), 0)

    def test_the_tiers_meet_without_gaps(self):
        now = datetime(2026, 11, 13, 12, 0)
        self.folder.mkdir(parents=True)
        ages = {"23 h 59 min": timedelta(hours=23, minutes=59), "24 h": timedelta(days=1),
                "24 h 10 min": timedelta(days=1, minutes=10),            # the hour before 24 h
                "24 h 20 min": timedelta(days=1, minutes=20),            # same hour slot as that
                "6 d 23 h": timedelta(days=6, hours=23), "7 d": timedelta(days=7),
                "7 d 1 h": timedelta(days=7, hours=1),                   # same day slot as 7 d
                "89 d": timedelta(days=89), "90 d": timedelta(days=90),
                "91 d": timedelta(days=91)}                              # same ISO week as 90 d
        for age in ages.values():
            (self.folder / self.stamp(now - age)).write_text("x", encoding="utf-8")
        backups.thin(self.folder, now)
        kept = {now - b.when for b in backups.list_backups(self.folder)}
        gone = {label for label, age in ages.items() if age not in kept}
        self.assertEqual(gone, {"24 h 20 min", "7 d 1 h", "91 d"}, "the older copy of each shared slot")

    def test_thinning_reports_how_many_copies_went(self):
        now = datetime(2026, 11, 13, 12, 0)
        self.folder.mkdir(parents=True)
        for minute in (5, 25, 45):
            (self.folder / self.stamp((now - timedelta(days=3)).replace(minute=minute))).write_text("x")
        self.assertEqual(backups.thin(self.folder, now), 2)
        self.assertEqual(backups.thin(self.folder, now), 0, "thinning again finds nothing more")

    def test_copies_of_a_chapter_opened_from_elsewhere_are_kept_apart_by_path(self):
        base = Path(self.tmp.name)
        one = backups.folder_for(base / "a" / "x.notz", self.notes, self.root)
        two = backups.folder_for(base / "b" / "x.notz", self.notes, self.root)
        self.assertNotEqual(one, two)
        self.assertEqual(one, backups.folder_for(base / "a" / ".." / "a" / "x.notz", self.notes, self.root))

    def test_moved_copies_join_the_ones_already_there(self):
        backups.backup(self.chapter, self.folder, now=T0)
        new = self.notes / "Book" / "02 B.notz"
        there = backups.folder_for(new, self.notes, self.root)
        there.mkdir(parents=True)
        (there / self.stamp(T0 - timedelta(days=1))).write_text("older", encoding="utf-8")
        backups.move({self.chapter: new}, self.notes, self.root)
        self.assertEqual([b.path.read_text(encoding="utf-8") for b in backups.list_backups(there)], ["v1", "older"])
        self.assertFalse(self.folder.exists())

    def test_moving_a_chapter_without_copies_or_onto_itself_does_nothing(self):
        new = self.notes / "Book" / "02 B.notz"
        backups.move({self.chapter: new}, self.notes, self.root)
        self.assertFalse(self.root.exists())
        backups.backup(self.chapter, self.folder, now=T0)
        backups.move({self.chapter: self.chapter}, self.notes, self.root)
        self.assertEqual(self.contents(), ["v1"])

    def test_a_copy_is_the_file_byte_for_byte(self):
        data = bytes(range(256)) * 3
        self.chapter.write_bytes(data)
        made = backups.backup(self.chapter, self.folder, now=T0)
        self.assertEqual(made.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
