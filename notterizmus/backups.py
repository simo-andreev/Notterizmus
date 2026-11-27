"""Earlier versions of chapters (no GTK).

Copies live in <data dir>/backups/<Book>/<chapter file name without .notz>/, named by
the time they were taken, in UTC (2026-11-06T10-00-00Z.notz; copies from before 1.6 by
local time, without the Z). The window takes one when a chapter is opened (forced) and
then at most every BACKUP_EVERY seconds while autosave runs, always of the file as it
is on disk just before it gets overwritten, so each copy is a version you really had.

Older copies are thinned, not capped: all of the last day, then one per hour for a week,
one per day for three months and one per week after that (the newest in each slot).
"""
from __future__ import annotations

import hashlib
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .files import atomic_write

BACKUP_EVERY = 600   # seconds between copies while editing
# (copies younger than this, keep the newest per slot); slot None keeps every copy
TIERS = [
    (timedelta(days=1), None),
    (timedelta(days=7), "%Y-%m-%d %H"),     # one per hour
    (timedelta(days=90), "%Y-%m-%d"),       # one per day
    (None, "%G-W%V"),                       # one per ISO week, for good
]
_STAMP = "%Y-%m-%dT%H-%M-%S"  # then "Z": in UTC, as local time has an hour twice a year (CR26)


@dataclass
class Backup:
    when: datetime  # in local time, with its offset: copies sort by the moment they were taken
    path: Path


def _local(when=None):
    """when (default: now) as local time with its offset; a time without one is local."""
    return (when or datetime.now()).astimezone()


def _taken(stem):
    """When a copy was taken, from its name: in UTC with a final Z; older copies were
    named by local time."""
    if stem.endswith("Z"):
        return datetime.strptime(stem[:-1], _STAMP).replace(tzinfo=timezone.utc).astimezone()
    return _local(datetime.strptime(stem, _STAMP))


def folder_for(chapter, notes_root, root):
    """Where the copies of chapter go: by book and file name for chapters in the notes
    folder, by a hash of the path for chapters opened from elsewhere."""
    chapter = Path(chapter)
    try:
        rel = chapter.resolve().relative_to(Path(notes_root).resolve())
        return Path(root) / rel.with_suffix("")
    except ValueError:
        digest = hashlib.sha1(str(chapter.resolve()).encode()).hexdigest()[:12]
        return Path(root) / "_elsewhere" / f"{chapter.stem}-{digest}"


def list_backups(folder):
    """Copies in a backup folder, newest first."""
    out = []
    for f in Path(folder).glob("*.notz"):
        try:
            out.append(Backup(_taken(f.stem), f))
        except (ValueError, OverflowError, OSError):  # not a copy's name, or a date out of range
            continue
    out.sort(key=lambda b: b.when, reverse=True)
    return out


def backup(chapter, folder, now=None, force=False, every=None):
    """Copy chapter (as it is on disk) into folder unless the newest copy is recent or
    identical, then thin the older copies. Returns the new copy's path, or None."""
    every = BACKUP_EVERY if every is None else every  # read at call time (tests shorten it)
    chapter = Path(chapter)
    if not chapter.is_file():
        return None
    now = _local(now)
    existing = list_backups(folder)
    if existing:
        newest = existing[0]
        if not force and (now - newest.when).total_seconds() < every:
            return None
        if newest.path.read_bytes() == chapter.read_bytes():
            return None
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / _name(now)
    if target.exists():  # two copies in the same second: keep the first
        return None
    shutil.copy2(chapter, target)
    thin(folder, now)
    return target


def keep(data, folder, now=None):
    """Store data (a chapter file's bytes) as the newest copy: a version that isn't on
    disk, such as the edits Reload replaces (CR10). Skipped if the newest copy is the same;
    never dropped for a copy taken in the same second. Returns its path, or None."""
    now = _local(now)
    existing = list_backups(folder)
    if existing and existing[0].path.read_bytes() == data:
        return None
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    while (folder / _name(now)).exists():
        now += timedelta(seconds=1)
    target = folder / _name(now)
    target.write_bytes(data)
    thin(folder, now)
    return target


def keep_unsaved(text, chapter, folder, now=None):
    """Write text (a chapter file's content that couldn't be saved over chapter) into
    folder/<book>/<chapter stem> <time in UTC>Z.notz, never over an earlier one, and
    return that path (RV1 in PLAN.md). Raises OSError if it can't be written either."""
    chapter = Path(chapter)
    now = _local(now)
    book = Path(folder) / chapter.parent.name
    while (target := book / f"{chapter.stem} {_name(now)}").exists():
        now += timedelta(seconds=1)
    with atomic_write(target) as f:
        f.write(text)
    return target


def _name(when):
    return f"{when.astimezone(timezone.utc).strftime(_STAMP)}Z.notz"


def thin(folder, now=None):
    """Delete copies the tiers don't keep. Returns the number deleted. Ages are the time
    that really passed; slots are hours, days and weeks of local time."""
    now = _local(now)
    seen, gone = set(), 0
    for b in list_backups(folder):  # newest first, so each slot keeps its newest copy
        age = now - b.when
        slot = next(fmt for limit, fmt in TIERS if limit is None or age < limit)
        if slot is None:
            continue
        key = (slot, b.when.strftime(slot))
        if key in seen:
            b.path.unlink(missing_ok=True)
            gone += 1
        else:
            seen.add(key)
    return gone


def move(moved, notes_root, root):
    """After chapters were renamed or moved ({old path: new path}), move their copies.

    In two steps, as library.renumber does: every folder that moves is first put aside
    under a hidden name, then put in its place. So chapters that swap names (untitled ones,
    or ones with the same title) keep their own copies; moved one at a time, the first
    merged into the other's folder (CR5 in CODE_REVIEW.md). A folder already where one
    goes, of a chapter that isn't moving, keeps its copies and gets these added."""
    root = Path(root)
    aside = []  # (folder, its hidden name, where it goes)
    try:
        for old, new in moved.items():
            src, dst = folder_for(old, notes_root, root), folder_for(new, notes_root, root)
            if src != dst and src.is_dir():
                tmp = root / f".moving-{uuid.uuid4().hex[:8]}"
                src.rename(tmp)
                aside.append((src, tmp, dst))
    except OSError:
        for src, tmp, _dst in aside:
            tmp.rename(src)
        raise
    failed = None
    for src, tmp, dst in aside:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():  # merge: keep both sets of copies
                for f in tmp.iterdir():
                    if not (dst / f.name).exists():
                        f.rename(dst / f.name)
                shutil.rmtree(tmp, ignore_errors=True)
            else:
                tmp.rename(dst)
        except OSError as e:
            failed = failed or e
            if not src.exists():
                tmp.rename(src)  # back where it was, at least
    for src, _tmp, _dst in aside:
        _remove_empty_parents(src.parent, root)
    if failed:
        raise failed


def _remove_empty_parents(folder, stop):
    folder = Path(folder)
    while folder != stop and folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
        folder = folder.parent
