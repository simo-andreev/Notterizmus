"""Imported assessment reports and practice attempts, as files in the notes folder."""
from __future__ import annotations

import errno
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from notterizmus import assessments as store, library
from notterizmus.assessment_txt import PARSER_VERSION, Points, Report, ReportError, parse
from notterizmus.assessments import Answer, Attempt, Link

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GRADED = (FIXTURES / "assessment_design_a_rate_limiter.txt").read_bytes()
UNGRADED = (FIXTURES / "assessment_design_a_rate_limiter_ungraded.txt").read_bytes()
NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc)
FOLDER = "design_a_rate_limiter_2026-11-23T19-05-51"


def report_text(title="Design a Thing", completed="24.11.2026 г., 10:00:00 ч."):
    return (f"{title} - Online Assessment\n{'=' * 60}\nCompleted: {completed}\nAttempt: 1 of 1\n\n"
            f"Question 1\n{'-' * 60}\nQ: Why?\n\nYour answer:\nBecause.\n\n").encode()


def disk_full(*_args):
    raise OSError(errno.ENOSPC, "No space left on device")


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "Notterizmus" / ".assessments"

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, data=GRADED, **kw):
        return store.import_report(self.root, data, source="report.txt", now=NOW, **kw)

    def entries(self, folder=None):
        return sorted(p.name for p in (folder or self.root).iterdir())

    def stored(self, a, name=store.REPORT_JSON):
        return json.loads((a.folder / name).read_text(encoding="utf-8"))

    def write(self, path, data):
        """Write as a sync tool does: a new file put in place, so a new inode."""
        tmp = path.with_name(".synced")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)


class ImportTest(StoreTest):
    def test_an_imported_report_keeps_its_file_byte_for_byte_and_what_was_read(self):
        a = self.add(chapter=Link("Book/03 Design a Rate Limiter.notz", "Book", 3, "Design a Rate Limiter"))
        self.assertEqual(self.entries(), [FOLDER])
        self.assertEqual(self.entries(a.folder), ["report.json", "report.txt"])
        self.assertEqual((a.folder / "report.txt").read_bytes(), GRADED)
        d = self.stored(a)
        self.assertEqual(d["format"], store.FORMAT)
        self.assertEqual(d["parser_version"], PARSER_VERSION)
        self.assertEqual(d["source"], "report.txt")
        self.assertEqual(datetime.fromisoformat(d["imported"]), NOW)
        self.assertEqual(d["chapter"], {"file": "Book/03 Design a Rate Limiter.notz", "book": "Book",
                                        "number": 3, "title": "Design a Rate Limiter"})
        self.assertEqual(d["report"], parse(GRADED).to_json())

    def test_a_listed_report_is_the_one_imported(self):
        a = self.add()
        (found,), broken = store.list_all(self.root)
        self.assertEqual(broken, [])
        self.assertEqual(found.id, FOLDER)
        self.assertEqual(found.report, parse(GRADED))
        self.assertEqual(found.report, a.report)
        self.assertEqual((found.attempts, found.has_draft), (0, False))

    def test_reports_are_listed_the_most_recently_completed_first(self):
        self.add(report_text("Older", "01.11.2026 г., 10:00:00 ч."))
        self.add(report_text("Newer", "20.11.2026 г., 10:00:00 ч."))
        self.add(report_text("Unknown date", "someday"))
        found, _broken = store.list_all(self.root)
        self.assertEqual([a.report.title for a in found], ["Newer", "Older", "Unknown date"])

    def test_folder_names(self):
        self.add(report_text("Design a Key-Value Store!"))
        self.add(report_text("Проектиране на чат"))
        self.add(report_text("???"))
        self.add(report_text("Without a time", "someday"))
        self.assertEqual(self.entries(), [
            "assessment_2026-11-24T10-00-00", "design_a_key_value_store_2026-11-24T10-00-00",
            f"without_a_time_{NOW.astimezone():%Y-%m-%dT%H-%M-%S}", "проектиране_на_чат_2026-11-24T10-00-00"])

    def test_reports_with_the_same_folder_name_get_their_own_folders(self):
        first = self.add(report_text("Design a Thing"))
        second = self.add(report_text("Design a thing?"))
        self.assertNotEqual(first.report.key, second.report.key)
        self.assertEqual(second.folder.name, first.folder.name + "-2")
        self.assertEqual(len(store.list_all(self.root)[0]), 2)

    def test_a_failed_import_leaves_nothing(self):
        with mock.patch("notterizmus.files.os.fsync", side_effect=disk_full):
            with self.assertRaises(OSError):
                self.add()
        self.assertEqual(self.entries(), [])

    def test_an_import_a_crash_stopped_is_never_listed_and_goes_after_an_hour(self):
        self.add()
        for name, age in ((".importing-old", store.STALE_IMPORT + 60), (".importing-new", 60)):
            stage = self.root / name
            stage.mkdir()
            (stage / "report.txt").write_bytes(GRADED)
            when = NOW.timestamp() - age
            os.utime(stage, (when, when))
        found, broken = store.list_all(self.root, now=NOW)
        self.assertEqual(([a.id for a in found], broken), ([FOLDER], []))
        self.assertEqual(self.entries(), [".importing-new", FOLDER])

    def test_reading_a_file_to_import(self):
        path = Path(self.tmp.name) / "download.txt"
        path.write_bytes(GRADED)
        data, report = store.read_import(path)
        self.assertEqual((data, report), (GRADED, parse(GRADED)))
        path.write_bytes(b"not a report\n")
        with self.assertRaises(ReportError):
            store.read_import(path)
        with self.assertRaises(OSError):
            store.read_import(Path(self.tmp.name) / "missing.txt")

    def test_a_huge_file_is_refused_without_reading_all_of_it(self):
        path = Path(self.tmp.name) / "huge.txt"
        with open(path, "wb") as f:
            f.truncate(200 * 1024 * 1024)
        with mock.patch("notterizmus.assessment_txt.parse", wraps=parse) as parsed:
            with self.assertRaisesRegex(ReportError, "larger than 5 MB"):
                store.read_import(path)
        self.assertEqual(len(parsed.call_args.args[0]), store.MAX_BYTES + 1)


class DuplicateTest(StoreTest):
    def test_a_report_downloaded_again_is_found_graded_or_not(self):
        self.add(UNGRADED)
        found, _broken = store.list_all(self.root)
        self.assertEqual(store.find_duplicate(found, parse(GRADED)).id, FOLDER)
        self.assertIsNone(store.find_duplicate(found, parse(report_text())))

    def test_replacing_an_ungraded_report_with_its_graded_one_keeps_the_practice(self):
        a = self.add(UNGRADED, chapter=Link("Book/03 X.notz", "Book", 3, "X"))
        store.finish(a, Attempt(answers={1: Answer("first try")}), now=NOW)
        store.write_draft(a, Attempt(answers={2: Answer("second try", revealed=True)}), now=NOW)
        new = store.replace_report(a, GRADED, source="graded.txt", now=NOW + timedelta(hours=1))
        self.assertTrue(new.report.graded)
        self.assertEqual(new.folder, a.folder)
        self.assertEqual((a.folder / "report.txt").read_bytes(), GRADED)
        again = store.load(a.folder)
        self.assertEqual(again.report, parse(GRADED))
        self.assertEqual((again.source, again.chapter), ("graded.txt", a.chapter))
        self.assertEqual(again.imported, NOW + timedelta(hours=1))
        self.assertEqual((again.attempts, again.has_draft), (1, True))
        self.assertEqual(store.read_draft(again).answer(2).text, "second try")
        self.assertEqual(len(store.list_all(self.root)[0]), 1)

    def test_only_the_same_report_can_replace_one(self):
        a = self.add()
        with self.assertRaisesRegex(ValueError, "isn't another download"):
            store.replace_report(a, report_text())
        self.assertEqual((a.folder / "report.txt").read_bytes(), GRADED)

    def test_a_failed_replace_leaves_the_report_as_it_was(self):
        a = self.add(UNGRADED)
        before = {name: (a.folder / name).read_bytes() for name in self.entries(a.folder)}
        with mock.patch("notterizmus.files.os.fsync", side_effect=disk_full):
            with self.assertRaises(OSError):
                store.replace_report(a, GRADED)
        self.assertEqual({name: (a.folder / name).read_bytes() for name in self.entries(a.folder)}, before)


class DraftTest(StoreTest):
    def test_there_is_no_draft_until_one_is_saved(self):
        a = self.add()
        draft = store.read_draft(a)
        self.assertEqual(draft, Attempt())
        self.assertTrue(draft.is_empty())
        self.assertFalse((a.folder / "draft.json").exists())

    def test_a_draft_is_read_as_it_was_saved(self):
        a = self.add()
        text = "Token bucket:\n    - refill rate\n\n    - bucket size ’quoted’\n"
        draft = Attempt(answers={2: Answer(text), 5: Answer(revealed=True), 7: Answer("   ")})
        self.assertIsNone(store.write_draft(a, draft, now=NOW))
        self.assertEqual(draft.started, NOW)
        again = store.read_draft(a)
        self.assertEqual(again.started, NOW)
        self.assertEqual(again.answers, {2: Answer(text), 5: Answer(revealed=True)}, "a blank answer isn't kept")
        self.assertEqual((again.drafted(), again.revealed()), ({2}, {5}))
        self.assertEqual(self.stored(a, "draft.json")["answers"], {
            "2": {"text": text, "revealed": False}, "5": {"text": "", "revealed": True}})
        self.assertTrue(store.load(a.folder).has_draft)

    def test_fields_this_version_does_not_know_are_kept(self):
        a = self.add()
        d = a.to_json()
        d["future"] = {"x": 1}
        d["chapter"] = {"file": "B/01 T.notz", "book": "B", "number": 1, "title": "T", "anchor": "n1"}
        self.write(a.folder / "report.json", d)
        self.write(a.folder / "draft.json", {"format": "notterizmus-attempt/2", "started": "2026-11-25T10:00:00+00:00",
                                             "timer": 300, "answers": {"1": {"text": "a", "revealed": False, "ink": "blue"}}})
        store.set_chapter(a, Link("B/02 U.notz", "B", 2, "U", extra={"anchor": "n1"}))
        draft = store.read_draft(a)
        draft.answers[1].text = "ab"
        store.write_draft(a, draft)
        d = self.stored(a)
        self.assertEqual((d["future"], d["chapter"]["anchor"], d["chapter"]["file"]), ({"x": 1}, "n1", "B/02 U.notz"))
        d = self.stored(a, "draft.json")
        self.assertEqual((d["format"], d["timer"], d["answers"]["1"]), (
            "notterizmus-attempt/2", 300, {"text": "ab", "revealed": False, "ink": "blue"}))

    def test_an_unreadable_draft_is_kept_aside_and_a_new_one_begins(self):
        a = self.add()
        (a.folder / "draft.json").write_text("{not json", encoding="utf-8")
        draft = store.read_draft(a, now=NOW)
        self.assertEqual(draft.answers, {})
        self.assertEqual(draft.set_aside.name, "draft-unreadable-2026-11-25T12-00-00Z.json")
        self.assertEqual(draft.set_aside.read_text(encoding="utf-8"), "{not json")
        store.write_draft(a, draft)
        self.assertTrue(draft.set_aside.exists())

    def test_a_failed_save_leaves_the_draft_as_it_was(self):
        a = self.add()
        draft = Attempt(answers={1: Answer("saved")})
        store.write_draft(a, draft)
        before = (a.folder / "draft.json").read_bytes()
        draft.answers[1].text = "not saved"
        with mock.patch("notterizmus.files.os.fsync", side_effect=disk_full):
            with self.assertRaises(OSError):
                store.write_draft(a, draft)
        self.assertEqual((a.folder / "draft.json").read_bytes(), before)
        self.assertEqual(self.entries(a.folder), ["draft.json", "report.json", "report.txt"])

    def test_words(self):
        self.assertEqual([store.count_words(t) for t in ("", "  ", "one", "one two\n\n  three\tfour")], [0, 0, 1, 4])


class FinishTest(StoreTest):
    def test_a_finished_attempt_is_kept_and_the_next_one_starts_blank(self):
        a = self.add()
        draft = Attempt(answers={1: Answer("mine", revealed=True)})
        store.write_draft(a, draft, now=NOW - timedelta(minutes=30))
        path, kept = store.finish(a, draft, now=NOW)
        self.assertIsNone(kept)
        self.assertEqual(path, a.folder / "attempts" / "2026-11-25T12-00-00Z.json")
        self.assertFalse((a.folder / "draft.json").exists())
        self.assertEqual(store.read_draft(a), Attempt())
        done = store.read_attempt(path)
        self.assertEqual((done.started, done.finished), (NOW - timedelta(minutes=30), NOW))
        self.assertEqual(done.answers, {1: Answer("mine", revealed=True)})
        self.assertEqual((store.load(a.folder).attempts, store.load(a.folder).has_draft), (1, False))

    def test_attempts_are_listed_newest_first_by_name_only(self):
        a = self.add()
        for minutes in (0, 10, 5):
            store.finish(a, Attempt(answers={1: Answer(str(minutes))}), now=NOW + timedelta(minutes=minutes))
        (a.folder / "attempts" / "2026-11-25T13-00-00Z.json").write_text("{broken", encoding="utf-8")
        (a.folder / "attempts" / ".hidden.tmp").write_text("x", encoding="utf-8")
        (a.folder / "attempts" / "notes.txt").write_text("x", encoding="utf-8")
        listed = store.list_attempts(a)
        self.assertEqual([f.path.name for f in listed], [
            "2026-11-25T13-00-00Z.json", "2026-11-25T12-10-00Z.json", "2026-11-25T12-05-00Z.json",
            "2026-11-25T12-00-00Z.json"])
        self.assertEqual(listed[1].when, NOW + timedelta(minutes=10))
        with self.assertRaises(ValueError):
            store.read_attempt(listed[0].path)
        self.assertEqual(store.read_attempt(listed[1].path).answer(1).text, "10")

    def test_the_last_attempt_is_the_newest_you_finished_that_can_be_read(self):
        """For the question list's "Last time" line (R35b)."""
        a = self.add()
        self.assertIsNone(store.last_attempt(a))
        store.finish(a, Attempt(answers={1: Answer("older")}), now=NOW)
        store.finish(a, Attempt(answers={1: Answer("newer"), 2: Answer(revealed=True)}), now=NOW + timedelta(minutes=5))
        theirs = Attempt(answers={1: Answer("from the laptop")}, origin=store.ELSEWHERE, finished=NOW + timedelta(minutes=8))
        (a.folder / "attempts" / "2026-11-25T12-08-00Z.json").write_text(json.dumps(theirs.to_json()), encoding="utf-8")
        (a.folder / "attempts" / "2026-11-25T12-09-00Z.json").write_text("{broken", encoding="utf-8")
        last = store.last_attempt(a)
        self.assertEqual(last.answers, {1: Answer("newer"), 2: Answer(revealed=True)})
        self.assertEqual(last.finished, NOW + timedelta(minutes=5))

    def test_two_attempts_finished_in_the_same_second_are_both_kept(self):
        a = self.add()
        first, _ = store.finish(a, Attempt(answers={1: Answer("one")}), now=NOW)
        second, _ = store.finish(a, Attempt(answers={1: Answer("two")}), now=NOW)
        self.assertEqual((first.name, second.name), ("2026-11-25T12-00-00Z.json", "2026-11-25T12-00-01Z.json"))

    def test_a_finish_a_crash_stopped_is_completed_when_the_draft_is_next_read(self):
        a = self.add()
        draft = Attempt(answers={1: Answer("almost")})
        draft.finished = NOW
        store.write_draft(a, draft)  # finish() stopped here, before draft.json was moved
        self.assertEqual(store.read_draft(a), Attempt())
        (done,) = store.list_attempts(a)
        self.assertEqual(store.read_attempt(done.path).answer(1).text, "almost")
        self.assertFalse((a.folder / "draft.json").exists())

    def test_a_failed_finish_leaves_the_draft_unfinished(self):
        a = self.add()
        draft = Attempt(answers={1: Answer("mine")})
        store.write_draft(a, draft)
        with mock.patch("notterizmus.files.os.fsync", side_effect=disk_full):
            with self.assertRaises(OSError):
                store.finish(a, draft, now=NOW)
        self.assertIsNone(draft.finished)
        self.assertEqual(store.read_draft(a).answer(1).text, "mine")
        self.assertEqual(store.list_attempts(a), [])


class ConflictTest(StoreTest):
    def test_a_draft_another_computer_changed_is_kept_as_an_attempt(self):
        a = self.add()
        mine = Attempt(answers={1: Answer("mine")})
        store.write_draft(a, mine, now=NOW - timedelta(hours=1))
        self.write(a.folder / "draft.json", Attempt(answers={1: Answer("theirs")}).to_json())
        mine.answers[1].text = "mine, more"
        kept = store.write_draft(a, mine, now=NOW)
        theirs = store.read_attempt(kept)
        self.assertEqual((theirs.origin, theirs.finished, theirs.answer(1).text), (store.ELSEWHERE, NOW, "theirs"))
        self.assertEqual(store.read_draft(a).answer(1).text, "mine, more")
        self.assertIsNone(store.write_draft(a, mine), "once kept, the draft is ours again")

    def test_a_draft_another_computer_started_is_kept_too(self):
        a = self.add()
        mine = store.read_draft(a)
        self.write(a.folder / "draft.json", Attempt(answers={3: Answer("theirs")}).to_json())
        mine.answers[1] = Answer("mine")
        self.assertIsNotNone(store.write_draft(a, mine))

    def test_nothing_is_kept_when_the_other_draft_is_empty_or_the_same(self):
        a = self.add()
        mine = Attempt(answers={1: Answer("same")})
        store.write_draft(a, mine)
        for theirs in (Attempt(), Attempt(answers={1: Answer("same")}, started=NOW)):
            self.write(a.folder / "draft.json", theirs.to_json())
            self.assertIsNone(store.write_draft(a, mine))
        self.assertEqual(store.list_attempts(a), [])

    def test_an_unreadable_draft_from_another_computer_is_kept_aside(self):
        a = self.add()
        mine = Attempt(answers={1: Answer("mine")})
        store.write_draft(a, mine)
        (a.folder / "draft.json").write_text("{conflict", encoding="utf-8")
        self.assertIsNone(store.write_draft(a, mine, now=NOW))
        self.assertEqual(mine.set_aside.read_text(encoding="utf-8"), "{conflict")
        self.assertEqual(store.read_draft(a).answer(1).text, "mine")


class RecoveryTest(StoreTest):
    def test_a_replace_a_crash_stopped_is_completed_when_the_report_is_next_read(self):
        a = self.add(UNGRADED)
        (a.folder / "report.txt").write_bytes(GRADED)  # Replace stopped before report.json
        again = store.load(a.folder)
        self.assertTrue(again.report.graded)
        self.assertEqual(self.stored(a)["report"], parse(GRADED).to_json())

    def test_a_report_an_older_parser_read_is_read_again(self):
        a = self.add()
        d = self.stored(a)
        d["parser_version"], d["report"]["title"] = PARSER_VERSION - 1, "As an older version read it"
        self.write(a.folder / "report.json", d)
        self.assertEqual(store.load(a.folder).report.title, "Design a Rate Limiter")
        self.assertEqual(self.stored(a)["parser_version"], PARSER_VERSION)

    def test_a_report_a_newer_parser_read_is_kept_as_it_read_it(self):
        a = self.add()
        d = self.stored(a)
        d["parser_version"], d["report"]["title"] = PARSER_VERSION + 1, "As a newer version read it"
        self.write(a.folder / "report.json", d)
        self.assertEqual(store.load(a.folder).report.title, "As a newer version read it")

    def test_an_unreadable_report_json_is_rebuilt_from_the_report(self):
        a = self.add(chapter=Link("B/01 T.notz"))
        (a.folder / "report.json").write_text("{", encoding="utf-8")
        again = store.load(a.folder)
        self.assertEqual((again.report, again.chapter), (parse(GRADED), None))
        self.assertEqual(self.stored(a)["report"], parse(GRADED).to_json())

    def test_without_report_txt_report_json_is_enough(self):
        a = self.add()
        (a.folder / "report.txt").unlink()
        self.assertEqual(store.load(a.folder).report, parse(GRADED))

    def test_a_folder_that_is_not_an_assessment_is_listed_apart_with_the_reason(self):
        self.add()
        junk = self.root / "junk"
        junk.mkdir()
        (junk / "report.json").write_text("[]", encoding="utf-8")
        (junk / "report.txt").write_text("hello\n", encoding="utf-8")
        (self.root / "stray.txt").write_text("x", encoding="utf-8")
        found, broken = store.list_all(self.root)
        self.assertEqual([a.id for a in found], [FOLDER])
        ((folder, reason),) = broken
        self.assertEqual(folder, junk)
        self.assertIn("doesn't look like a TopCoding assessment report", reason)

    def test_no_folder_no_assessments(self):
        self.assertEqual(store.list_all(self.root), ([], []))


class ChapterTest(StoreTest):
    def setUp(self):
        super().setUp()
        self.notes = self.root.parent

    def books(self, layout):
        for book, chapters in layout.items():
            (self.notes / book).mkdir(parents=True, exist_ok=True)
            for name in chapters:
                (self.notes / book / f"{name}.notz").write_text("{}", encoding="utf-8")
        return library.scan(self.notes)

    def chapter(self, book, name):
        return self.notes / book / f"{name}.notz"

    def test_a_link_to_a_chapter(self):
        self.assertEqual(store.link_for(self.chapter("Test Book 1", "03 Design a Rate Limiter"), self.notes),
                         Link("Test Book 1/03 Design a Rate Limiter.notz", "Test Book 1", 3, "Design a Rate Limiter"))

    def test_the_chapter_most_like_the_title_is_suggested(self):
        books = self.books({"Test Book 1": [
            "03 Design a Rate Limiter", "06 Design a Key-Value store", "08 Design A URL Shortner",
            "09 Design a web cralwer", "10 Design a notification system", "12 Design A Chat System"],
            "Other": ["01 URL shortening"]})
        expect = {"Design a Rate Limiter": "03 Design a Rate Limiter",
                  "Design a Key-value Store": "06 Design a Key-Value store",
                  "Design a URL Shortener": "08 Design A URL Shortner",
                  "Design a Web Crawler": "09 Design a web cralwer",
                  "Chat System": "12 Design A Chat System",
                  "Design YouTube": None, "Design a News Feed System": None, "": None}
        for title, name in expect.items():
            with self.subTest(title):
                found = store.suggest(title, books)
                self.assertEqual(found and found.path.stem, name)

    def test_a_link_finds_its_chapter_after_another_program_changed_it(self):
        self.books({"Book": ["03 Rate Limiter", "04 Other"], "Elsewhere": []})
        link = store.link_for(self.chapter("Book", "03 Rate Limiter"), self.notes)
        cases = [  # (what another program did to the chapter, where it is now)
            ("nothing", "Book/03 Rate Limiter"),
            ("renamed it", "Book/03 Limiting Rates"),
            ("renumbered it", "Book/07 Rate Limiter"),
            ("moved it to another book", "Elsewhere/01 Rate Limiter"),
            ("deleted it", None),
        ]
        current = self.chapter("Book", "03 Rate Limiter")
        for what, where in cases:
            with self.subTest(what):
                if where is None:
                    current.unlink()
                else:
                    target = self.notes / f"{where}.notz"
                    current.rename(target)
                    current = target
                ch = store.resolve(link, library.scan(self.notes), self.notes)
                self.assertEqual(ch and ch.path, None if where is None else current)

    def test_an_ambiguous_match_is_no_match(self):
        books = self.books({"Book": ["03 Same", "04 Same"], "Other": ["03 Same"]})
        gone = Link("Gone/03 Same.notz", "Gone", 3, "Same")
        self.assertIsNone(store.resolve(gone, books, self.notes))
        renamed = Link("Book/03 Old.notz", "Book", 3, "Old")
        self.assertEqual(store.resolve(renamed, books, self.notes).path.name, "03 Same.notz")

    def test_a_link_found_by_other_means_is_brought_up_to_date(self):
        self.books({"Book": ["03 Renamed"]})
        a = self.add(chapter=Link("Book/03 Before.notz", "Book", 3, "Before"))
        ((again, ch),) = store.resolve_links([a], library.scan(self.notes), self.notes)
        self.assertEqual(ch.path, self.chapter("Book", "03 Renamed"))
        self.assertEqual(again.chapter.file, "Book/03 Renamed.notz")
        self.assertEqual(store.load(a.folder).chapter.file, "Book/03 Renamed.notz")

    def test_links_follow_chapters_the_app_renamed_moved_or_swapped(self):
        self.books({"Book": ["01 One", "02 Two", "03 Three"]})
        one, two, three = (self.add(report_text(t), chapter=store.link_for(self.chapter("Book", n), self.notes))
                           for t, n in (("A", "01 One"), ("B", "02 Two"), ("C", "03 Three")))
        moved = {self.chapter("Book", "01 One"): self.chapter("Book", "02 One"),
                 self.chapter("Book", "02 Two"): self.chapter("Book", "01 Two"),
                 self.chapter("Book", "03 Three"): self.chapter("New Book", "01 Three")}
        changed = store.follow_moves(self.root, moved, self.notes)
        self.assertEqual(len(changed), 3)
        self.assertEqual([store.load(a.folder).chapter for a in (one, two, three)], [
            Link("Book/02 One.notz", "Book", 2, "One"), Link("Book/01 Two.notz", "Book", 1, "Two"),
            Link("New Book/01 Three.notz", "New Book", 1, "Three")])
        self.assertEqual(store.follow_moves(self.root, {self.chapter("Book", "09 X"): self.chapter("Book", "10 X")},
                                            self.notes), [])


class ResultCategoryTest(unittest.TestCase):
    """A question's score in TopCoding's colors, as its report page gives them (read from
    report 24 on 2026-11-26): 0.8 and up good, 0.5 and up partial, below that poor, which
    includes an unanswered question (scored 0); an ungraded question has none."""

    def category(self, got, out_of="1"):
        return store.result_category(Points(got, out_of))

    def check(self, cases):
        for got, out_of, expected in cases:
            with self.subTest(score=f"{got} / {out_of}"):
                self.assertEqual(self.category(got, out_of), expected)

    def test_a_score_on_a_boundary_takes_the_better_color(self):
        self.check([("0.8", "1", store.GOOD), ("0.80", "1", store.GOOD), ("0.5", "1", store.PARTIAL),
                    ("0.50", "1", store.PARTIAL)])

    def test_a_score_just_below_a_boundary_takes_the_lower_one(self):
        self.check([("0.79", "1", store.PARTIAL), ("0.7999", "1", store.PARTIAL), ("0.49", "1", store.POOR),
                    ("0.4999", "1", store.POOR)])

    def test_whole_and_fractional_scores(self):
        self.check([("1", "1", store.GOOD), ("1.0", "1", store.GOOD), ("0.95", "1", store.GOOD),
                    ("0.85", "1", store.GOOD), ("0.75", "1", store.PARTIAL), ("0.6", "1", store.PARTIAL),
                    ("0.25", "1", store.POOR), ("0.05", "1", store.POOR), ("0", "1", store.POOR),
                    ("0.00", "1", store.POOR)])

    def test_a_decimal_comma_and_scores_out_of_more_than_one(self):
        # 2.4 / 3 is 0.8 exactly, which binary floating point makes 0.7999999999999999
        self.check([("0,8", "1", store.GOOD), ("0,45", "1", store.POOR), ("1.6", "2", store.GOOD),
                    ("2.4", "3", store.GOOD), ("1.5", "3", store.PARTIAL), ("1.4", "3", store.POOR)])

    def test_an_ungraded_question_or_a_score_no_report_has_gets_no_color(self):
        self.assertIsNone(store.result_category(None))
        self.check([("1", "0", None), ("n/a", "1", None), ("", "1", None)])

    def test_an_unanswered_question_is_poor_once_graded_and_has_no_color_before(self):
        graded, ungraded = parse(GRADED).questions[7], parse(UNGRADED).questions[7]
        self.assertEqual((graded.number, graded.answer, str(graded.score)), (8, None, "0 / 1"))
        self.assertEqual(store.result_category(graded.score), store.POOR)
        self.assertEqual((ungraded.number, ungraded.answer, ungraded.score), (8, None, None))
        self.assertIsNone(store.result_category(ungraded.score))


class FinalCategoryTest(unittest.TestCase):
    """A report's final result in TopCoding's colors: by its percentage to one decimal, as
    the page shows it, 80 and up good, 65 and up partial, below that poor; none while it is
    ungraded (the page's blue)."""

    def check(self, cases):
        for got, out_of, percent, expected in cases:
            with self.subTest(result=f"{got} / {out_of} ({percent}%)"):
                report = Report("A Report", final_result=Points(got, out_of), final_percent=percent)
                self.assertEqual(store.final_category(report), expected)

    def test_the_files_percentage_on_and_just_below_each_boundary(self):
        self.check([("15.20", "19", "80.0", store.GOOD), ("15.18", "19", "79.9", store.PARTIAL),
                    ("12.35", "19", "65.0", store.PARTIAL), ("12.33", "19", "64.9", store.POOR),
                    ("19", "19", "100.0", store.GOOD), ("0", "19", "0.0", store.POOR), ("0,00", "19", "0,0", store.POOR)])

    def test_without_the_files_percentage_it_is_worked_out_and_rounded_as_the_page_does(self):
        # 15.195 / 19 is 79.97 %, which the page shows and colors as 80.0
        self.check([("15.195", "19", None, store.GOOD), ("15.19", "19", None, store.PARTIAL),
                    ("12.34", "19", None, store.POOR), ("13", "20", None, store.PARTIAL)])

    def test_the_fixtures_result_and_an_ungraded_report(self):
        self.assertEqual(store.final_category(parse(GRADED)), store.POOR)  # 7.10 / 19 (37.4%)
        self.assertIsNone(store.final_category(parse(UNGRADED)))
        self.check([("1", "0", None, None), ("7.10", "19", "n/a", None)])


if __name__ == "__main__":
    unittest.main()
