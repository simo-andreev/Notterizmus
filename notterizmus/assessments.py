"""Imported TopCoding assessment reports and the practice attempts on them (no GTK).

They live in a hidden folder of the notes folder (paths.assessments_dir()), so they go
where the notes go, one folder per imported report:

    .assessments/
      design_a_rate_limiter_2026-11-23T19-05-51/
        report.txt      the file as it was imported, byte for byte, so it can be read again
        report.json     the report as read, the chapter it belongs to, and how it was read
        draft.json      the practice attempt in progress
        attempts/
          2026-11-25T10-05-12Z.json    finished attempts, named in UTC (as backups.py names copies)

Every file is written in one step (files.atomic_write), and an import is written into a
hidden ".importing-…" folder that is then renamed into place, so it is there whole or
not at all. After a crash or a power cut:
- an import that stopped halfway leaves only its hidden folder, removed an hour later;
- a Replace that stopped between report.txt and report.json shows in report.json's
  sha256 of report.txt, and report.txt is read again, as it is when report.json was
  written by an older parser (assessment_txt.PARSER_VERSION);
- Finish Attempt marks draft.json finished before it moves it into attempts/, so a draft
  found marked finished is moved there when it is next read.

Sync tools carry the folder to other computers. A draft that another computer changed
since this one read it is kept as an attempt "from another computer" before this
computer's draft is written over it: neither is lost, but they aren't merged.

Fields this version doesn't know are kept when a file is written again, as in chapters.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path

from . import assessment_txt, library
from .assessment_txt import MAX_BYTES, PARSER_VERSION, Report
from .files import atomic_write, sync_folder
from .model import fit_name

log = logging.getLogger(__name__)

FORMAT = "notterizmus-assessment/1"
ATTEMPT_FORMAT = "notterizmus-attempt/1"
REPORT_TXT, REPORT_JSON, DRAFT, ATTEMPTS = "report.txt", "report.json", "draft.json", "attempts"
ELSEWHERE = "another computer"  # the origin of a draft kept when this computer saved over it
STALE_IMPORT = 3600  # seconds: a hidden import folder this old was left by a crash
MATCH = 0.8          # how alike (difflib's ratio) a chapter's title must be to be suggested
_STAMP = "%Y-%m-%dT%H-%M-%S"  # then "Z": attempts are named in UTC (CR26)
_REPORT_FIELDS = ("format", "parser_version", "imported", "source", "sha256", "chapter", "report")
_ATTEMPT_FIELDS = ("format", "started", "finished", "origin", "answers")
_LINK_FIELDS = ("file", "book", "number", "title")
_ANSWER_FIELDS = ("text", "revealed")


@dataclass
class Link:
    """The chapter an assessment belongs to, as it was when they were linked: its file
    (relative to the notes folder), its book's folder, its number and its title.
    resolve() finds the chapter again after another program renamed, renumbered or
    moved it; the app's own changes are followed by follow_moves()."""
    file: str
    book: str = ""
    number: int | None = None
    title: str = ""
    extra: dict = field(default_factory=dict)

    def to_json(self):
        return {**self.extra, "file": self.file, "book": self.book, "number": self.number, "title": self.title}

    @classmethod
    def from_json(cls, d):
        number = d.get("number")
        if number is not None and type(number) is not int:
            raise TypeError(f"{number!r} isn't a chapter number")
        return cls(file=_str(d["file"]), book=_str(d.get("book")), number=number, title=_str(d.get("title")),
                   extra={k: v for k, v in d.items() if k not in _LINK_FIELDS})


@dataclass
class Assessment:
    """An imported report, as its folder's report.json has it."""
    folder: Path
    report: Report
    chapter: Link | None = None
    imported: datetime | None = None
    source: str = ""           # the imported file's name
    sha256: str = ""           # of the report.txt that report.json was written from
    parser_version: int = PARSER_VERSION
    format: str = FORMAT
    extra: dict = field(default_factory=dict)
    attempts: int = 0          # finished practice attempts (counted when read, not stored)
    has_draft: bool = False    # a practice attempt is in progress (the same)

    @property
    def id(self):
        return self.folder.name

    def to_json(self):
        d = {
            "format": self.format,
            "parser_version": self.parser_version,
            "imported": _iso(self.imported),
            "source": self.source,
            "sha256": self.sha256,
            "chapter": None if self.chapter is None else self.chapter.to_json(),
            "report": self.report.to_json(),
        }
        for k, v in self.extra.items():
            d.setdefault(k, v)
        return d

    @classmethod
    def from_json(cls, folder, d):
        """Raises ValueError for data that isn't an assessment's."""
        try:
            chapter, version = d.get("chapter"), d.get("parser_version", 0)
            if type(version) is not int:
                raise TypeError(f"{version!r} isn't a parser version")
            return cls(folder=Path(folder), report=Report.from_json(d["report"]),
                       chapter=None if chapter is None else Link.from_json(chapter),
                       imported=_when(d.get("imported")), source=_str(d.get("source")),
                       sha256=_str(d.get("sha256")), parser_version=version,
                       format=_str(d.get("format")) or FORMAT,
                       extra={k: v for k, v in d.items() if k not in _REPORT_FIELDS})
        except (AttributeError, KeyError, TypeError) as e:
            raise ValueError(f"{REPORT_JSON} isn't an assessment's") from e


@dataclass
class Answer:
    text: str = ""
    revealed: bool = False  # the original answer, the sample answer, the score and feedback were shown
    extra: dict = field(default_factory=dict)

    def is_blank(self):
        return not self.text.strip() and not self.revealed and not self.extra

    def to_json(self):
        return {**self.extra, "text": self.text, "revealed": self.revealed}


@dataclass
class Attempt:
    """A practice attempt: the one in progress (draft.json) or a finished one."""
    started: datetime | None = None   # when it was first saved
    finished: datetime | None = None
    answers: dict = field(default_factory=dict)  # {question number: Answer}
    origin: str = ""                  # ELSEWHERE: a draft kept from another computer
    format: str = ATTEMPT_FORMAT
    extra: dict = field(default_factory=dict)
    # Not stored. disk: draft.json as this attempt last read or wrote it (the conflict check).
    # set_aside: an unreadable draft.json was kept under this name.
    disk: tuple | None = field(default=None, compare=False, repr=False)
    set_aside: Path | None = field(default=None, compare=False, repr=False)

    def answer(self, number):
        return self.answers.get(number) or Answer()

    def drafted(self):
        """The numbers of the questions answered in this attempt."""
        return {n for n, a in self.answers.items() if a.text.strip()}

    def revealed(self):
        return {n for n, a in self.answers.items() if a.revealed}

    def is_empty(self):
        return not self.drafted() and not self.revealed()

    def same_as(self, other):
        def content(attempt):
            return {n: (a.text, a.revealed) for n, a in attempt.answers.items() if not a.is_blank()}
        return content(self) == content(other)

    def to_json(self):
        d = {
            "format": self.format,
            "started": _iso(self.started),
            "finished": _iso(self.finished),
            **({"origin": self.origin} if self.origin else {}),
            "answers": {str(n): a.to_json() for n, a in sorted(self.answers.items()) if not a.is_blank()},
        }
        for k, v in self.extra.items():
            d.setdefault(k, v)
        return d

    @classmethod
    def from_json(cls, d):
        """Raises ValueError for data that isn't an attempt."""
        try:
            answers = {}
            for key, value in (d.get("answers") or {}).items():
                revealed = value.get("revealed", False)
                if type(revealed) is not bool:
                    raise TypeError(f"{revealed!r} isn't true or false")
                answers[int(key)] = Answer(_str(value.get("text")), revealed,
                                           {k: v for k, v in value.items() if k not in _ANSWER_FIELDS})
            return cls(started=_when(d.get("started")), finished=_when(d.get("finished")), answers=answers,
                       origin=_str(d.get("origin")), format=_str(d.get("format")) or ATTEMPT_FORMAT,
                       extra={k: v for k, v in d.items() if k not in _ATTEMPT_FIELDS})
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            raise ValueError("this isn't a practice attempt") from e


@dataclass
class AttemptFile:
    """A finished attempt, known by its name only until read_attempt() reads it."""
    when: datetime  # when it was finished, in local time
    path: Path


def count_words(text):
    return len(text.split())


# How TopCoding's report page colors scores (its script, read on 2026-11-26 from report
# 24). A question's: 0.8 and up green, 0.5 and up amber, below that red; an unanswered
# question scores 0, so it is red too, and an ungraded one has no color. The final
# result's: by its percentage to one decimal, as the page shows it, 80 and up green, 65
# and up amber, below that red (the page's blue while it is ungraded: no color here).
GOOD, PARTIAL, POOR = "good", "partial", "poor"
GOOD_FROM, PARTIAL_FROM = Fraction(4, 5), Fraction(1, 2)
FINAL_GOOD_FROM, FINAL_PARTIAL_FROM = 80, 65  # percent


def result_category(score):
    """GOOD, PARTIAL or POOR for a question's original score (assessment_txt.Points), as
    TopCoding colors it; None for an ungraded question (no score). TopCoding's questions
    are out of 1; a score out of more counts as its share of that. Exact, as the file
    writes it: 0.8 is GOOD and 0.79 PARTIAL, whatever binary floating point would make of
    them."""
    if score is None:
        return None
    try:
        share = _share(score)
    except (ValueError, ZeroDivisionError):  # not a score a report can have
        return None
    return GOOD if share >= GOOD_FROM else PARTIAL if share >= PARTIAL_FROM else POOR


def final_category(report):
    """GOOD, PARTIAL or POOR for a report's final result, as TopCoding colors it; None while
    it is ungraded. By the percentage to one decimal that the page shows and compares: the
    file's own ("37.4"), else worked out from the points, rounded half up."""
    if report.final_result is None:
        return None
    try:
        percent = (Fraction(report.final_percent.replace(",", ".")) if report.final_percent
                   else Fraction(int(_share(report.final_result) * 1000 + Fraction(1, 2)), 10))
    except (ValueError, ZeroDivisionError):  # not a result a report can have
        return None
    return GOOD if percent >= FINAL_GOOD_FROM else PARTIAL if percent >= FINAL_PARTIAL_FROM else POOR


def _share(points):
    """got / out_of, exact as the file writes them (a decimal comma too)."""
    return Fraction(points.got.replace(",", ".")) / Fraction(points.out_of.replace(",", "."))


# -- assessments --------------------------------------------------------------------------

def list_all(root, now=None):
    """(assessments, unreadable): the assessments in root, the most recently completed
    first, and [(folder, reason)] for the folders that can't be read as one. Also removes
    what imports stopped by a crash left behind."""
    root = Path(root)
    try:
        entries = sorted(root.iterdir())
    except FileNotFoundError:
        return [], []
    found, broken = [], []
    for d in entries:
        if d.name.startswith(".importing-"):
            _remove_stale_import(d, now)
        if d.name.startswith(".") or not d.is_dir():
            continue
        try:
            found.append(load(d))
        except (OSError, ValueError) as e:
            broken.append((d, str(e)))
    found.sort(key=lambda a: a.report.title.casefold())
    found.sort(key=lambda a: a.report.completed_at or datetime.min, reverse=True)
    return found, broken


def load(folder):
    """The assessment in folder. report.json is written again from report.txt when it
    doesn't match it (a Replace stopped halfway) or an older parser wrote it, and rebuilt
    from it, without its chapter, when it can't be read. Raises OSError or ValueError if
    neither file can be read."""
    folder = Path(folder)
    a = error = None
    try:
        a = Assessment.from_json(folder, _read_json(folder / REPORT_JSON))
    except (OSError, ValueError) as e:
        error = e
    try:
        raw = (folder / REPORT_TXT).read_bytes()
    except OSError:
        if a is None:
            raise error from None
        raw = None
    if raw is not None:
        digest = hashlib.sha256(raw).hexdigest()
        if a is None or a.sha256 != digest or a.parser_version < PARSER_VERSION:
            try:
                report = assessment_txt.parse(raw)
            except ValueError as e:
                if a is None:
                    raise ValueError(f"neither {REPORT_JSON} ({error}) nor {REPORT_TXT} ({e}) can be read") from e
            else:  # (a report.txt the parser now refuses keeps the report as it was read)
                if a is None:
                    a = Assessment(folder, report, imported=_modified(folder / REPORT_TXT))
                a = replace(a, report=report, sha256=digest, parser_version=PARSER_VERSION)
                try:
                    _write_json(folder / REPORT_JSON, a.to_json())
                except OSError as e:  # read again next time
                    log.warning("can't update %s: %s", folder / REPORT_JSON, e)
    a.attempts = len(_attempt_names(folder))
    a.has_draft = (folder / DRAFT).is_file()
    return a


def read_import(path):
    """(the file's bytes, the report in them) for importing the file at path. Raises
    OSError if it can't be read, assessment_txt.ReportError if it isn't a report."""
    with open(path, "rb") as f:
        data = f.read(MAX_BYTES + 1)  # parse() refuses a larger file; no need to read all of it
    return data, assessment_txt.parse(data)


def find_duplicate(found, report):
    """The assessment among found that report is another download of, or None."""
    key = report.key
    return next((a for a in found if a.report.key == key), None)


def import_report(root, data, report=None, source="", chapter=None, now=None):
    """Store the report in data (a TopCoding report file's bytes; report, if given, is
    what parse() read from them) as a new assessment in root, and return it."""
    report = assessment_txt.parse(data) if report is None else report
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    now = _now(now)
    stage = root / f".importing-{uuid.uuid4().hex[:12]}"  # hidden: never listed
    stage.mkdir()
    try:
        a = Assessment(stage, report, chapter=chapter, imported=now, source=source,
                       sha256=hashlib.sha256(data).hexdigest())
        with atomic_write(stage / REPORT_TXT, binary=True) as f:
            f.write(data)
        _write_json(stage / REPORT_JSON, a.to_json())
        target = _free_name(root, folder_name(report, now))
        stage.rename(target)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    sync_folder(root)
    return replace(a, folder=target)


def folder_name(report, now=None):
    """An assessment's folder name: its title and when it was completed (else imported)."""
    slug = re.sub(r"[\W_]+", "_", report.title.casefold()).strip("_") or "assessment"
    when = report.completed_at or _now(now)
    return f"{fit_name(slug, 120).rstrip('_')}_{when.strftime(_STAMP)}"


def replace_report(a, data, report=None, source="", now=None):
    """Put another download of the same report (its graded one, say) in place of a's,
    keeping its chapter, its draft and its attempts; returns the assessment as it is now.
    report.txt goes first: report.json's sha256 shows a Replace that stopped in between,
    and load() completes it."""
    report = assessment_txt.parse(data) if report is None else report
    current = load(a.folder)
    if report.key != current.report.key:
        raise ValueError(f"“{report.title}” isn't another download of the report imported as “{current.report.title}”")
    with atomic_write(current.folder / REPORT_TXT, binary=True) as f:
        f.write(data)
    new = replace(current, report=report, sha256=hashlib.sha256(data).hexdigest(),
                  parser_version=PARSER_VERSION, imported=_now(now), source=source or current.source)
    _write_json(new.folder / REPORT_JSON, new.to_json())
    return new


def set_chapter(a, chapter):
    """Link a's report to chapter (a Link, or None for none); returns the assessment as it is now."""
    new = replace(load(a.folder), chapter=chapter)
    _write_json(new.folder / REPORT_JSON, new.to_json())
    return new


# -- practice attempts --------------------------------------------------------------------

def read_draft(a, now=None):
    """The practice attempt in progress: a new one if there is none. A draft marked
    finished was being finished when the app stopped: it goes into the attempts now, and
    a new one follows it. An unreadable draft is kept under another name (see
    Attempt.set_aside), so that nothing is written over it. Raises OSError."""
    path = Path(a.folder) / DRAFT
    disk = _disk_state(path)
    if disk is None:
        return Attempt()
    try:
        attempt = Attempt.from_json(_read_json(path))
    except ValueError:
        return Attempt(set_aside=_set_aside(path, now))
    if attempt.finished is not None:
        _archive(path, attempt.finished)
        return Attempt()
    attempt.disk = disk
    return attempt


def write_draft(a, attempt, now=None):
    """Save attempt as the draft in progress. Returns the path of the attempt kept from
    another computer, or None: if draft.json changed since attempt was read or written,
    another computer (through a sync tool) changed it, and its version is kept as an
    attempt before this one is written, unless it has nothing in it or the same answers."""
    now = _now(now)
    path = Path(a.folder) / DRAFT
    kept = None
    disk = _disk_state(path)
    if disk is not None and disk != attempt.disk:
        kept = _keep_theirs(path, attempt, now)
    if attempt.started is None:
        attempt.started = now
    _write_json(path, attempt.to_json())
    attempt.disk = _disk_state(path)
    return kept


def _keep_theirs(path, attempt, now):
    try:
        theirs = Attempt.from_json(_read_json(path))
    except ValueError:
        attempt.set_aside = _set_aside(path, now)
        return None
    if theirs.is_empty() or theirs.same_as(attempt):
        return None
    theirs.origin = ELSEWHERE
    theirs.finished = theirs.finished or now
    target = _attempt_path(path.parent, theirs.finished)
    _write_json(target, theirs.to_json())
    return target


def finish(a, attempt, now=None):
    """Finish attempt: it is kept among the attempts, and the next one starts blank.
    Returns (its path, the path of an attempt kept from another computer or None).
    draft.json is marked finished first, then moved: read_draft() completes a finish
    that stopped in between."""
    now = _now(now)
    attempt.finished = now
    try:
        kept = write_draft(a, attempt, now)
    except BaseException:
        attempt.finished = None
        raise
    return _archive(Path(a.folder) / DRAFT, now), kept


def list_attempts(a):
    """Finished attempts, newest first, by their names only: read_attempt() reads one."""
    folder = Path(a.folder) / ATTEMPTS
    out = []
    for name in _attempt_names(a.folder):
        try:
            when = datetime.strptime(name[:-len("Z.json")], _STAMP).replace(tzinfo=timezone.utc).astimezone()
        except (ValueError, OverflowError):
            continue
        out.append(AttemptFile(when, folder / name))
    out.sort(key=lambda f: f.when, reverse=True)
    return out


def read_attempt(path):
    """A finished attempt. Raises OSError or ValueError."""
    return Attempt.from_json(_read_json(path))


def _attempt_names(folder):
    try:
        names = os.listdir(Path(folder) / ATTEMPTS)
    except OSError:
        return []
    return [n for n in names if n.endswith("Z.json") and not n.startswith(".")]


def _attempt_path(folder, when):
    """A free name in folder's attempts for an attempt finished at when."""
    attempts = Path(folder) / ATTEMPTS
    attempts.mkdir(exist_ok=True)
    when = when.astimezone(timezone.utc).replace(microsecond=0)
    while (path := attempts / f"{when.strftime(_STAMP)}Z.json").exists():
        when += timedelta(seconds=1)  # two in the same second: keep both
    return path


def _archive(draft, when):
    target = _attempt_path(draft.parent, when)
    draft.rename(target)
    sync_folder(target.parent)
    sync_folder(draft.parent)
    return target


def _set_aside(path, now):
    """Keep an unreadable draft under another name, so that a new one can be written."""
    stamp = _now(now).astimezone(timezone.utc).strftime(_STAMP)
    target, n = path.with_name(f"draft-unreadable-{stamp}Z.json"), 2
    while target.exists():
        target, n = path.with_name(f"draft-unreadable-{stamp}Z-{n}.json"), n + 1
    path.rename(target)
    return target


# -- chapters -----------------------------------------------------------------------------

def link_for(path, notes_root):
    """A Link to the chapter at path."""
    path = Path(path)
    number, title = library.parse_name(path.stem)
    return Link(file=_relative(path, notes_root), book=path.parent.name, number=number, title=title)


def suggest(title, books):
    """The chapter among books (library.scan()'s) whose title is most like an
    assessment's title, ignoring case and punctuation and allowing for typos; None if
    none is alike enough."""
    want = _normal(title)
    if not want:
        return None
    best, best_ratio = None, 0.0
    for book in books:
        for ch in book.chapters:
            have = _normal(ch.title)
            if not have:
                continue
            if have == want:
                return ch
            ratio = max(_ratio(want, have), _ratio(_topic(want), _topic(have)))
            if ratio > best_ratio:
                best, best_ratio = ch, ratio
    return best if best_ratio >= MATCH else None


def resolve(link, books, notes_root):
    """The chapter among books that link points to, or None. By its file; failing that,
    in its book, by its title (renumbered) and then by its number (renamed); failing
    that, by its title in any book (moved). Each way counts only if it finds one chapter."""
    if link is None:
        return None
    chapters = [(book, ch) for book in books for ch in book.chapters]
    file = Path(link.file)
    file = file if file.is_absolute() else Path(notes_root) / file
    for _book, ch in chapters:
        if library.same_file(ch.path, file):
            return ch
    in_book = [ch for book, ch in chapters if book.path.name == link.book]
    title = _normal(link.title)
    for found in ([ch for ch in in_book if title and _normal(ch.title) == title],
                  [ch for ch in in_book if link.number is not None and ch.number == link.number],
                  [ch for _book, ch in chapters if title and _normal(ch.title) == title]):
        if len(found) == 1:
            return found[0]
    return None


def resolve_links(found, books, notes_root):
    """[(assessment, its chapter or None)] for the assessments found. A link found other
    than by its file (another program renamed or moved the chapter) is brought up to date."""
    out = []
    for a in found:
        ch = resolve(a.chapter, books, notes_root)
        if ch is not None and a.chapter.file != _relative(ch.path, notes_root):
            try:
                a = set_chapter(a, link_for(ch.path, notes_root))
            except (OSError, ValueError) as e:  # it is found again next time
                log.warning("can't update the chapter of %s: %s", a.folder, e)
        out.append((a, ch))
    return out


def follow_moves(root, moved, notes_root):
    """After chapters were renamed or moved ({old path: new path}, as library's changes
    return), link their assessments to the new paths. Returns the assessments changed;
    the first error is raised after the others were changed."""
    if not moved:
        return []
    where = {_relative(old, notes_root): new for old, new in moved.items()}
    found, _broken = list_all(root)
    changed, failed = [], None
    for a in found:
        if a.chapter is not None and a.chapter.file in where:
            try:
                changed.append(set_chapter(a, link_for(where[a.chapter.file], notes_root)))
            except (OSError, ValueError) as e:
                failed = failed or e
    if failed:
        raise failed
    return changed


def _relative(path, notes_root):
    """path relative to the notes folder, as a link stores it; a path elsewhere whole."""
    path = Path(path).resolve()
    try:
        return path.relative_to(Path(notes_root).resolve()).as_posix()
    except ValueError:
        return str(path)


def _normal(text):
    """A title for comparing: lower case, words only."""
    return " ".join(re.sub(r"[\W_]+", " ", text.casefold()).split())


def _topic(normal):
    """A normalized title without "design a": "design a url shortener" -> "url shortener"."""
    return re.sub(r"^design (?:an? |the )?", "", normal)


def _ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


# -- files --------------------------------------------------------------------------------

def _read_json(path):
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except RecursionError as e:  # nested too deep to read
            raise ValueError(f"{Path(path).name} isn't readable") from e


def _write_json(path, data):
    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    with atomic_write(path) as f:
        f.write(text)


def _disk_state(path):
    """As model._disk_state: what tells one version of a file from another; None if there's none."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_ino, st.st_mtime_ns, st.st_size


def _free_name(root, name):
    target, n = root / name, 2
    while target.exists():
        target, n = root / f"{name}-{n}", n + 1
    return target


def _remove_stale_import(folder, now=None):
    try:
        age = (now.timestamp() if now else time.time()) - folder.stat().st_mtime
    except OSError:
        return
    if age > STALE_IMPORT:
        shutil.rmtree(folder, ignore_errors=True)


def _modified(path):
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    except OSError:
        return None


def _now(now=None):
    """now (default: the current time) as local time with its offset."""
    return (now or datetime.now()).astimezone()


def _iso(when):
    return None if when is None else when.isoformat(timespec="seconds")


def _when(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{value!r} isn't a date and time")
    when = datetime.fromisoformat(value)
    return when if when.tzinfo else when.astimezone()


def _str(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{value!r} isn't text")
    return value
