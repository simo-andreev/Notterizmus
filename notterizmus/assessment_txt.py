"""TopCoding's assessment report as a text file (no GTK).

On a TopCoding assessment report page, Download .txt saves a file that the page writes
itself (its script, read on 2026-11-25 from report 24):

    Design a Rate Limiter - Online Assessment
    ============================================================
    Difficulty: easy
    Completed: 23.11.2026 г., 19:05:51 ч.
    Time allocated: 60 min
    Time spent: 60 min
    Attempt: 1 of 1
    Final result: 7.10 / 19 (37.4%)

    Question 1
    ------------------------------------------------------------
    Q: What is the purpose of a rate limiter in a distributed system?

    Your answer:
    To limit the number of requests …

    Sample answer:
    A rate limiter controls …

    Score: 0.95 / 1
    Feedback:
    Excellent answer! …

- Difficulty, Completed and the two times are left out when TopCoding has no value for
  them. Completed is the browser's toLocaleString(), so its form depends on the browser's
  language: "23.11.2026 г., 19:05:51 ч." in Bulgarian, "11/23/2026, 7:05:51 PM" in US
  English.
- "No answer provided" stands for no answer. Sample answer is left out for a question
  without one.
- Graded and ungraded reports: a report downloaded before TopCoding has graded the answers
  has no "Final result" line and no "Score" or "Feedback" in its questions. In a graded
  one every question has a Score; Feedback is left out where there is none (a score of 0).

parse() reads both kinds. Anything else raises ReportError, naming the line and the
question: a report is imported whole or not at all.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

TITLE_SUFFIX = " - Online Assessment"
NO_ANSWER = "No answer provided"
MAX_BYTES = 5 * 1024 * 1024  # a real report is about 16 KB
PARSER_VERSION = 1  # raise it when parse() reads a report differently: stored reports are read again

_TITLE_RULE = re.compile(r"^={10,}$")
_QUESTION_RULE = re.compile(r"^-{10,}$")
_QUESTION = re.compile(r"^Question\s+(\d+)$")
_NUMBER = r"(\d+(?:[.,]\d+)?)"
_SCORE = re.compile(rf"^Score:\s*{_NUMBER}\s*/\s*{_NUMBER}$", re.IGNORECASE)
_FINAL = re.compile(rf"^{_NUMBER}\s*/\s*{_NUMBER}(?:\s*\(\s*{_NUMBER}\s*%\s*\))?$")
# Completed, as browsers write a date and time in different languages
_DOTTED = re.compile(r"^(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})(?:\s*г\.)?,?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s*ч\.)?$")
_SLASHED = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4}),?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s*([AaPp])\.?\s?[Mm]\.?)?$")
_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})[T ,]\s*(\d{1,2}):(\d{2})(?::(\d{2}))?$")


class ReportError(ValueError):
    """Why a file can't be imported as a TopCoding report, and where: line (from 1) and
    question (its number), each None where it doesn't apply."""

    def __init__(self, reason, line=None, question=None):
        self.reason, self.line, self.question = reason, line, question
        where = ", ".join(p for p in (f"line {line}" if line else "", f"question {question}" if question else "") if p)
        text = f"{where}: {reason}" if where else reason
        super().__init__(text[:1].upper() + text[1:])


@dataclass(frozen=True)
class Points:
    """A score as the report writes it: got "0.95" out of "1"."""
    got: str
    out_of: str

    def __str__(self):
        return f"{self.got} / {self.out_of}"

    @property
    def value(self):
        return _number(self.got)

    @property
    def maximum(self):
        return _number(self.out_of)


@dataclass
class Question:
    number: int
    prompt: str
    answer: str | None = None    # None: "No answer provided"
    sample: str | None = None    # None: the report has no sample answer for it
    score: Points | None = None  # None in an ungraded report
    feedback: str | None = None  # None: no feedback (ungraded, or a score of 0)


@dataclass
class Report:
    title: str
    questions: list = field(default_factory=list)
    difficulty: str = ""
    completed: str = ""                  # as the file writes it
    completed_at: datetime | None = None  # the same, read; None if its form is unknown
    time_allocated: str = ""             # "60 min"
    time_spent: str = ""
    attempt: str = ""                    # "1 of 1": TopCoding's attempt, not a practice attempt
    final_result: Points | None = None   # None until TopCoding has graded the answers
    final_percent: str | None = None     # "37.4"
    extra_header: dict = field(default_factory=dict)  # header lines this version doesn't know

    @property
    def graded(self):
        return self.final_result is not None or any(q.score is not None for q in self.questions)

    @property
    def key(self):
        """What tells two reports apart: the title and when the assessment was completed.
        A file downloaded again, graded or not, has the same key. Without a completion
        time, the questions and your answers stand in for it."""
        if self.completed_at is not None:
            when = self.completed_at.isoformat(timespec="seconds")
        elif self.completed.strip():
            when = " ".join(self.completed.split())
        else:
            text = "\n".join(f"{q.prompt}\n{q.answer or ''}" for q in self.questions)
            when = "answers:" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
        return f"{self.title.casefold()}|{when}"

    def to_json(self):
        return {
            "title": self.title,
            "difficulty": self.difficulty,
            "completed": self.completed,
            "completed_at": self.completed_at.isoformat(timespec="seconds") if self.completed_at else None,
            "time_allocated": self.time_allocated,
            "time_spent": self.time_spent,
            "attempt": self.attempt,
            "final_result": None if self.final_result is None else {
                "got": self.final_result.got, "out_of": self.final_result.out_of, "percent": self.final_percent},
            "extra_header": dict(self.extra_header),
            "questions": [{
                "number": q.number, "prompt": q.prompt, "answer": q.answer, "sample": q.sample,
                "score": None if q.score is None else {"got": q.score.got, "out_of": q.score.out_of},
                "feedback": q.feedback,
            } for q in self.questions],
        }

    @classmethod
    def from_json(cls, d):
        """Raises ValueError for data that isn't a report."""
        try:
            final = d.get("final_result")
            report = cls(
                title=_text(d["title"]), difficulty=_text(d.get("difficulty")), completed=_text(d.get("completed")),
                completed_at=datetime.fromisoformat(d["completed_at"]) if d.get("completed_at") else None,
                time_allocated=_text(d.get("time_allocated")), time_spent=_text(d.get("time_spent")),
                attempt=_text(d.get("attempt")),
                final_result=None if final is None else _points(final),
                final_percent=None if final is None else _text(final.get("percent"), none=True),
                extra_header={_text(k): _text(v) for k, v in (d.get("extra_header") or {}).items()},
            )
            for q in d["questions"]:
                report.questions.append(Question(
                    number=_int(q["number"]), prompt=_text(q["prompt"]), answer=_text(q.get("answer"), none=True),
                    sample=_text(q.get("sample"), none=True),
                    score=None if q.get("score") is None else _points(q["score"]),
                    feedback=_text(q.get("feedback"), none=True)))
            return report
        except (AttributeError, KeyError, TypeError) as e:
            raise ValueError("this isn't a stored assessment report") from e


def _text(value, none=False):
    if value is None:
        if none:
            return None
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{value!r} isn't text")
    return value


def _int(value):
    if type(value) is not int:
        raise TypeError(f"{value!r} isn't a whole number")
    return value


def _points(d):
    got, out_of = _text(d["got"]), _text(d["out_of"])
    _number(got)
    _number(out_of)
    return Points(got, out_of)


def _number(text):
    try:
        return float(text.replace(",", "."))
    except ValueError as e:
        raise TypeError(f"{text!r} isn't a number") from e


# -- reading a report ---------------------------------------------------------------------

def parse(data):
    """The report in data (the file's bytes, or its text). Raises ReportError."""
    text = _decode(data) if isinstance(data, (bytes, bytearray)) else str(data)
    if text.startswith("﻿"):
        text = text[1:]
    whole = text.endswith(("\n", "\r"))  # a real report ends with a line break
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in text:
        raise ReportError("this is a binary file, not a TopCoding report")
    lines = text.split("\n")
    if whole:
        lines.pop()  # the last line break ends the last line; no line follows it

    i = _skip_blank(lines, 0)
    if i >= len(lines):
        raise ReportError("the file is empty")
    if i + 1 >= len(lines) or not _TITLE_RULE.match(lines[i + 1].strip()):
        raise ReportError("this doesn't look like a TopCoding assessment report: its first line should be "
                          "the title, underlined with a line of “=”", line=min(i + 2, len(lines)))
    title_line = lines[i].strip()
    title = title_line[:-len(TITLE_SUFFIX)].strip() if title_line.endswith(TITLE_SUFFIX) else title_line
    report = Report(title=title or "Assessment")

    j, final_line = i + 2, None
    while j < len(lines) and lines[j].strip():
        if _header_field(report, lines[j].strip(), j + 1):
            final_line = j + 1
        j += 1

    headings = [(k, int(m.group(1))) for k in range(j, len(lines) - 1)
                if (m := _QUESTION.match(lines[k].strip())) and _QUESTION_RULE.match(lines[k + 1].strip())]
    first = _skip_blank(lines, j)
    if not headings:
        raise ReportError("the report has no questions: none starts with “Question 1” underlined with a line of “-”",
                          line=min(first, len(lines) - 1) + 1)
    if first != headings[0][0]:
        raise ReportError(f"expected “Question 1”, found “{_short(lines[first])}”", line=first + 1)
    for n, (k, number) in enumerate(headings, start=1):
        if number != n:
            reason = (f"question {n} is missing: question {number} comes after question {n - 1}" if number > n
                      else f"question {number} comes again after question {n - 1}")
            raise ReportError(reason, line=k + 1)
    if not whole:
        raise ReportError("the file stops in the middle of a line, so it may have been cut short. "
                          "Download the report again", line=len(lines), question=headings[-1][1])

    parts = []
    for n, (k, number) in enumerate(headings):
        end = headings[n + 1][0] if n + 1 < len(headings) else len(lines)
        parts.append(_question(lines, k + 2, end, number))
    report.questions = [q for q, _where in parts]
    _check_complete(report, parts, final_line)
    return report


def _decode(data):
    if len(data) > MAX_BYTES:
        raise ReportError("the file is larger than 5 MB, far too large for a TopCoding report")
    data = bytes(data)
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ReportError("this isn't UTF-8 text, as TopCoding's reports are", line=data[:e.start].count(b"\n") + 1) from e


def _header_field(report, line, number):
    """Read one "Name: value" line of the header into report; true for the final result."""
    name, sep, value = line.partition(":")
    name, value = name.strip(), value.strip()
    if not sep or not name:
        raise ReportError(f"“{_short(line)}” should be a “Name: value” line of the report's header", line=number)
    key = name.casefold()
    if key == "difficulty":
        report.difficulty = value
    elif key == "completed":
        report.completed, report.completed_at = value, parse_completed(value)
    elif key == "time allocated":
        report.time_allocated = value
    elif key == "time spent":
        report.time_spent = value
    elif key == "attempt":
        report.attempt = value
    elif key == "final result":
        m = _FINAL.match(value)
        if not m:
            raise ReportError(f"“{_short(value)}” isn't a final result like “7.10 / 19 (37.4%)”", line=number)
        report.final_result, report.final_percent = Points(m.group(1), m.group(2)), m.group(3)
        if not 0 < report.final_result.maximum or report.final_result.value > report.final_result.maximum:
            raise ReportError(f"the final result “{report.final_result}” is out of range", line=number)
        return True
    else:
        report.extra_header[name] = value
    return False


def _question(lines, start, end, number):
    """The question whose lines, after its heading, run from start to end. Returns it and
    where its parts are, for the checks that compare questions."""
    i = _skip_blank(lines, start, end)
    if i >= end or not lines[i].lstrip().startswith("Q:"):
        found = f"found “{_short(lines[i])}”" if i < end else "the file ends there"
        raise ReportError(f"expected the question, “Q: …”; {found}", line=i + 1 if i < end else start, question=number)
    asked = next((k for k in range(i + 1, end) if _is(lines[k], "Your answer:")), None)
    if asked is None:
        raise ReportError("there's no “Your answer:” line after the question", line=i + 1, question=number)
    prompt = _section([lines[i].lstrip()[2:].lstrip()] + lines[i + 1:asked]) or "N/A"

    # The last "Sample answer:" after a blank line, so that an answer quoting it stays whole;
    # then the score, which only TopCoding's own text (the sample answer) comes before.
    sample_at = next((k for k in range(end - 1, asked, -1)
                      if _is(lines[k], "Sample answer:") and (k - 1 == asked or not lines[k - 1].strip())), None)
    after = (asked if sample_at is None else sample_at) + 1
    score_at = next((k for k in range(after, end) if _is_score_line(lines, k, end)), None)
    answer_end = sample_at if sample_at is not None else (score_at if score_at is not None else end)
    answer = _section(lines[asked + 1:answer_end])
    sample = None if sample_at is None else _section(lines[sample_at + 1:score_at if score_at is not None else end])
    score = feedback = None
    if score_at is not None:
        m = _SCORE.match(lines[score_at].strip())
        score = Points(m.group(1), m.group(2))
        if not 0 < score.maximum or score.value > score.maximum:
            raise ReportError(f"the score “{score}” is out of range", line=score_at + 1, question=number)
        label = _skip_blank(lines, score_at + 1, end)
        if label < end:
            inline = lines[label].strip()[len("Feedback:"):].strip()
            feedback = _section(([inline] if inline else []) + lines[label + 1:end])
    bad_score = next((k for k in range(after, end) if score_at is None and not lines[k - 1].strip()
                      and lines[k].strip().casefold().startswith("score:")), None)
    question = Question(number, prompt, answer=None if answer.strip() in ("", NO_ANSWER) else answer,
                        sample=sample or None, score=score, feedback=feedback or None)
    last = max(k for k in range(i, end) if lines[k].strip()) + 1
    return question, {"line": i + 1, "last": last, "bad_score": None if bad_score is None else bad_score + 1}


def _is_score_line(lines, k, end):
    """Whether line k is the score: "Score: 0.95 / 1" after a blank line, with nothing but
    the feedback after it."""
    if not _SCORE.match(lines[k].strip()) or lines[k - 1].strip():
        return False
    label = _skip_blank(lines, k + 1, end)
    return label >= end or lines[label].strip().casefold().startswith("feedback:")


def _check_complete(report, parts, final_line):
    """Checks across questions: a graded report has a score for each question, as many
    points as its final result says, and a last question as complete as the others. A
    file cut short fails one of them."""
    questions = report.questions
    if report.graded:
        for q, where in parts:
            if q.score is None:
                if where["bad_score"]:
                    raise ReportError("this isn't a score like “Score: 0.95 / 1”", line=where["bad_score"], question=q.number)
                raise ReportError("there's no score, though the report is graded: the file may have been cut short "
                                  "or changed", line=where["last"], question=q.number)
    if report.final_result is not None:
        points = sum(q.score.maximum for q in questions)
        if abs(points - report.final_result.maximum) > 1e-6:
            raise ReportError(f"the final result is out of {report.final_result.out_of} points, but the file's "
                              f"{len(questions)} question{'s' if len(questions) != 1 else ''} are worth {points:g}: "
                              "it may have been cut short. Download the report again", line=final_line)
    last, where = parts[-1]
    if len(questions) > 1 and last.sample is None and all(q.sample is not None for q in questions[:-1]):
        raise ReportError("there's no sample answer, though every other question has one: the file may have been "
                          "cut short. Download the report again", line=where["last"], question=last.number)


def parse_completed(text):
    """The date and time in the Completed line, as the browser wrote them in its language;
    None if the form isn't one of those known."""
    t = " ".join(text.split())  # also the no-break spaces some languages put before AM/PM
    try:
        if m := _DOTTED.match(t):  # Bulgarian, German, Russian…: day first
            d, mo, y, h, mi, s = m.groups()
            return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0))
        if m := _SLASHED.match(t):
            a, b, y, h, mi, s, half = m.groups()
            if half:  # US English: month first, 12-hour clock
                return datetime(int(y), int(a), int(b), int(h) % 12 + (12 if half in "Pp" else 0), int(mi), int(s or 0))
            return datetime(int(y), int(b), int(a), int(h), int(mi), int(s or 0))  # British English, French: day first
        if m := _ISO.match(t):
            y, mo, d, h, mi, s = m.groups()
            return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0))
    except ValueError:  # a month or an hour out of range
        return None
    return None


def _skip_blank(lines, i, end=None):
    end = len(lines) if end is None else end
    while i < end and not lines[i].strip():
        i += 1
    return i


def _is(line, label):
    return line.strip().casefold() == label.casefold()


def _section(lines):
    """Lines as one text, without the blank lines around them; the rest is kept as written:
    indentation, blank lines inside, list markers."""
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return "\n".join(lines[start:end])


def _short(text, limit=60):
    text = text.strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"
