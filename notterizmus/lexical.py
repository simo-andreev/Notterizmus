"""The clipboard format of TopCoding's editor (Lexical), both ways.

Lexical takes a drawing only as its own clipboard JSON (MIME type
application/x-lexical-editor): TopCoding's Excalidraw node has no HTML form. When that
JSON is on the clipboard Lexical uses it for everything and ignores the HTML, so the
text and tables are written here too, as the nodes Lexical itself makes from the HTML
of export.py (checked against TopCoding's editor, 2026-11-17).

Browsers hand a web page only the clipboard formats they know, plus the ones packed in
their own custom-data format, which each browser has its own of: web_custom_data() packs
the JSON the Chrome way, moz_custom_data() the Firefox way, and both are offered.

The other way, a copy made in TopCoding's editor carries its JSON packed the same way;
pasted_items() reads the drawings out of it, which its HTML leaves out.

No GTK here.
"""
from __future__ import annotations

import json
import struct

from . import drawing
from .importer import strip_runs
from .model import Run, normalize_runs, runs_text

LEXICAL_MIME = "application/x-lexical-editor"
CHROME_CUSTOM_MIME = "chromium/x-web-custom-data"
FIREFOX_CUSTOM_MIME = "application/x-moz-custom-clipdata"
NAMESPACE = "SummaryEditor"  # TopCoding's editor; Lexical refuses JSON from another one

BOLD, ITALIC, CODE = 1, 2, 16
HEADER_ROW, HEADER_COLUMN = 1, 2  # Lexical's TableCellHeaderStates, a bitmask

_ELEMENT = {"direction": None, "format": "", "indent": 0, "version": 1}


def _text(text, fmt):
    return {"detail": 0, "format": fmt, "mode": "normal", "style": "", "text": text, "type": "text", "version": 1}


def _paragraph(children):
    return {"children": children, **_ELEMENT, "type": "paragraph", "textFormat": 0, "textStyle": ""}


def _add_text(children, text, fmt):
    """Append text, joined to the text before it when the formatting is the same."""
    if not text:
        return
    if children and children[-1]["type"] == "text" and children[-1]["format"] == fmt:
        children[-1]["text"] += text
    else:
        children.append(_text(text, fmt))


def _fmt(bold, italic, code=False):
    return (BOLD if bold else 0) | (ITALIC if italic else 0) | (CODE if code else 0)


def _runs(runs):
    children = []
    for r in runs:
        _add_text(children, r.text, _fmt(r.bold, r.italic))
    return children


def _header_state(header, ri, ci):
    """What TopCoding's editor makes of the <th> cells of our HTML: row headers, and in the
    first column a row and column header (3), checked 2026-11-17 (CR28)."""
    if not header or ri:
        return 0
    return HEADER_ROW | HEADER_COLUMN if ci == 0 else HEADER_ROW


def _table(node):
    header = node.data.get("header")
    rows = []
    for ri, row in enumerate(node.data.get("rows", [])):
        cells = [{"children": [_paragraph(_runs(cell))], **_ELEMENT, "type": "tablecell", "backgroundColor": None,
                  "colSpan": 1, "headerState": _header_state(header, ri, ci), "rowSpan": 1}
                 for ci, cell in enumerate(row)]
        rows.append({"children": cells, **_ELEMENT, "type": "tablerow"})
    return {"children": rows, **_ELEMENT, "type": "table"}


def _drawing(node):
    return {"data": drawing.scene_json(node.data), "type": "excalidraw", "version": 1}


def to_nodes(lines, code_prefix=False):
    """Top-level Lexical nodes for layout lines: paragraphs (lines joined by line breaks),
    broken by tables and drawings, as export.to_html breaks its <p> for tables."""
    nodes = []
    para = None  # the lines of the paragraph being built, each a list of text nodes

    def flush():
        nonlocal para
        if para:
            children = []
            for i, line in enumerate(para):
                if i:
                    children.append({"type": "linebreak", "version": 1})
                children += line
            nodes.append(_paragraph(children))
        para = None

    for ln in lines:
        if ln.kind == "unknown":
            continue
        if ln.kind == "table":
            flush()
            nodes.append(_table(ln.node))
            continue
        if ln.kind == "drawing":
            if not drawing.is_empty(ln.node.data):
                flush()
                nodes.append(_drawing(ln.node))
            continue
        line = []
        for s in ln.segs():
            text = s.text.rstrip() if ln.kind == "spacer" else s.text
            _add_text(line, text, _fmt(s.bold, s.italic, code_prefix and s.role == "connector"))
        para = (para or []) + [line]
    flush()
    return nodes


def has_drawing(lines):
    return any(ln.kind == "drawing" and not drawing.is_empty(ln.node.data) for ln in lines)


def clipboard_json(lines, code_prefix=False):
    return json.dumps({"namespace": NAMESPACE, "nodes": to_nodes(lines, code_prefix)}, ensure_ascii=False)


def _string16(s):
    data = s.encode("utf-16-le")
    return struct.pack("<I", len(data) // 2) + data + b"\0" * (-len(data) % 4)


def web_custom_data(items):
    """Chrome's "web custom data" (a base::Pickle): a count, then for each item its MIME
    type and its text, both as UTF-16 with a length in front and padded to four bytes."""
    payload = struct.pack("<I", len(items)) + b"".join(_string16(k) + _string16(v) for k, v in items.items())
    return struct.pack("<I", len(payload)) + payload


def read_web_custom_data(data):
    """The inverse of web_custom_data: the items of Chrome's custom data."""
    def uint(pos):
        return struct.unpack_from("<I", data, pos)[0], pos + 4

    def string16(pos):
        n, pos = uint(pos)
        if pos + 2 * n > len(data):
            raise ValueError("a text runs past the end")
        text = data[pos:pos + 2 * n].decode("utf-16-le")
        pos += 2 * n
        return text, pos + (-pos % 4)

    size, pos = uint(0)
    if size > len(data) - 4:
        raise ValueError("the size in front is more than the data")
    count, pos = uint(pos)
    out = {}
    for _ in range(count):
        key, pos = string16(pos)
        out[key], pos = string16(pos)
    return out


_MOZ_STRING, _MOZ_END = 1, 0  # Firefox's eCustomClipboardTypeId_String / _None


def moz_custom_data(items):
    """Firefox's custom clipboard data (DataTransfer.cpp): for each item a big-endian 1,
    then its MIME type and its text, both as UTF-16LE with their length in bytes in
    front (big-endian); a big-endian 0 ends it."""
    def string16(s):
        data = s.encode("utf-16-le")
        return struct.pack(">I", len(data)) + data
    return b"".join(struct.pack(">I", _MOZ_STRING) + string16(k) + string16(v) for k, v in items.items()) \
        + struct.pack(">I", _MOZ_END)


def read_moz_custom_data(data):
    """The inverse of moz_custom_data: the items of Firefox's custom data."""
    out, pos = {}, 0

    def string16():
        nonlocal pos
        (n,) = struct.unpack_from(">I", data, pos)
        if pos + 4 + n > len(data):
            raise ValueError("a text runs past the end")
        text = data[pos + 4:pos + 4 + n].decode("utf-16-le")
        pos += 4 + n
        return text

    while True:
        (kind,) = struct.unpack_from(">I", data, pos)
        pos += 4
        if kind == _MOZ_END:
            break
        if kind != _MOZ_STRING:
            raise ValueError(f"unknown item kind {kind}")
        key = string16()
        out[key] = string16()
    return out


def clipboard_data(lines, code_prefix=False):
    """(MIME type, data) pairs to offer beside the HTML and plain text: the editor's JSON
    in Chrome's and in Firefox's custom format. None when the HTML already says everything
    (no drawing): then Lexical keeps reading the HTML, whose result in TopCoding is the
    long-proven one."""
    if not has_drawing(lines):
        return None
    items = {LEXICAL_MIME: clipboard_json(lines, code_prefix)}
    return [(CHROME_CUSTOM_MIME, web_custom_data(items)), (FIREFOX_CUSTOM_MIME, moz_custom_data(items))]


# --- reading: a copy made in TopCoding's editor ------------------------------------

# Element nodes that end a line, as their HTML (<p>, <h1>, <li>, ...) does; other
# elements with children (links, say) are part of the line they are in.
_LINE_ELEMENTS = {"paragraph", "heading", "quote", "listitem", "code"}


class _Reader:
    """Lexical nodes -> pasted items in importer.html_items' form."""

    def __init__(self):
        self.items = []
        self.cur = []

    def newline(self):
        self.items.append(("line", normalize_runs(self.cur)))
        self.cur = []

    def end(self):
        if self.cur:
            self.newline()
        return self.items

    def read(self, node):
        if not isinstance(node, dict):
            return
        kind = node.get("type")
        if kind == "text":
            fmt = node.get("format") if isinstance(node.get("format"), int) else 0
            self.cur.append(Run(str(node.get("text") or ""), bool(fmt & BOLD), bool(fmt & ITALIC)))
        elif kind == "tab":
            self.cur.append(Run("\t"))
        elif kind == "linebreak":
            self.newline()
        elif kind == "table":
            self.end()
            self.table(node)
        elif kind == "excalidraw":
            self.end()
            data = drawing.from_scene(node.get("data"))
            if data is not None and not drawing.is_empty(data):
                self.items.append(("drawing", data))
        elif isinstance(node.get("children"), list):
            for child in node["children"]:
                self.read(child)
            if kind in _LINE_ELEMENTS and (self.cur or not node["children"]):
                self.newline()

    def table(self, node):
        rows, header = [], False
        for row in _children(node, "tablerow"):
            cells = []
            for cell in _children(row, "tablecell"):
                if not rows and cell.get("headerState"):
                    header = True
                inner = _Reader()
                children = cell.get("children")
                for child in children if isinstance(children, list) else []:
                    inner.read(child)
                runs = []
                for item in inner.end():  # a cell's lines are joined, as its HTML's are
                    if item[0] == "line" and runs_text(item[1]).strip():
                        if runs and not runs_text(runs)[-1].isspace():
                            runs.append(Run(" "))
                        runs += item[1]
                cells.append(strip_runs(runs))
            rows.append(cells)
        if rows:
            self.items.append(("table", rows, header))


def _children(node, kind):
    children = node.get("children")
    return [c for c in children if isinstance(c, dict) and c.get("type") == kind] if isinstance(children, list) else []


def to_items(nodes):
    """Lexical nodes, as the editor copies them, as pasted items in the form of
    importer.html_items: ("line", runs), ("table", rows, header) and ("drawing", data),
    so that the outline is worked out from them as from the editor's HTML. Drawings that
    are empty or can't be read are left out."""
    reader = _Reader()
    for node in nodes:
        reader.read(node)
    return reader.end()


def pasted_items(mime, data):
    """The items of a copy from TopCoding's editor that has a drawing in it, from a
    browser's custom clipboard data (Chrome's or Firefox's, by `mime`). None when there
    is no drawing or the data can't be read: the HTML beside it then says everything,
    and is what the paste has always used."""
    reader = read_web_custom_data if mime == CHROME_CUSTOM_MIME else read_moz_custom_data
    # Any app can put data under these names: anything that doesn't read as expected,
    # however it fails, leaves the paste to the HTML (CR14 in CODE_REVIEW.md).
    try:
        text = reader(bytes(data)).get(LEXICAL_MIME)
        payload = json.loads(text) if text else None
        nodes = payload.get("nodes") if isinstance(payload, dict) else None
        if not isinstance(nodes, list):
            return None
        items = to_items(nodes)
    except (ValueError, TypeError, AttributeError, KeyError, IndexError, struct.error, RecursionError):
        return None  # (UnicodeDecodeError and JSONDecodeError are ValueErrors)
    return items if any(it[0] == "drawing" for it in items) else None
