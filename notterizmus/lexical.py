"""Exporter: the outline as nodes of TopCoding's editor (Lexical), for the clipboard.

Lexical takes a drawing only as its own clipboard JSON (MIME type
application/x-lexical-editor): TopCoding's Excalidraw node has no HTML form. When that
JSON is on the clipboard Lexical uses it for everything and ignores the HTML, so the
text and tables are written here too, as the nodes Lexical itself makes from the HTML
of export.py (checked against TopCoding's editor, 2026-11-17).

Chrome hands a web page only the clipboard formats it knows, plus the ones packed in
its own "web custom data" format; web_custom_data() packs the JSON that way.

No GTK here.
"""
from __future__ import annotations

import json
import struct

from . import drawing

LEXICAL_MIME = "application/x-lexical-editor"
CHROME_CUSTOM_MIME = "chromium/x-web-custom-data"
NAMESPACE = "SummaryEditor"  # TopCoding's editor; Lexical refuses JSON from another one

BOLD, ITALIC, CODE = 1, 2, 16
HEADER_ROW = 1

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


def _table(node):
    header = node.data.get("header")
    rows = []
    for ri, row in enumerate(node.data.get("rows", [])):
        cells = [{"children": [_paragraph(_runs(cell))], **_ELEMENT, "type": "tablecell", "backgroundColor": None,
                  "colSpan": 1, "headerState": HEADER_ROW if header and ri == 0 else 0, "rowSpan": 1}
                 for cell in row]
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
    """The inverse of web_custom_data (for tests)."""
    def uint(pos):
        return struct.unpack_from("<I", data, pos)[0], pos + 4

    def string16(pos):
        n, pos = uint(pos)
        text = data[pos:pos + 2 * n].decode("utf-16-le")
        pos += 2 * n
        return text, pos + (-pos % 4)

    size, pos = uint(0)
    if size != len(data) - 4:
        raise ValueError("the size in front doesn't match the data")
    count, pos = uint(pos)
    out = {}
    for _ in range(count):
        key, pos = string16(pos)
        out[key], pos = string16(pos)
    return out


def clipboard_data(lines, code_prefix=False):
    """What to offer as CHROME_CUSTOM_MIME beside the HTML and plain text, or None when
    the HTML already says everything (no drawing): then Lexical keeps reading the HTML,
    whose result in TopCoding is the long-proven one."""
    if not has_drawing(lines):
        return None
    return web_custom_data({LEXICAL_MIME: clipboard_json(lines, code_prefix)})
