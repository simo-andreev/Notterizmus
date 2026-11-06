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


def _same(a, b):
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
            if _same(ch.path, path):
                return book, i
    return None, None


def neighbor(books, path, delta):
    """The chapter delta steps away in the same book, or None at either end."""
    book, i = find(books, path)
    if book is None:
        return None
    j = i + delta
    return book.chapters[j] if 0 <= j < len(book.chapters) else None
