"""Turn pasted text/HTML back into outline nodes.

Recognises the app's own output (and hand-written notes in the same style):
tree connectors are dropped, labels like "Ⅱ.1.a)" / "II.1.a)" / "2.1)" give the
depth of numbered items, and leading markers (•, +, -, !, ?, *) give bullets, nested
by indentation. Numbering is regenerated, so pasted labels never go stale.
"""
from __future__ import annotations

import copy
import re
from html.parser import HTMLParser

from .model import Node, Run, normalize_runs, runs_text

_ROMAN = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫⅬⅭⅮⅯⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹⅺⅻⅼⅽⅾⅿ"
_LATIN_ROMAN = (r"(?=[IVXLCDMivxlcdm])(?:M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
                r"|m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3}))")
_CYRILLIC = "а-яА-ЯёЁ"
_END = r"\)(?:[ \t ]+|$)"  # the bracket, then spaces (no-break ones too) or the end
# A part of a dotted label ("Ⅱ.1.ab)"): the dots make it one, letters and all.
_PART = rf"(?:[{_ROMAN}]+|\d+|[A-Za-z]{{1,4}}|[{_CYRILLIC}])"
# A label of one part is a number, a roman numeral or a single letter, never a word:
# any one to four letters made "Yes) that is right" a numbered item (CR24 in CODE_REVIEW.md).
_ONE = rf"(?:[{_ROMAN}]+|\d+|{_LATIN_ROMAN}|[A-Za-z{_CYRILLIC}])"
LABEL_RE = re.compile(rf"({_PART}(?:\.{_PART})+|{_ONE}){_END}")
# ... unless the rules number the top level with letters: then "aa)" is the 27th item.
_LETTERS_RE = re.compile(rf"([A-Za-z]{{1,4}}){_END}")
PREFIX_RE = re.compile(r"[ \t │├└┃┣┗┠┖╎┆|]*")
EXTRA_MARKERS = {"*": "dot", "·": "dot", "▪": "dot", "◦": "dot", "‣": "dot", "–": "minus", "—": "minus"}


def drop_chars(runs, n):
    out = []
    for r in runs:
        if n >= len(r.text):
            n -= len(r.text)
            continue
        out.append(Run(r.text[n:], r.bold, r.italic))
        n = 0
    return out


def strip_runs(runs):
    """Trim trailing whitespace."""
    runs = normalize_runs(runs)
    while runs and not runs[-1].text.rstrip():
        runs.pop()
    if runs:
        runs[-1] = Run(runs[-1].text.rstrip(), runs[-1].bold, runs[-1].italic)
    return runs


def text_items(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    return [("line", [Run(line)]) for line in text.split("\n")]


def join_lines(lines):
    """Lines (lists of runs) -> one run list: line breaks become spaces, blank lines
    are dropped, and words hyphenated across a line break are re-joined."""
    out = []
    for runs in lines:
        runs = strip_runs([Run(r.text.replace("\n", " "), r.bold, r.italic) for r in runs])
        if runs:
            runs[0] = Run(runs[0].text.lstrip(), runs[0].bold, runs[0].italic)
        if not runs_text(runs):
            continue
        if out:
            prev = runs_text(out)
            nxt = runs_text(runs)
            if re.search(r"[^\W\d_]-$", prev) and nxt[:1].islower():
                last = out[-1]
                out[-1] = Run(last.text[:-1], last.bold, last.italic)
            else:
                out.append(Run(" "))
        out += runs
    return normalize_runs(out)


# --- HTML ----------------------------------------------------------------------

_BLOCKS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "ul", "ol",
           "section", "article", "header", "footer"}
_VOID = {"br", "img", "meta", "link", "hr", "input", "col", "wbr"}
_SKIP = {"style", "script", "head", "title"}


def _style(attrs):
    st = {}
    for k, v in attrs:
        if k == "style" and v:
            for decl in v.split(";"):
                if ":" in decl:
                    a, b = decl.split(":", 1)
                    st[a.strip().lower()] = b.strip().lower()
    return st


class _HTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.cur = []
        self.stack = []  # (tag, bold|None, italic|None, pre|None)
        self.skip = 0
        self.table = self.row = self.cell = None
        self.header = False

    def _eff(self, idx):
        for entry in reversed(self.stack):
            if entry[idx] is not None:
                return entry[idx]
        return False

    def _newline(self):
        if self.cell is not None:
            if self.cell and not self.cell[-1].text.endswith(" "):
                self.cell.append(Run(" "))
            return
        self.items.append(("line", self.cur))
        self.cur = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
            return
        if tag == "br":
            self._newline()
            return
        if tag == "table":
            if self.cur:
                self._newline()
            self.table, self.header = [], False
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
            if tag == "th" and self.table == []:
                self.header = True
        elif tag in _BLOCKS and self.cur:
            self._newline()
        if tag in _VOID:
            return
        st = _style(attrs)
        bold = True if tag in ("b", "strong") else None
        fw = st.get("font-weight")
        if fw:
            bold = fw in ("bold", "bolder") or (fw.isdigit() and int(fw) >= 600)
        italic = True if tag in ("i", "em") else None
        if st.get("font-style"):
            italic = st["font-style"] in ("italic", "oblique")
        ws = st.get("white-space")
        pre = True if tag == "pre" or (ws and ws.startswith("pre")) else None
        self.stack.append((tag, bold, italic, pre))

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(strip_runs(self.cell))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            if self.table:
                self.items.append(("table", self.table, self.header))
            self.table = None
        elif tag in _BLOCKS:
            self._newline()
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.skip:
            return
        data = data.replace(" ", " ")
        if not self._eff(3):
            if not data.strip() and "\n" in data:
                return
            data = re.sub(r"\s+", " ", data)
        if not data:
            return
        target = self.cell if self.cell is not None else self.cur
        target.append(Run(data, self._eff(1), self._eff(2)))

    def close(self):
        super().close()
        if self.cur:
            self._newline()


def html_items(html):
    p = _HTML()
    p.feed(html)
    p.close()
    return [(k, normalize_runs(v)) if k == "line" else (k, v, *rest)
            for k, v, *rest in p.items]


# --- structure -------------------------------------------------------------------

def _marker_map(rules):
    m = {spec["symbol"]: name for name, spec in rules["markers"].items() if spec.get("symbol")}
    for sym, name in EXTRA_MARKERS.items():
        if name in rules["markers"]:
            m.setdefault(sym, name)
    return m


def parse(items, rules):
    """Returns a list of root nodes, or None when nothing looks structured."""
    markers = sorted(_marker_map(rules).items(), key=lambda kv: -len(kv[0]))
    letters = rules["numbering"]["levels"][0] in ("alpha_lower", "alpha_upper")
    parsed = []
    for it in items:
        if it[0] in ("table", "drawing"):
            parsed.append(it)
            continue
        runs = it[1]
        text = runs_text(runs)
        pre = PREFIX_RE.match(text).end()
        rest = text[pre:]
        if not rest.strip():
            continue  # blank or connector-only spacer line
        lm = LABEL_RE.match(rest) or (letters and _LETTERS_RE.match(rest))
        if lm:
            depth = lm.group(1).count(".") + 1
            parsed.append(("heading", depth, strip_runs(drop_chars(runs, pre + lm.end()))))
            continue
        for sym, name in markers:
            if rest.startswith(sym) and (len(rest) == len(sym) or rest[len(sym)] in " \t "):
                skip = len(sym) + (len(rest[len(sym):]) - len(rest[len(sym):].lstrip()))
                parsed.append(("bullet", pre, strip_runs(drop_chars(runs, pre + skip)), name))
                break
        else:
            parsed.append(("plain", pre, strip_runs(drop_chars(runs, pre)), "dot"))
    if not any(p[0] in ("heading", "bullet") for p in parsed):
        return None

    min_depth = min((p[1] for p in parsed if p[0] == "heading"), default=1)
    forest, hstack, bstack = [], [], []

    def attach(parent, node):
        (parent.append(node) if parent is not None else forest.append(node))

    for p in parsed:
        if p[0] == "heading":
            d = p[1] - min_depth
            del hstack[d:]
            n = Node("heading", p[2])
            attach(hstack[-1] if hstack else None, n)
            hstack.append(n)
            bstack = []
        elif p[0] in ("bullet", "plain"):
            ind = p[1]
            while bstack and bstack[-1][0] >= ind:
                bstack.pop()
            parent = bstack[-1][1] if bstack else (hstack[-1] if hstack else None)
            n = Node("bullet", p[2], marker=p[3])
            attach(parent, n)
            bstack.append((ind, n))
        else:  # a table or a drawing: under the numbered item, where Ctrl+T or Ctrl+D puts one
            attach(hstack[-1] if hstack else None, block_node(p))
    return forest


def table_node(rows, header=False):
    """A table node from pasted rows (lists of cells, each a list of runs)."""
    return Node("table", data={"header": bool(header), "rows": _square(rows)})


def block_node(item):
    """A table or drawing node from a pasted ("table", rows, header) or ("drawing", data) item."""
    return table_node(item[1], item[2]) if item[0] == "table" else Node("drawing", data=copy.deepcopy(item[1]))


def block_nodes(items):
    """The tables and drawings among pasted items, as nodes, in order."""
    return [block_node(it) for it in items if it[0] in ("table", "drawing")]


def _square(rows):
    ncol = max((len(r) for r in rows), default=1) or 1
    return [r + [[] for _ in range(ncol - len(r))] for r in rows]
