"""Exporters: HTML for pasting into TopCoding (Lexical editor) and plain text."""
from __future__ import annotations

from html import escape

from .model import runs_text

# Lexical collapses whitespace on paste unless the parent element is white-space: pre*.
_PRE = '<span style="white-space: pre-wrap;">{}</span>'


def _seg_html(text, bold, italic):
    if not text:
        return ""
    h = _PRE.format(escape(text, quote=False))
    if italic:
        h = f"<em>{h}</em>"
    if bold:
        h = f"<strong>{h}</strong>"
    return h


def _runs_html(runs):
    return "".join(_seg_html(r.text, r.bold, r.italic) for r in runs)


def _table_html(node):
    rows = node.data.get("rows", [])
    header = node.data.get("header")
    out = ["<table><tbody>"]
    for ri, row in enumerate(rows):
        tag = "th" if header and ri == 0 else "td"
        out.append("<tr>")
        for cell in row:
            out.append(f"<{tag}><p>{_runs_html(cell) or '<br>'}</p></{tag}>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _line_html(ln, code_prefix):
    segs = ln.segs()
    if ln.kind == "spacer":
        segs = [type(s)(s.text.rstrip(), s.role, s.bold, s.italic) for s in segs]
    out = []
    for s in segs:
        h = _seg_html(s.text, s.bold, s.italic)
        if code_prefix and s.role == "connector" and h:
            h = f"<code>{h}</code>"
        out.append(h)
    return "".join(out)


def to_html(lines, code_prefix=False):
    parts = ['<meta charset="utf-8">']
    para = []

    def flush():
        if para:
            parts.append("<p>" + "<br>".join(para) + "</p>")
            para.clear()

    for ln in lines:
        if ln.kind == "table":
            flush()
            parts.append(_table_html(ln.node))
            continue
        para.append(_line_html(ln, code_prefix))
    flush()
    return "".join(parts)


def _table_plain(prefix, node):
    rows = [[runs_text(c) for c in row] for row in node.data.get("rows", [])]
    if not rows:
        return []
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    w = [max(len(r[i]) for r in rows) for i in range(ncol)]
    hr = lambda l, m, r: prefix + l + m.join("─" * (x + 2) for x in w) + r
    out = [hr("┌", "┬", "┐")]
    for i, r in enumerate(rows):
        out.append(prefix + "│" + "│".join(f" {c.ljust(w[j])} " for j, c in enumerate(r)) + "│")
        if i == 0 and node.data.get("header") and len(rows) > 1:
            out.append(hr("├", "┼", "┤"))
    out.append(hr("└", "┴", "┘"))
    return out


def to_plain(lines):
    out = []
    for ln in lines:
        if ln.kind == "table":
            out += _table_plain(ln.prefix_text(), ln.node)
        else:
            out.append("".join(s.text for s in ln.segs()).rstrip())
    return "\n".join(out) + "\n"


runs_html = _runs_html
