"""Document model: a tree of nodes, independent of GTK.

Node kinds:
  root     - invisible container
  heading  - numbered item (Ⅰ), Ⅰ.1), Ⅰ.1.a) ...)
  bullet   - leaf note with a marker (•, +, -, ... see rules.markers)
  table    - table block; rows live in node.data["rows"]
Future kinds (e.g. "drawing") only need a data codec here, a layout rule
in layout.py, an exporter in export.py and a row widget in ui/rows.py.

Kinds and fields this version doesn't know (written by a newer one) are kept
unchanged when the file is saved; the editor shows such blocks read-only.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

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
        return Run(d.get("t", ""), bool(d.get("b")), bool(d.get("i")))


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
    return {
        "header": bool(d.get("header")),
        "rows": [[runs_from_json(cell) for cell in row] for row in d.get("rows", [])],
    }


DATA_CODECS = {"table": (_table_enc, _table_dec)}

TEXT_KINDS = ("heading", "bullet")
BLOCK_KINDS = ("heading", "bullet", "table")  # any other kind comes from a newer version
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
        kind = d["kind"]
        children = [Node.from_json(c) for c in d.get("children", [])]
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
            marker=d.get("marker", "dot"),
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
        node.kind = "heading"  # top level is always numbered
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
    """Remove node; its children take its place in the parent."""
    par = node.parent
    idx = node.index()
    node.detach()
    for k, c in enumerate(list(node.children)):
        c.parent = None
        if can_contain(par, c):
            par.insert(idx + k, c)
    node.children = []


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

    @classmethod
    def new(cls, book, chapter_no, chapter_title, path=None):
        root = Node("root", children=[Node("heading")])
        return cls(root, book, chapter_no, chapter_title, path)

    def to_json(self):
        return {
            "format": FORMAT,
            "book": self.book,
            "chapter": {"number": self.chapter_no, "title": self.chapter_title},
            **({"lang": self.lang} if self.lang else {}),
            "content": [c.to_json() for c in self.root.children],
        }

    @classmethod
    def from_json(cls, d, path=None):
        ch = d.get("chapter", {})
        root = Node("root", children=[Node.from_json(c) for c in d.get("content", [])])
        if not root.children:
            root.append(Node("heading"))
        return cls(root, d.get("book", ""), ch.get("number", 1), ch.get("title", ""), path, d.get("lang"))

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls.from_json(json.load(f), path)

    def save(self, path=None):
        path = Path(path or self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, ensure_ascii=False, indent=1)
            f.write("\n")
        os.replace(tmp, path)
        self.path = path


def chapter_filename(chapter_no, title):
    safe = "".join("_" if ch in '/\\\0' else ch for ch in title).strip()
    return f"{int(chapter_no):02d} {safe}.notz" if safe else f"{int(chapter_no):02d}.notz"
