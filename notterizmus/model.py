"""Document model: a tree of nodes, independent of GTK.

Node kinds:
  root     - invisible container
  heading  - numbered item (Ⅰ), Ⅰ.1), Ⅰ.1.a) ...)
  bullet   - leaf note with a marker (•, +, -, !, ?, ... see rules.markers)
  table    - table block; rows live in node.data["rows"]
  drawing  - Excalidraw scene in node.data (see drawing.py)
A new kind only needs a data codec here, a layout rule in layout.py, an
exporter in export.py and a row widget in ui/rows.py.

Kinds and fields this version doesn't know (written by a newer one) are kept
unchanged when the file is saved; the editor shows such blocks read-only. That goes for
the fields of the file itself too (Document.extra), and for its format name.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import drawing
from .files import atomic_write

FORMAT = "notterizmus/1"


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False

    def to_json(self):
        d = {"t": self.text}
        if self.bold:
            d["b"] = True
        if self.italic:
            d["i"] = True
        return d

    @staticmethod
    def from_json(d):
        text = d.get("t")
        text = "" if text is None else text
        if not isinstance(text, str):
            raise TypeError("a piece of text isn't text")
        return Run(text, bool(d.get("b")), bool(d.get("i")))


def runs_text(runs):
    return "".join(r.text for r in runs)


def normalize_runs(runs):
    out = []
    for r in runs:
        if not r.text:
            continue
        if out and out[-1].bold == r.bold and out[-1].italic == r.italic:
            out[-1] = Run(out[-1].text + r.text, r.bold, r.italic)
        else:
            out.append(Run(r.text, r.bold, r.italic))
    return out


def runs_to_json(runs):
    return [r.to_json() for r in runs]


def runs_from_json(lst):
    return [Run.from_json(d) for d in lst or []]


# --- kind-specific payload codecs -----------------------------------------

def _table_enc(data):
    return {
        "header": bool(data.get("header")),
        "rows": [[runs_to_json(cell) for cell in row] for row in data.get("rows", [])],
    }


def _table_dec(d):
    """A table's data as the editor uses it: square. Rows of different lengths (a
    hand-edited file, a newer version) made Delete Column raise and Tab skip cells
    (CR47 in CODE_REVIEW.md)."""
    rows = [[runs_from_json(cell) for cell in row] for row in d.get("rows", [])]
    width = max((len(row) for row in rows), default=0)
    return {
        "header": bool(d.get("header")),
        "rows": [row + [[] for _ in range(width - len(row))] for row in rows],
    }


DATA_CODECS = {"table": (_table_enc, _table_dec), "drawing": (drawing.encode, drawing.decode)}

TEXT_KINDS = ("heading", "bullet")
BLOCK_KINDS = ("heading", "bullet", "table", "drawing")  # any other kind comes from a newer version
_KNOWN_FIELDS = ("kind", "id", "runs", "marker", "data", "children")


def is_text(node):
    return node.kind in TEXT_KINDS


def new_table_data(rows=2, cols=2):
    return {"header": False, "rows": [[[] for _ in range(cols)] for _ in range(rows)]}


# --- tree --------------------------------------------------------------------

class Node:
    def __init__(self, kind, runs=None, marker="dot", children=None, data=None, id=None):
        self.kind = kind
        self.runs = runs or []
        self.marker = marker
        self.data = data or {}
        self.id = id or uuid.uuid4().hex[:12]
        self.parent = None
        self.children = []
        self.extra = {}  # fields from a newer version, saved back unchanged
        for c in children or []:
            self.insert(len(self.children), c)

    def __repr__(self):
        return f"<Node {self.kind} {runs_text(self.runs)[:20]!r}>"

    @property
    def text(self):
        return runs_text(self.runs)

    def insert(self, idx, child):
        child.parent = self
        self.children.insert(idx, child)

    def append(self, child):
        self.insert(len(self.children), child)
        return child

    def detach(self):
        self.parent.children.remove(self)
        self.parent = None

    def index(self):
        return self.parent.children.index(self)

    def prev_sibling(self):
        i = self.index()
        return self.parent.children[i - 1] if i > 0 else None

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def to_json(self):
        d = {"kind": self.kind, "id": self.id}
        if self.kind not in BLOCK_KINDS and self.kind != "root":
            d.update(self.extra)  # a block from a newer version: exactly as it was read
            if self.children:
                d["children"] = [c.to_json() for c in self.children]
            return d
        if self.kind in ("heading", "bullet"):
            d["runs"] = runs_to_json(self.runs)
        if self.kind == "bullet":
            d["marker"] = self.marker
        if self.kind in DATA_CODECS:
            d["data"] = DATA_CODECS[self.kind][0](self.data)
        elif self.data:
            d["data"] = self.data
        if self.children:
            d["children"] = [c.to_json() for c in self.children]
        for k, v in self.extra.items():
            d.setdefault(k, v)
        return d

    @staticmethod
    def from_json(d):
        """Raises KeyError, TypeError or AttributeError for JSON that isn't an item
        (Document.from_json turns those into one ValueError)."""
        kind = d["kind"]
        if not isinstance(kind, str) or not isinstance(d.get("id") or "", str) \
                or (kind in BLOCK_KINDS and d.get("marker") is not None
                                          and not isinstance(d["marker"], str)):
            raise TypeError("an item's kind, id or marker isn't text")
        children = d.get("children") or []
        if not isinstance(children, list):
            raise TypeError("an item's sub-items aren't a list")
        children = [Node.from_json(c) for c in children]
        if kind not in BLOCK_KINDS:
            node = Node(kind, id=d.get("id"), children=children)
            node.extra = {k: v for k, v in d.items() if k not in ("kind", "id", "children")}
            return node
        data = d.get("data") or {}
        if kind in DATA_CODECS:
            data = DATA_CODECS[kind][1](data)
        node = Node(
            kind,
            runs=runs_from_json(d.get("runs")),
            marker="dot" if d.get("marker") is None else d["marker"],
            data=data,
            id=d.get("id"),
            children=children,
        )
        node.extra = {k: v for k, v in d.items() if k not in _KNOWN_FIELDS}
        return node


def can_contain(parent, child):
    if parent.kind in ("root", "heading"):
        return True
    if parent.kind == "bullet":
        return child.kind != "heading"
    return False


def display_order(root):
    return [n for n in root.walk() if n is not root]


def editable_order(root):
    """display_order() without what the editor doesn't show: the sub-items of a block from
    a newer version, kept unchanged in the file but never edited (CR12 in CODE_REVIEW.md)."""
    out = []

    def add(node):
        for c in node.children:
            out.append(c)
            if c.kind in BLOCK_KINDS:
                add(c)
    add(root)
    return out


# --- structural operations (return True when something changed) --------------

def indent(node):
    prev = node.prev_sibling()
    if prev is None or not can_contain(prev, node):
        return False
    node.detach()
    prev.append(node)
    return True


def outdent(node):
    par = node.parent
    if par is None or par.kind == "root":
        return False
    gp = par.parent
    if not can_contain(gp, node):
        return False
    idx = par.index()
    node.detach()
    gp.insert(idx + 1, node)
    if gp.kind == "root" and node.kind == "bullet":
        node.kind = "heading"  # a bullet outdented to the top level is the next numbered item
    return True


def move(node, delta):
    sibs = node.parent.children
    i = sibs.index(node)
    j = i + delta
    if not 0 <= j < len(sibs):
        return False
    sibs[i], sibs[j] = sibs[j], sibs[i]
    return True


def remove_promote(node):
    """Remove node; its children take its place in the parent. A bullet that lands at
    the top level becomes a numbered item, as when it is outdented there."""
    par = node.parent
    idx = node.index()
    node.detach()
    for c in list(node.children):
        c.parent = None
        if can_contain(par, c):
            if par.kind == "root" and c.kind == "bullet":
                c.kind = "heading"  # as when it is outdented there
            par.insert(idx, c)
            idx += 1
    node.children = []


def _removable(node):
    """node is still in a chapter, and not inside a block from a newer version (whose
    sub-items have no rows: they go, or stay, with that block)."""
    p = node.parent
    while p is not None and p.kind != "root":
        if p.kind not in BLOCK_KINDS:
            return False
        p = p.parent
    return p is not None


def remove_items(nodes):
    """Remove exactly these items. Sub-items that aren't among them move up into the place
    of the nearest one removed, as with remove_promote; a block from a newer version goes
    with everything under it."""
    for n in nodes:
        if not _removable(n):
            continue
        if n.kind in BLOCK_KINDS:
            remove_promote(n)
        else:
            n.detach()


def selected_json(nodes):
    """JSON of exactly these items, in their outline shape: an item between them that isn't
    among them gives way to its sub-items that are, as remove_items would. A block from a
    newer version goes with everything under it."""
    ids = {n.id for n in nodes}

    def keep(n):
        kids = [] if n.id in ids and n.kind not in BLOCK_KINDS else [j for c in n.children for j in keep(c)]
        if n.id not in ids:
            return kids
        d = n.to_json()
        if n.kind in BLOCK_KINDS:
            d.pop("children", None)
            if kids:
                d["children"] = kids
        return [d]

    def outermost(n):
        p = n.parent
        while p is not None:
            if p.id in ids:
                return False
            p = p.parent
        return True

    return [j for n in nodes if outermost(n) for j in keep(n)]


def set_kind(node, kind, marker=None):
    """Change heading <-> bullet. Returns an error string or None."""
    if kind == "heading" and not can_contain(node.parent, Node("heading")):
        return "A numbered item can't sit under a bullet."
    if kind == "bullet" and any(c.kind == "heading" for c in node.children):
        return "This item has numbered sub-items, so it can't become a bullet."
    node.kind = kind
    if marker:
        node.marker = marker
    return None


def fresh_ids(node):
    for n in node.walk():
        n.id = uuid.uuid4().hex[:12]
    return node


def enclosing_heading(node):
    """node itself if it is a heading, else the nearest heading ancestor (or None)."""
    n = node
    while n is not None and n.kind != "heading":
        n = n.parent
    return n


def heading_numbers(node):
    """1-based position among heading siblings at each level, e.g. Ⅱ.1.a -> [2, 1, 1]."""
    nums = []
    n = node
    while n is not None and n.kind == "heading":
        sibs = [c for c in n.parent.children if c.kind == "heading"]
        nums.insert(0, sibs.index(n) + 1)
        n = n.parent
    return nums


def leaf_insert_index(heading):
    """Where new bullets/tables go inside a heading: after its leading leaves."""
    for i, c in enumerate(heading.children):
        if c.kind == "heading":
            return i
    return len(heading.children)


# --- document ------------------------------------------------------------------

class Document:
    def __init__(self, root=None, book="", chapter_no=1, chapter_title="", path=None, lang=None):
        self.root = root or Node("root")
        self.lang = lang  # spell-check language, e.g. "en_US"
        self.book = book
        self.chapter_no = chapter_no
        self.chapter_title = chapter_title
        self.path = Path(path) if path else None
        # From a file written by a newer version, saved back unchanged: its format name,
        # and the fields of the file and of its "chapter" entry this version doesn't know.
        self.format = FORMAT
        self.extra = {}
        self.chapter_extra = {}
        self._disk = None  # the file as this document last read or wrote it (see changed_on_disk)

    @classmethod
    def new(cls, book, chapter_no, chapter_title, path=None):
        root = Node("root", children=[Node("heading")])
        return cls(root, book, chapter_no, chapter_title, path)

    def to_json(self):
        d = {
            "format": self.format,
            "book": self.book,
            "chapter": {**self.chapter_extra, "number": self.chapter_no, "title": self.chapter_title},
            **({"lang": self.lang} if self.lang else {}),
            "content": [c.to_json() for c in self.root.children],
        }
        for k, v in self.extra.items():
            d.setdefault(k, v)
        return d

    @classmethod
    def from_json(cls, d, path=None):
        """Raises ValueError for JSON that isn't a chapter: the wrong shape, or a value of
        the wrong kind. (Fields that are missing or null get their defaults.)"""
        try:
            ch = d.get("chapter") or {}
            book, title, number = d.get("book") or "", ch.get("title") or "", ch.get("number")
            lang, fmt, content = d.get("lang"), d.get("format") or FORMAT, d.get("content") or []
            number = 1 if number is None else number
            if isinstance(number, float) and number.is_integer():
                number = int(number)
            if not (isinstance(book, str) and isinstance(title, str) and type(number) is int
                    and isinstance(fmt, str) and (lang is None or isinstance(lang, str))
                    and isinstance(content, list)):
                raise TypeError("its book, chapter, language or content isn't what a chapter has")
            root = Node("root", children=[Node.from_json(c) for c in content])
            if not root.children:
                root.append(Node("heading"))
            doc = cls(root, book, number, title, path, lang)
            doc.format = fmt
            doc.extra = {k: v for k, v in d.items() if k not in ("format", "book", "chapter", "lang", "content")}
            doc.chapter_extra = {k: v for k, v in ch.items() if k not in ("number", "title")}
            return doc
        except (AttributeError, KeyError, TypeError, RecursionError) as e:  # Recursion: nested too deep
            raise ValueError("this isn't a Notterizmus chapter file") from e

    @classmethod
    def load(cls, path):
        """Raises OSError if the file can't be read, ValueError if it isn't a chapter."""
        disk = _disk_state(path)  # before reading: a change made meanwhile still shows
        with open(path, encoding="utf-8") as f:
            try:
                data = json.load(f)
            except RecursionError as e:  # nested too deep to read
                raise ValueError("this isn't a Notterizmus chapter file") from e
        doc = cls.from_json(data, path)
        doc._disk = disk
        return doc

    def dumps(self):
        """The chapter file's text."""
        return json.dumps(self.to_json(), ensure_ascii=False, indent=1) + "\n"

    def save(self, path=None):
        """Write the chapter in one step (files.atomic_write): a save that fails (a full
        disk, say) leaves the file as it was, and nothing half written in the book's folder."""
        path = Path(path or self.path)
        with atomic_write(path) as f:
            f.write(self.dumps())
        self.path = path
        self.remember_disk()

    def remember_disk(self):
        """Take the file as it is now as this document's own: after it was written for
        this document by other means (a chapter renamed or renumbered, say)."""
        self._disk = _disk_state(self.path) if self.path else None

    def changed_on_disk(self):
        """Whether another program changed or replaced the file since this document last
        read or wrote it: a sync tool, a second machine (CR10 in CODE_REVIEW.md, R16). A file
        that is gone counts as unchanged, so a save brings it back, as before."""
        if self._disk is None or self.path is None:
            return False
        now = _disk_state(self.path)
        return now is not None and now != self._disk


def _disk_state(path):
    """What tells one version of a file from another: a file replaced in one step (as sync
    tools and this app write) is a new inode; one rewritten in place has a new modification
    time and usually size. None if there is no file."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_ino, st.st_mtime_ns, st.st_size


NAME_MAX = 255  # bytes in a file or folder name


def fit_name(text, limit=NAME_MAX):
    """text shortened to at most limit bytes of UTF-8, on a character boundary."""
    data = text.encode("utf-8")
    return text if len(data) <= limit else data[:limit].decode("utf-8", "ignore").rstrip()


def chapter_filename(chapter_no, title):
    """'NN Title.notz', shortened to fit a file name (CR15 in CODE_REVIEW.md); the whole
    title stays inside the file."""
    safe = "".join("_" if ch in '/\\\0' else ch for ch in title).strip()
    number = f"{int(chapter_no):02d}"
    if not safe:
        return f"{number}.notz"
    return f"{number} {fit_name(safe, NAME_MAX - len(number) - len(' .notz'))}.notz"
