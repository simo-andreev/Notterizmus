import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
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
        now = now.astimezone()  # ages are the time that really passed, across a clock change too
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
        self.assertEqual(made, self.folder / f"{T0.astimezone(timezone.utc):%Y-%m-%dT%H-%M-%S}Z.notz", "in UTC")
        self.assertEqual([b.when for b in backups.list_backups(self.folder)], [T0.astimezone()])

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
        made = backups.backup(self.chapter, self.folder, now=T0)
        for name in ("junk.notz", "2026-13-45T99-99-99.notz", "2026-13-45T99-99-99Z.notz", "note.txt"):
            (self.folder / name).write_text("x", encoding="utf-8")
        self.assertEqual([b.path.name for b in backups.list_backups(self.folder)], [made.name])
        self.assertEqual(backups.thin(self.folder, T0 + timedelta(days=400)), 0)
        self.assertEqual(len(list(self.folder.iterdir())), 5)

    def test_a_folder_that_does_not_exist_has_no_copies(self):
        self.assertEqual(backups.list_backups(self.root / "nowhere"), [])
        self.assertEqual(backups.thin(self.root / "nowhere"), 0)

    def test_the_tiers_meet_without_gaps(self):
        now = datetime(2026, 11, 13, 12, 0).astimezone()  # ages are the time that really passed
        self.folder.mkdir(parents=True)
        ages = {"23 h 59 min": timedelta(hours=23, minutes=59), "24 h": timedelta(days=1),
                "24 h 10 min": timedelta(days=1, minutes=10),            # the hour before 24 h
                "24 h 20 min": timedelta(days=1, minutes=20),            # same hour slot as that
                "6 d 23 h": timedelta(days=6, hours=23), "7 d": timedelta(days=7),
                "7 d 1 h": timedelta(days=7, hours=1),                   # same day slot as 7 d
                "89 d": timedelta(days=89), "90 d": timedelta(days=90),
                "91 d": timedelta(days=91)}                              # same ISO week as 90 d
        for age in ages.values():
            (self.folder / f"{(now - age).astimezone(timezone.utc):%Y-%m-%dT%H-%M-%S}Z.notz").write_text("x")
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

    def test_a_version_that_is_not_on_disk_can_be_kept(self):
        """Reload (a chapter changed on disk) keeps the edits it replaces (CR10)."""
        backups.backup(self.chapter, self.folder, now=T0)
        made = backups.keep(b"unsaved edits", self.folder, now=T0)
        self.assertEqual(made.read_bytes(), b"unsaved edits")
        self.assertEqual(self.contents(), ["unsaved edits", "v1"], "the newest, though taken in the same second")
        self.assertIsNone(backups.keep(b"unsaved edits", self.folder, now=T0 + timedelta(minutes=1)))

    def test_a_copy_is_the_file_byte_for_byte(self):
        data = bytes(range(256)) * 3
        self.chapter.write_bytes(data)
        made = backups.backup(self.chapter, self.folder, now=T0)
        self.assertEqual(made.read_bytes(), data)


class DaylightSavingTest(unittest.TestCase):
    """Copies were named by local time, which has an hour twice when daylight saving ends:
    copies in that hour sorted in the wrong order or collided, so the newest copy and the
    ten-minute check could be wrong (CR26 in CODE_REVIEW.md). On 2026-10-25 in Sofia the
    clocks go back from 04:00 summer time to 03:00, so 03:00–04:00 comes twice."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.chapter = base / "Notterizmus" / "Book" / "01 Intro.notz"
        self.chapter.parent.mkdir(parents=True)
        self.folder = base / "backups" / "Book" / "01 Intro"
        self.addCleanup(self.set_zone, os.environ.get("TZ"))
        self.set_zone("Europe/Sofia")

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def set_zone(zone):
        if zone is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = zone
        time.tzset()

    def copy(self, text, now, force=True):
        self.chapter.write_text(text, encoding="utf-8")
        return backups.backup(self.chapter, self.folder, now=now, force=force)

    def contents(self):
        return [b.path.read_text(encoding="utf-8") for b in backups.list_backups(self.folder)]

    def test_two_copies_in_the_hour_that_comes_twice_are_kept_in_order(self):
        self.assertIsNotNone(self.copy("v1", datetime(2026, 10, 25, 3, 50)))          # summer time
        self.assertIsNotNone(self.copy("v2", datetime(2026, 10, 25, 3, 10, fold=1)))  # 20 min later
        self.assertEqual(self.contents(), ["v2", "v1"], "newest first")
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()),
                         ["2026-10-25T00-50-00Z.notz", "2026-10-25T01-10-00Z.notz"], "named in UTC")
        self.assertEqual([f"{b.when:%H:%M}" for b in backups.list_backups(self.folder)], ["03:10", "03:50"],
                         "shown in local time")

    def test_the_ten_minute_check_counts_the_hour_that_comes_twice(self):
        self.copy("v1", datetime(2026, 10, 25, 3, 50))
        self.assertIsNotNone(self.copy("v2", datetime(2026, 10, 25, 3, 55, fold=1), force=False),
                             "03:55 winter time is 65 minutes after 03:50 summer time")

    def test_copies_with_old_local_time_names_are_still_listed_and_thinned(self):
        self.folder.mkdir(parents=True)
        for minute in (5, 25):
            (self.folder / f"2026-11-10T10-{minute:02d}-00.notz").write_text(f"old {minute}", encoding="utf-8")
        self.copy("new", datetime(2026, 11, 10, 10, 45))
        self.assertEqual(self.contents(), ["new", "old 25", "old 5"])
        backups.thin(self.folder, datetime(2026, 11, 13, 12, 0))  # three days on: one copy per hour
        self.assertEqual(self.contents(), ["new"])


class SwapTest(unittest.TestCase):
    """When chapters whose file names differ only in the number (untitled ones, or ones with
    the same title) swapped places, their copies moved one folder at a time, and the first
    move merged into the other chapter's folder: chapter 01 then listed both chapters'
    copies, and 02 none (CR5 in CODE_REVIEW.md)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.notes, self.root = base / "Notterizmus", base / "backups"
        self.book = self.notes / "Book"
        self.book.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def copies_of(self, names):
        """One copy of each chapter (a file name in Book); its text names the chapter."""
        for i, name in enumerate(names):
            (self.book / name).write_text(f"copy of {name}", encoding="utf-8")
            backups.backup(self.book / name, backups.folder_for(self.book / name, self.notes, self.root),
                           now=T0 + timedelta(minutes=i))

    def copies(self, name):
        folder = backups.folder_for(self.book / name, self.notes, self.root)
        return [b.path.read_text(encoding="utf-8") for b in backups.list_backups(folder)]

    def test_untitled_chapters_that_swap_keep_their_own_copies(self):
        self.copies_of(["01.notz", "02.notz"])
        backups.move({self.book / "01.notz": self.book / "02.notz",
                      self.book / "02.notz": self.book / "01.notz"}, self.notes, self.root)
        self.assertEqual([self.copies("01.notz"), self.copies("02.notz")], [["copy of 02.notz"], ["copy of 01.notz"]])

    def test_three_chapters_with_one_title_that_rotate_keep_their_own_copies(self):
        names = ["01 Same.notz", "02 Same.notz", "03 Same.notz"]
        self.copies_of(names)
        backups.move({self.book / a: self.book / b for a, b in zip(names, names[1:] + names[:1])},
                     self.notes, self.root)
        self.assertEqual([self.copies(n) for n in names],
                         [["copy of 03 Same.notz"], ["copy of 01 Same.notz"], ["copy of 02 Same.notz"]])
        self.assertEqual([p.name for p in self.root.rglob(".*")], [], "nothing is left aside")


class UnsavedTest(unittest.TestCase):
    """A chapter that couldn't be saved where it belongs, written aside before the window
    may close without it (RV1 in PLAN.md)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "unsaved"
        self.chapter = Path(self.tmp.name) / "Notterizmus" / "Книга" / "03 Глава.notz"

    def test_kept_by_book_and_chapter_with_the_time_in_utc(self):
        path = backups.keep_unsaved("текст", self.chapter, self.folder,
                                    now=datetime(2026, 11, 27, 10, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(path, self.folder / "Книга" / "03 Глава 2026-11-27T10-00-00Z.notz")
        self.assertEqual(path.read_text(encoding="utf-8"), "текст")

    def test_a_second_copy_in_the_same_second_does_not_replace_the_first(self):
        now = datetime(2026, 11, 27, 10, 0, 0, tzinfo=timezone.utc)
        first = backups.keep_unsaved("one", self.chapter, self.folder, now=now)
        second = backups.keep_unsaved("two", self.chapter, self.folder, now=now)
        self.assertNotEqual(first, second)
        self.assertEqual((first.read_text(), second.read_text()), ("one", "two"))

    def test_nothing_half_written_is_left_when_it_fails(self):
        self.folder.mkdir()
        (self.folder / "Книга").write_text("a file where the folder should be")
        with self.assertRaises(OSError):
            backups.keep_unsaved("x", self.chapter, self.folder)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["Книга"])


if __name__ == "__main__":
    unittest.main()
