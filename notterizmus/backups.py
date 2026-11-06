"""Earlier versions of chapters (no GTK).

Copies live in <data dir>/backups/<Book>/<chapter file name without .notz>/, named by
the time they were taken. The window takes one when a chapter is opened (forced) and
then at most every BACKUP_EVERY seconds while autosave runs, always of the file as it
is on disk just before it gets overwritten, so each copy is a version you really had.
"""
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

BACKUP_EVERY = 600   # seconds between copies while editing
KEEP = 20            # copies kept per chapter
_STAMP = "%Y-%m-%dT%H-%M-%S"


@dataclass
class Backup:
    when: datetime
    path: Path


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
            out.append(Backup(datetime.strptime(f.stem, _STAMP), f))
        except ValueError:
            continue
    out.sort(key=lambda b: b.when, reverse=True)
    return out


def backup(chapter, folder, now=None, force=False, every=None, keep=None):
    """Copy chapter (as it is on disk) into folder unless the newest copy is recent or
    identical. Returns the new copy's path, or None."""
    every = BACKUP_EVERY if every is None else every  # read at call time (tests shorten it)
    keep = KEEP if keep is None else keep
    chapter = Path(chapter)
    if not chapter.is_file():
        return None
    now = now or datetime.now()
    existing = list_backups(folder)
    if existing:
        newest = existing[0]
        if not force and (now - newest.when).total_seconds() < every:
            return None
        if newest.path.read_bytes() == chapter.read_bytes():
            return None
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{now.strftime(_STAMP)}.notz"
    if target.exists():  # two copies in the same second: keep the first
        return None
    shutil.copy2(chapter, target)
    for old in list_backups(folder)[keep:]:
        old.path.unlink(missing_ok=True)
    return target


def move(moved, notes_root, root):
    """After chapters were renamed or moved ({old path: new path}), move their copies."""
    for old, new in moved.items():
        src, dst = folder_for(old, notes_root, root), folder_for(new, notes_root, root)
        if src == dst or not src.is_dir():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():  # merge: keep both sets of copies
            for f in src.iterdir():
                if not (dst / f.name).exists():
                    f.rename(dst / f.name)
            shutil.rmtree(src, ignore_errors=True)
        else:
            src.rename(dst)
        _remove_empty_parents(src.parent, Path(root))


def _remove_empty_parents(folder, stop):
    folder = Path(folder)
    while folder != stop and folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
        folder = folder.parent
