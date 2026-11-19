"""The notes folder as books and chapters, for the sidebar (no GTK).

Each folder in <Documents>/Notterizmus is a book; each .notz file in it is a chapter,
named "<NN> <Title>.notz" by model.chapter_filename().
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .model import Document, chapter_filename, fit_name

_NAME = re.compile(r"^(\d+)(?:\s+(.*))?$")


@dataclass
class Chapter:
    number: int | None
    title: str
    path: Path

    @property
    def label(self):
        if self.title:
            return self.title
        return f"Chapter {self.number}" if self.number is not None else self.path.stem


@dataclass
class Book:
    name: str
    path: Path
    chapters: list = field(default_factory=list)


def parse_name(stem):
    """'03 The Title' -> (3, 'The Title'); '03' -> (3, ''); 'notes' -> (None, 'notes')."""
    m = _NAME.match(stem.strip())
    if m:
        return int(m.group(1)), (m.group(2) or "").strip()
    return None, stem


def scan(root):
    """Books (folders with at least one chapter) sorted by name, chapters by number."""
    try:
        folders = [d for d in Path(root).iterdir() if d.is_dir() and not d.name.startswith(".")]
    except OSError:
        return []
    books = []
    for d in folders:
        chapters = []
        for f in d.glob("*.notz"):
            if f.name.startswith(".") or not f.is_file():
                continue
            number, title = parse_name(f.stem)
            chapters.append(Chapter(number, title, f))
        if chapters:
            chapters.sort(key=lambda c: (c.number is None, c.number or 0, c.title.casefold(), c.path.name))
            books.append(Book(d.name, d, chapters))
    books.sort(key=lambda b: b.name.casefold())
    return books


def same_file(a, b):
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


def find(books, path):
    """(book, index) of the chapter at path, or (None, None)."""
    if path is None:
        return None, None
    for book in books:
        for i, ch in enumerate(book.chapters):
            if same_file(ch.path, path):
                return book, i
    return None, None


def neighbor(books, path, delta):
    """The chapter delta steps away in the same book, or None at either end."""
    book, i = find(books, path)
    if book is None:
        return None
    j = i + delta
    return book.chapters[j] if 0 <= j < len(book.chapters) else None


# -- changing chapters and books ----------------------------------------------------------
# The open chapter must be saved before any of these and pointed at its new path after
# (each returns {old path: new path}); otherwise autosave would bring the old file back.

def safe_name(name):
    """A book name as a folder name: without "/", "\\" or NUL, never hidden (scan() skips
    hidden folders, so ".NET" becomes "_NET"), never "." or ".." (they would put chapters in
    the notes folder itself, or above it), and short enough for a file name (CR7, CR15)."""
    folder = "".join("_" if c in "/\\\0" else c for c in name).strip()
    if folder in ("", ".", ".."):
        return "Unsorted"
    return fit_name("_" + folder[1:] if folder.startswith(".") else folder)


def book_name(book_dir):
    """The book's name as stored in its chapters (folder names lose "/" and "\\")."""
    for f in sorted(Path(book_dir).glob("*.notz")):
        if not f.name.startswith("."):
            try:
                name = Document.load(f).book
            except (OSError, ValueError):
                continue
            if name:
                return name
    return Path(book_dir).name


def _rewrite(path, new_path, doc=None, **fields):
    """Save the chapter at path (already loaded as doc, if given) to new_path with some
    fields changed; remove the old file."""
    if doc is None:
        doc = Document.load(path)
    if "number" in fields:
        doc.chapter_no = fields["number"]
    if "title" in fields:
        doc.chapter_title = fields["title"]
    if "book" in fields:
        doc.book = fields["book"]
    doc.save(new_path)
    if Path(new_path).resolve() != Path(path).resolve():
        Path(path).unlink()
    return Path(new_path)


def _temp_path(folder):
    return Path(folder) / f".moving-{uuid.uuid4().hex[:8]}.notz"  # hidden: scan() skips it


def chapters_numbered(folder, number, exclude=None):
    """The chapters with this number in a book folder (other than exclude), by file name."""
    out = []
    for f in sorted(Path(folder).glob("*.notz")):
        if f.name.startswith(".") or (exclude is not None and same_file(f, exclude)):
            continue
        if parse_name(f.stem)[0] == number:
            out.append(Chapter(number, parse_name(f.stem)[1], f))
    return out


def chapter_numbered(folder, number, exclude=None):
    """The chapter with this number in a book folder (other than exclude), or None."""
    found = chapters_numbered(folder, number, exclude)
    return found[0] if found else None


def _compose(first, second):
    out = {old: second.get(new, new) for old, new in first.items()}
    for old, new in second.items():
        if not any(same_file(old, v) for v in first.values()):
            out[old] = new
    return out


def set_chapter(path, number, title, book_dir=None):
    """Give a chapter a new number and title, optionally moving it to another book's
    folder. In its own book, a number another chapter has is swapped with it; in another
    book, or if two chapters have it, it raises FileExistsError. Returns {old path: new
    path}. Every check comes before any file moves, and a failure after the swap (a full
    disk, say) undoes the swap before it is raised (CR6 in CODE_REVIEW.md)."""
    path = Path(path)
    folder = Path(book_dir) if book_dir else path.parent
    moving = not same_file(folder, path.parent)
    others = chapters_numbered(folder, number, exclude=path)
    if len(others) > 1 or (others and moving):
        raise FileExistsError(others[0].path)
    other = others[0] if others else None
    mine = parse_name(path.stem)[0]
    mine = number if mine is None else mine
    swap = other is not None and mine != number  # (a chapter that already has the number keeps it)
    new = folder / chapter_filename(number, title)
    if new.exists() and not same_file(new, path) and not (swap and same_file(new, other.path)):
        raise FileExistsError(new)  # (the other chapter's file is free once the two swap)
    fields = {"number": number, "title": title}
    if moving:
        folder.mkdir(parents=True, exist_ok=True)
        fields["book"] = book_name(folder) if any(folder.glob("*.notz")) else folder.name
    moved = renumber({path: number, other.path: mine}) if swap else {}
    try:
        final = _rewrite(moved.get(path, path), new, **fields)
    except BaseException as e:
        if moved:
            try:
                renumber({moved[path]: mine, moved[other.path]: number})
            except (OSError, ValueError) as undo:
                e.add_note(f"The swap with {other.path.name} couldn't be undone: {undo}")
        raise
    return _compose(moved, {moved.get(path, path): final})


def renumber(changes):
    """Apply {path: new number} to chapters of one book, numbers possibly swapping
    between them; titles are kept. Returns {old path: new path}.

    In two steps, so that numbers can swap: each chapter is first written under a hidden
    staging name with its new number, then given its new name. If anything fails halfway
    (a full disk, say), every chapter is put back under its old name and number before the
    error is raised again (CR6 in CODE_REVIEW.md)."""
    # Read every chapter before moving any: one that can't be read then stops the change
    # while all the files still have their names.
    docs = {Path(path): Document.load(path) for path in changes}
    staged = []   # (path, staging path, old number, new path)
    renamed = []  # those of them already under their new path
    try:
        for path, number in changes.items():
            path = Path(path)
            doc = docs[path]
            if doc.chapter_no == number and path.name == chapter_filename(number, doc.chapter_title):
                continue
            item = (path, _temp_path(path.parent), doc.chapter_no, path.parent / chapter_filename(number, doc.chapter_title))
            staged.append(item)
            _rewrite(path, item[1], doc=doc, number=number)
        taken = [new for _p, _t, _n, new in staged if new.exists()]
        if taken:  # another chapter's file is in the way
            raise FileExistsError(taken[0])
        for item in staged:
            item[1].rename(item[3])
            renamed.append(item)
    except BaseException as e:
        hidden = _put_back(staged, renamed)
        if hidden:
            e.add_note("Left under a hidden name (restore_stranded() gives it back): "
                       + ", ".join(str(p) for p in hidden))
        raise
    return {path: new for path, _t, _n, new in staged}


def _put_back(staged, renamed):
    """Undo a renumbering that stopped halfway, as far as can be done; returns the files
    still under a hidden staging name. Never overwrites a chapter."""
    for _path, tmp, _n, new in reversed(renamed):  # first off the new names: they may be others' old ones
        try:
            new.rename(tmp)
        except OSError:
            pass  # it stays under its new name: changed, but still listed
    hidden = []
    for path, tmp, old_number, _new in staged:
        if not tmp.exists():
            continue  # its write failed, so it still has its own name
        if path.exists():
            hidden.append(tmp)
            continue
        try:
            _rewrite(tmp, path, number=old_number)
        except (OSError, ValueError):
            try:
                tmp.rename(path)  # its old name, if not its old number inside
            except OSError:
                hidden.append(tmp)
    return hidden


def stranded(root):
    """Chapters left under a hidden staging name by a change that stopped halfway and
    couldn't be undone, or by a crash or power cut in the middle of one."""
    try:
        folders = [d for d in Path(root).iterdir() if d.is_dir() and not d.name.startswith(".")]
    except OSError:
        return []
    return sorted(f for d in folders for f in d.glob(".moving-*.notz") if f.is_file())


def restore_stranded(path):
    """Give a stranded chapter its name back, from the number and title inside it. If
    another chapter has that name, " (restored)" goes after its title. Returns the new path."""
    path = Path(path)
    doc = Document.load(path)
    title, n = doc.chapter_title, 1
    new = path.parent / chapter_filename(doc.chapter_no, title)
    while new.exists():
        title = f"{doc.chapter_title} (restored{f' {n}' if n > 1 else ''})".strip()
        new = path.parent / chapter_filename(doc.chapter_no, title)
        n += 1
    return _rewrite(path, new, doc=doc, title=title)


def reorder(chapters):
    """Chapters of one book in their new order: they get the book's existing numbers in
    that order (chapters 1, 2, 5 reordered C, A, B become C=1, A=2, B=5)."""
    numbered = [c for c in chapters if c.number is not None]
    numbers = sorted(c.number for c in numbered)
    return renumber({c.path: n for c, n in zip(numbered, numbers)})


def rename_book(book_dir, new_name, failed=None):
    """Rename a book's folder and the book name stored in its chapters (a chapter file
    that can't be read as one just moves along with the folder).
    Raises FileExistsError if another book already uses that name (ignoring case).
    Once the folder has moved, a chapter that can't be rewritten (a full disk, say) keeps
    its old book name and the rest go on: it is added to the list failed, if given, so
    the folder and the paths returned always agree."""
    book_dir = Path(book_dir)
    new_dir = book_dir.parent / safe_name(new_name)
    clash = [d for d in book_dir.parent.iterdir()
             if d.is_dir() and not same_file(d, book_dir) and d.name.casefold() == new_dir.name.casefold()]
    if clash:
        raise FileExistsError(clash[0])
    if new_dir.name != book_dir.name:
        book_dir.rename(new_dir)
    moved = {}
    for f in sorted(new_dir.glob("*.notz")):
        if not f.name.startswith("."):
            try:
                _rewrite(f, f, book=new_name)
            except ValueError:
                pass  # not a chapter
            except OSError:
                if failed is not None:
                    failed.append(f)
            moved[book_dir / f.name] = f
    return moved
