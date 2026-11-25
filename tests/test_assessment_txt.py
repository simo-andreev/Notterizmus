"""TopCoding's assessment report as a text file: the fixtures are real downloads of one
report, graded and (before TopCoding had graded it) ungraded; the rest are built the way
the report page's own script writes the file (export() below)."""
from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from notterizmus.assessment_txt import MAX_BYTES, Points, Report, ReportError, parse, parse_completed

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GRADED = FIXTURES / "assessment_design_a_rate_limiter.txt"
UNGRADED = FIXTURES / "assessment_design_a_rate_limiter_ungraded.txt"

HEADER = (("Difficulty", "easy"), ("Completed", "23.11.2026 г., 19:05:51 ч."), ("Time allocated", "60 min"),
          ("Time spent", "12 min"), ("Attempt", "1 of 1"))


def export(*questions, title="Design a Thing", header=HEADER, final=None):
    """A report's text as TopCoding's page writes it. Each question is a dict: q (the
    question), u (your answer), a (the sample answer), r (the score, once graded) and
    f (the feedback)."""
    s = [f"{title} - Online Assessment", "=" * 60, *(f"{k}: {v}" for k, v in header)]
    if final:
        s.append(f"Final result: {final}")
    s.append("")
    for n, q in enumerate(questions, start=1):
        s += [f"Question {n}", "-" * 60, f"Q: {q.get('q') or 'N/A'}", "", "Your answer:",
              q.get("u") or "No answer provided", ""]
        if q.get("a"):
            s += ["Sample answer:", q["a"], ""]
        if "r" in q:
            s.append(f"Score: {q['r']} / 1")
            if q.get("f"):
                s += ["Feedback:", q["f"]]
        s.append("")
    return "\n".join(s)


def error(data):
    """The ReportError data raises."""
    try:
        parse(data)
    except ReportError as e:
        return e
    raise AssertionError("no ReportError")


ONE = {"q": "Why?", "u": "Because.", "a": "Since."}


class GradedReportTest(unittest.TestCase):
    """The report as downloaded once TopCoding had graded it."""

    @classmethod
    def setUpClass(cls):
        cls.report = parse(GRADED.read_bytes())
        cls.q = {q.number: q for q in cls.report.questions}

    def test_header(self):
        r = self.report
        self.assertEqual(r.title, "Design a Rate Limiter")
        self.assertEqual(r.difficulty, "easy")
        self.assertEqual(r.completed, "23.11.2026 г., 19:05:51 ч.")
        self.assertEqual(r.completed_at, datetime(2026, 11, 23, 19, 5, 51))
        self.assertEqual((r.time_allocated, r.time_spent, r.attempt), ("60 min", "60 min", "1 of 1"))
        self.assertEqual(r.final_result, Points("7.10", "19"))
        self.assertEqual(r.final_percent, "37.4")
        self.assertEqual(r.extra_header, {})
        self.assertTrue(r.graded)

    def test_every_question_in_order(self):
        self.assertEqual([q.number for q in self.report.questions], list(range(1, 20)))
        self.assertEqual(self.q[1].prompt, "What is the purpose of a rate limiter in a distributed system?")
        self.assertEqual(self.q[13].prompt, "What’s the role of approximate counting algorithms like Bloom filters "
                                            "or Count-Min Sketch in rate limiting?")

    def test_fractional_scores(self):
        self.assertEqual([q.score.got for q in self.report.questions],
                         ["1", "0.75", "1", "0.95", "0.75", "0.85", "0.85", "0", "0.95"] + ["0"] * 10)
        self.assertEqual({q.score.out_of for q in self.report.questions}, {"1"})
        self.assertAlmostEqual(sum(q.score.value for q in self.report.questions), 7.10)

    def test_no_feedback_where_the_score_is_0(self):
        self.assertEqual([q.number for q in self.report.questions if q.feedback is None], [8] + list(range(10, 20)))
        self.assertTrue(self.q[6].feedback.startswith("Excellent answer! You correctly identified the two main"))

    def test_answers_keep_indentation_blank_lines_and_list_markers(self):
        a = self.q[2].answer
        self.assertTrue(a.startswith("A rate limiter can be implemented:\n1) At client-side:\n    pro: Cheap"))
        self.assertIn("per platform\n\n2) Server-side:\n    > Can be in many", a)
        self.assertTrue(a.endswith("    con: Needs storage and compute to run"), "the spaces-only line after it is dropped")
        self.assertIn("\n\nThe purpose of which, in turn, is to:\n  - avoid malicious use", self.q[1].answer)
        self.assertIn("set for each user. \nThat region's", self.q[7].answer, "spaces at the end of a line stay")

    def test_no_answer_provided_means_no_answer(self):
        self.assertEqual([q.number for q in self.report.questions if q.answer is None], [8] + list(range(10, 20)))
        self.assertTrue(all(q.sample for q in self.report.questions))


class UngradedReportTest(unittest.TestCase):
    """The same report, downloaded before TopCoding had graded it: no Final result, Score
    or Feedback lines."""

    def test_reads_as_the_graded_one_without_the_grading(self):
        ungraded, graded = parse(UNGRADED.read_bytes()), parse(GRADED.read_bytes())
        self.assertFalse(ungraded.graded)
        self.assertIsNone(ungraded.final_result)
        self.assertIsNone(ungraded.final_percent)
        self.assertEqual([(q.score, q.feedback) for q in ungraded.questions], [(None, None)] * 19)
        self.assertEqual([(q.number, q.prompt, q.answer, q.sample) for q in ungraded.questions],
                         [(q.number, q.prompt, q.answer, q.sample) for q in graded.questions])

    def test_has_the_same_key_as_the_graded_one(self):
        self.assertEqual(parse(UNGRADED.read_bytes()).key, parse(GRADED.read_bytes()).key)


class ToleranceTest(unittest.TestCase):
    def same(self, text, expected=None):
        expected = expected or parse(GRADED.read_bytes())
        self.assertEqual(parse(text).to_json(), expected.to_json())

    def test_windows_and_old_mac_line_endings(self):
        text = GRADED.read_text(encoding="utf-8")
        self.same(text.replace("\n", "\r\n").encode("utf-8"))
        self.same(text.replace("\n", "\r").encode("utf-8"))

    def test_a_byte_order_mark(self):
        self.same(b"\xef\xbb\xbf" + GRADED.read_bytes())

    def test_extra_blank_lines_and_spaces_around_labels(self):
        plain = export({"q": "Why?", "u": "Because.\n\n  - indented", "a": "Since.", "r": "0.5", "f": "Fine."},
                       final="0.5 / 1 (50.0%)")
        loose = ("\n\nDesign a Thing - Online Assessment\n" + "=" * 60 + "  \n"
                 + "\n".join(f"{k}: {v}" for k, v in HEADER) + "\nFinal result: 0.5 / 1 (50.0%)\n\n\n\n"
                 "Question 1  \n" + "-" * 60 + "\nQ: Why?\n\n\n Your answer: \n\nBecause.\n\n  - indented\n\n\n\n"
                 "Sample answer:  \nSince.\n\n\nScore: 0.5 / 1 \n\nFeedback: \nFine.\n\n\n")
        self.same(loose, parse(plain))

    def test_an_empty_answer_is_no_answer(self):
        text = export({"q": "Why?", "u": "x", "a": "Since."}).replace("Your answer:\nx\n", "Your answer:\n\n")
        self.assertIsNone(parse(text).questions[0].answer)

    def test_feedback_may_be_missing_after_any_score(self):
        r = parse(export({**ONE, "r": "0.5"}, final="0.5 / 1 (50.0%)"))
        self.assertEqual((str(r.questions[0].score), r.questions[0].feedback), ("0.5 / 1", None))

    def test_feedback_on_the_label_line(self):
        text = export({**ONE, "r": "1", "f": "Good."}).replace("Feedback:\nGood.", "Feedback: Good.")
        self.assertEqual(parse(text).questions[0].feedback, "Good.")

    def test_a_question_over_several_lines(self):
        r = parse(export({"q": "First line\n  second line", "u": "A", "a": "S"}))
        self.assertEqual(r.questions[0].prompt, "First line\n  second line")

    def test_an_answer_that_quotes_the_labels_stays_whole(self):
        answer = "My notes:\n\nSample answer:\nnot really\n\nQuestion 2\nstill mine\n\nScore: 3 / 10"
        r = parse(export({"q": "Why?", "u": answer, "a": "Since.", "r": "0.25", "f": "Hm."}, final="0.25 / 1 (25.0%)"))
        q = r.questions[0]
        self.assertEqual((q.answer, q.sample, q.score, q.feedback), (answer, "Since.", Points("0.25", "1"), "Hm."))

    def test_header_lines_this_version_does_not_know_are_kept(self):
        r = parse(export(ONE, header=(("Attempt", "2 of 3"), ("Topic group", "Rate limiting"))))
        self.assertEqual(r.extra_header, {"Topic group": "Rate limiting"})
        self.assertEqual((r.attempt, r.difficulty, r.completed, r.completed_at), ("2 of 3", "", "", None))

    def test_a_title_without_the_usual_ending(self):
        text = export(ONE).replace("Design a Thing - Online Assessment", "Design a Thing")
        self.assertEqual(parse(text).title, "Design a Thing")

    def test_scores_with_a_decimal_comma(self):
        r = parse(export({**ONE, "r": "0,5"}, final="0,5 / 1 (50,0%)"))
        self.assertEqual((r.questions[0].score.value, r.final_percent), (0.5, "50,0"))


class CompletedTest(unittest.TestCase):
    """Completed is written by the browser in its own language."""

    def test_forms(self):
        at = datetime(2026, 11, 23, 19, 5, 51)
        for text in ("23.11.2026 г., 19:05:51 ч.", "23.11.2026, 19:05:51", "23.11.2026 19:05:51",
                     "23/11/2026, 19:05:51", "11/23/2026, 7:05:51 PM", "11/23/2026, 7:05:51 p.m.",
                     "2026-11-23 19:05:51", "2026-11-23T19:05:51"):
            self.assertEqual(parse_completed(text), at, text)
        self.assertEqual(parse_completed("11/23/2026, 12:05:51 AM"), datetime(2026, 11, 23, 0, 5, 51))
        self.assertEqual(parse_completed("11/23/2026, 12:05:51 PM"), datetime(2026, 11, 23, 12, 5, 51))
        self.assertEqual(parse_completed("23.11.2026 г., 19:05 ч."), datetime(2026, 11, 23, 19, 5))

    def test_unknown_forms_keep_only_the_text(self):
        for text in ("Sunday evening", "31.02.2026, 10:00:00", "", "23.11.2026"):
            self.assertIsNone(parse_completed(text), text)
        r = parse(export(ONE, header=(("Completed", "Sunday evening"),)))
        self.assertEqual((r.completed, r.completed_at), ("Sunday evening", None))
        self.assertEqual(r.key, "design a thing|Sunday evening")

    def test_the_key_is_the_same_in_any_language(self):
        bg = parse(export(ONE))
        us = parse(export(ONE, header=(("Completed", "11/23/2026, 7:05:51 PM"),)))
        self.assertEqual(bg.key, us.key)
        later = parse(export(ONE, header=(("Completed", "23.11.2026 г., 19:05:52 ч."),)))
        self.assertNotEqual(bg.key, later.key)

    def test_without_a_completion_time_the_answers_tell_reports_apart(self):
        a, b = parse(export(ONE, header=())), parse(export({**ONE, "u": "Other."}, header=()))
        self.assertNotEqual(a.key, b.key)
        self.assertEqual(a.key, parse(export(ONE, header=())).key)


class MalformedTest(unittest.TestCase):
    """Anything else is refused whole, with the line (and question) to look at."""

    def test_not_a_report(self):
        self.assertEqual(str(error(b"")), "The file is empty")
        e = error(b'{"format": "notterizmus/1", "book": "B"}\n')
        self.assertEqual(e.line, 1)
        self.assertIn("doesn't look like a TopCoding assessment report", str(e))
        e = error(b"Some notes\nabout rate limiters\n")
        self.assertEqual((e.line, e.question), (2, None))
        self.assertTrue(str(e).startswith("Line 2: this doesn't look like"))

    def test_not_utf8_binary_or_too_large(self):
        e = error(export(ONE).encode("cp1251"))
        self.assertEqual(e.line, 4)  # "г." of the Completed line
        self.assertIn("UTF-8", str(e))
        self.assertIn("binary", str(error(export(ONE).replace("Because", "Bec\x00ause").encode("utf-8"))))
        self.assertIn("larger than 5 MB", str(error(b"x" * (MAX_BYTES + 1))))

    def test_a_header_line_that_is_not_a_field(self):
        text = export(ONE).replace("Attempt: 1 of 1", "Attempt 1 of 1")
        e = error(text)
        self.assertEqual((e.line, e.question), (7, None))

    def test_no_questions(self):
        e = error("Design a Thing - Online Assessment\n" + "=" * 60 + "\nAttempt: 1 of 1\n\n")
        self.assertIn("no questions", str(e))

    def test_something_else_before_the_first_question(self):
        text = export(ONE).replace("Question 1\n", "Hello\n\nQuestion 1\n")
        e = error(text)
        self.assertEqual(e.line, 9)
        self.assertIn("expected “Question 1”, found “Hello”", str(e))

    def test_question_numbers_must_count_up(self):
        text = export(ONE, ONE, ONE).replace("Question 2\n", "Question 3\n", 1)
        e = error(text)
        self.assertIn("question 2 is missing", str(e))
        self.assertEqual(text.split("\n")[e.line - 1], "Question 3")
        e = error(export(ONE, ONE).replace("Question 2\n", "Question 1\n"))
        self.assertIn("question 1 comes again after question 1", str(e))

    def test_a_question_without_its_text_or_answer_label(self):
        text = export(ONE, ONE).replace("Q: Why?\n\nYour answer:\nBecause.\n\nSample answer:\nSince.\n\n\nQuestion 2",
                                        "Q: Why?\n\nBecause.\n\nSample answer:\nSince.\n\n\nQuestion 2")
        e = error(text)
        self.assertEqual((e.line, e.question), (11, 1))
        self.assertEqual(str(e), "Line 11, question 1: there's no “Your answer:” line after the question")
        e = error(export(ONE, ONE).replace("Q: Why?\n\nYour answer:\nBecause.\n\nSample answer:\nSince.\n\n\n"
                                           "Question 2", "Your answer:\nBecause.\n\n\nQuestion 2"))
        self.assertEqual(e.question, 1)
        self.assertIn("expected the question, “Q: …”", str(e))

    def test_scores_out_of_range_or_not_numbers(self):
        e = error(export({**ONE, "r": "2"}, final="2 / 1 (200%)"))
        self.assertIn("out of range", str(e))
        e = error(export({**ONE, "r": "2"}))
        self.assertEqual((e.question, "out of range" in str(e)), (1, True))
        e = error(export({**ONE, "r": "high"}, final="0 / 1 (0%)"))
        self.assertEqual(e.question, 1)
        self.assertIn("isn't a score like “Score: 0.95 / 1”", str(e))
        self.assertIn("isn't a final result", str(error(export(ONE, final="lots"))))

    def test_a_graded_report_has_a_score_for_every_question(self):
        e = error(export({**ONE, "r": "1"}, ONE, {**ONE, "r": "0"}))
        self.assertEqual(e.question, 2)
        self.assertIn("there's no score, though the report is graded", str(e))

    def test_the_final_result_counts_the_questions(self):
        e = error(export({**ONE, "r": "1"}, {**ONE, "r": "0"}, final="1 / 3 (33.3%)"))
        self.assertEqual(e.line, 8)
        self.assertIn("out of 3 points, but the file's 2 questions are worth 2", str(e))


class CutShortTest(unittest.TestCase):
    """A file cut short is never imported in part."""

    def test_every_cut_of_the_graded_report_is_refused(self):
        data = GRADED.read_bytes()
        lines = data.split(b"\n")
        cuts = {len(b"\n".join(lines[:n])) + 1 for n in range(len(lines) - 1)}  # after each line break
        cuts |= set(range(1, len(data) - 1, 97))  # and in the middle of lines
        for cut in sorted(cuts - {len(data)}):
            with self.subTest(cut=cut):
                self.assertRaises(ReportError, parse, data[:cut])

    def test_the_ungraded_report_cut_inside_its_last_question(self):
        text = UNGRADED.read_text(encoding="utf-8")
        within_answer = text[:text.index("Sample answer:\nEnsure each new instance")]
        e = error(within_answer)
        self.assertEqual(e.question, 19)
        self.assertIn("there's no sample answer, though every other question has one", str(e))
        e = error(text[:text.index("registers itself")])
        self.assertIn("stops in the middle of a line", str(e))
        self.assertEqual(e.question, 19)

    def test_a_cut_names_the_question_it_falls_in(self):
        text = GRADED.read_text(encoding="utf-8")
        e = error(text[:text.index("Question 7") + 40])
        self.assertEqual(e.question, 7)


class StoredTest(unittest.TestCase):
    def test_round_trip(self):
        for path in (GRADED, UNGRADED):
            report = parse(path.read_bytes())
            self.assertEqual(Report.from_json(report.to_json()), report)

    def test_data_that_is_not_a_report(self):
        good = parse(export(ONE)).to_json()
        for bad in ({}, {"title": 1, "questions": []}, {**good, "questions": None},
                    {**good, "questions": [{"number": "1", "prompt": "x"}]},
                    {**good, "final_result": {"got": "x", "out_of": "1"}}, []):
            with self.subTest(bad=bad):
                self.assertRaises(ValueError, Report.from_json, bad)


if __name__ == "__main__":
    unittest.main()
