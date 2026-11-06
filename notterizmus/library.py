"""The notes folder as books and chapters, for the sidebar (no GTK).

Each folder in <Documents>/Notterizmus is a book; each .notz file in it is a chapter,
named "<NN> <Title>.notz" by model.chapter_filename().
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

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
    """A book name as a folder name."""
    return "".join("_" if c in "/\\\0" else c for c in name).strip() or "Unsorted"


def book_name(book_dir):
    """The book's name as stored in its chapters (folder names lose "/" and "\\")."""
    from .model import Document
    for f in sorted(Path(book_dir).glob("*.notz")):
        if not f.name.startswith("."):
            try:
                name = Document.load(f).book
            except (OSError, ValueError, KeyError):
                continue
            if name:
                return name
    return Path(book_dir).name


def _rewrite(path, new_path, **fields):
    """Save the chapter at path to new_path with some fields changed; remove the old file."""
    from .model import Document
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
    import uuid
    return Path(folder) / f".moving-{uuid.uuid4().hex[:8]}.notz"  # hidden: scan() skips it


def chapter_numbered(folder, number, exclude=None):
    """The chapter with this number in a book folder (other than exclude), or None."""
    for f in Path(folder).glob("*.notz"):
        if f.name.startswith(".") or (exclude is not None and same_file(f, exclude)):
            continue
        if parse_name(f.stem)[0] == number:
            return Chapter(number, parse_name(f.stem)[1], f)
    return None


def _compose(first, second):
    out = {old: second.get(new, new) for old, new in first.items()}
    for old, new in second.items():
        if not any(same_file(old, v) for v in first.values()):
            out[old] = new
    return out


def set_chapter(path, number, title, book_dir=None):
    """Give a chapter a new number and title, optionally moving it to another book's
    folder. In its own book, a number another chapter has is swapped with it; in another
    book it raises FileExistsError. Returns {old path: new path}."""
    from .model import chapter_filename
    path = Path(path)
    folder = Path(book_dir) if book_dir else path.parent
    moving = not same_file(folder, path.parent)
    other = chapter_numbered(folder, number, exclude=path)
    moved = {}
    if other is not None:
        if moving:
            raise FileExistsError(other.path)
        mine = parse_name(path.stem)[0]
        moved = renumber({path: number, other.path: mine if mine is not None else number})
        path = moved.get(path, path)
    new = folder / chapter_filename(number, title)
    if new.exists() and not same_file(new, path):
        raise FileExistsError(new)
    fields = {"number": number, "title": title}
    if moving:
        folder.mkdir(parents=True, exist_ok=True)
        fields["book"] = book_name(folder) if any(folder.glob("*.notz")) else folder.name
    return _compose(moved, {path: _rewrite(path, new, **fields)})


def renumber(changes):
    """Apply {path: new number} to chapters of one book, numbers possibly swapping
    between them; titles are kept. Returns {old path: new path}."""
    from .model import Document, chapter_filename
    staged = []
    for path, number in changes.items():
        path = Path(path)
        doc = Document.load(path)
        if doc.chapter_no == number and path.name == chapter_filename(number, doc.chapter_title):
            continue
        tmp = _rewrite(path, _temp_path(path.parent), number=number)
        staged.append((path, tmp, doc.chapter_no, path.parent / chapter_filename(number, doc.chapter_title)))
    taken = [new for _p, _t, _n, new in staged if new.exists()]
    if taken:  # another chapter's file is in the way: put everything back
        for path, tmp, old_number, _new in staged:
            _rewrite(tmp, path, number=old_number)
        raise FileExistsError(taken[0])
    moved = {}
    for path, tmp, _n, new in staged:
        tmp.rename(new)
        moved[path] = new
    return moved


def reorder(chapters):
    """Chapters of one book in their new order: they get the book's existing numbers in
    that order (chapters 1, 2, 5 reordered C, A, B become C=1, A=2, B=5)."""
    numbered = [c for c in chapters if c.number is not None]
    numbers = sorted(c.number for c in numbered)
    return renumber({c.path: n for c, n in zip(numbered, numbers)})


def rename_book(book_dir, new_name):
    """Rename a book's folder and the book name stored in its chapters.
    Raises FileExistsError if another book already uses that name (ignoring case)."""
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
            _rewrite(f, f, book=new_name)
            moved[book_dir / f.name] = f
    return moved
