"""Turns the node tree into display lines with numbering and tree connectors.

Shape produced (default rules):

    Ⅱ) 4-step framework:
    │    • note directly under Ⅱ
    ├ Ⅱ.1) Step 1
    │ │
    │ ├ Ⅱ.1.a) Review given task:
    │ │      • What is the product/system?
    │ │
    │ └ Ⅱ.1.c) Check ...
    │
    └ Ⅱ.2) Step 2
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import BLOCK_KINDS, Run


@dataclass
class Seg:
    text: str
    role: str = "text"  # connector | label | marker | text
    bold: bool = False
    italic: bool = False


@dataclass
class Line:
    kind: str  # item | spacer | blank | table | drawing | unknown (a block from a newer version)
    prefix: list = field(default_factory=list)  # list[Seg]
    node: object = None

    def segs(self):
        out = list(self.prefix)
        if self.kind == "item" and self.node is not None:
            out += [Seg(r.text, "text", r.bold, r.italic) for r in self.node.runs]
        return out

    def prefix_text(self):
        return "".join(s.text for s in self.prefix)


def layout(root, rules):
    lay = _Layout(rules)
    lay.top(root)
    return lay.out


class _Layout:
    def __init__(self, rules):
        self.r = rules
        self.t = rules["tree"]
        self.out = []

    def conn(self, text):
        return Seg(text, "connector", bold=self.t["bold_connectors"])

    def top(self, root):
        n = 0
        for i, c in enumerate(root.children):
            if c.kind == "heading":
                if i > 0 and self.t["blank_between_top_level"]:
                    self.out.append(Line("blank"))
                n += 1
                self.heading(c, "", "", [n])
            else:
                self.leaf(c, "", False, 0)

    def heading(self, h, head_conn, inner, numbers):
        prefix = []
        if head_conn:
            prefix.append(self.conn(head_conn))
        prefix.append(Seg(self.r.label(numbers) + " ", "label",
                          bold=self.r["numbering"]["bold_label"]))
        self.out.append(Line("item", prefix, h))
        self.children(h, inner, len(head_conn), numbers)

    def children(self, h, inner, label_col, numbers):
        kids = h.children
        heads = [i for i, c in enumerate(kids) if c.kind == "heading"]
        last_head = heads[-1] if heads else -1
        n = 0
        marker_col = label_col + self.r["bullets"]["indent"]
        for i, c in enumerate(kids):
            if c.kind == "heading":
                n += 1
                is_last = i == last_head
                # blocks from a newer version aren't exported, so they don't count here
                prev = next((k for k in reversed(kids[:i]) if k.kind in BLOCK_KINDS), None)
                if self.t["spacer_lines"] and (
                        prev is None or prev.kind == "heading" or self.t["spacer_after_leaf"]):
                    self.out.append(Line("spacer", [self.conn(inner + self.t["trunk"])]))
                head_conn = inner + (self.t["last"] if is_last else self.t["branch"])
                child_inner = inner + (self.t["space"] if is_last else self.t["pipe"])
                self.heading(c, head_conn, child_inner, numbers + [n])
            else:
                trunk_str = inner + self.t["trunk"] if i < last_head else inner
                self.leaf(c, trunk_str, True, marker_col)

    def leaf(self, c, trunk_str, _owned, marker_col):
        base = trunk_str
        if len(base) < marker_col:
            base = base + " " * (marker_col - len(base))
        elif base and not base.endswith(" "):
            base += " "
        prefix = [self.conn(base)] if base else []
        if c.kind in ("table", "drawing"):
            self.out.append(Line(c.kind, prefix, c))
            return
        if c.kind not in BLOCK_KINDS:  # shown in the editor, left out of exports
            self.out.append(Line("unknown", prefix, c))
            return
        if c.kind == "bullet":
            prefix.append(Seg(self.r.marker_symbol(c.marker) + " ", "marker"))
        self.out.append(Line("item", prefix, c))
        for k in c.children:
            self.leaf(k, trunk_str, True, marker_col + self.r["bullets"]["nested_indent"])
