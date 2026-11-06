"""Files written by a newer version: unknown block types and fields survive a save and
stay out of the exports."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from notterizmus.export import to_html, to_plain
from notterizmus.layout import layout
from notterizmus.model import Document, Node
from notterizmus.rules import Rules

DRAWING = {
    "kind": "drawing", "id": "d1",
    "runs": [{"t": "SECRET caption", "b": True}],
    "marker": "plus",
    "data": {"elements": [{"type": "rect", "x": 1}], "rows": "not a table"},
    "zoom": 1.5,
    "children": [{"kind": "bullet", "id": "c1", "runs": [{"t": "SECRET child"}], "marker": "dot"}],
}


def chapter(*content):
    return {"format": "notterizmus/1", "book": "B", "chapter": {"number": 1, "title": "T"},
            "content": list(content)}


def heading(text, *children, **extra):
    return {"kind": "heading", "id": text, "runs": [{"t": text}], "children": list(children), **extra}


def bullet(text, **extra):
    return {"kind": "bullet", "id": text, "runs": [{"t": text}], "marker": "dot", **extra}


class UnknownBlocksTest(unittest.TestCase):
    def roundtrip(self, d):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.notz"
            path.write_text(json.dumps(d), encoding="utf-8")
            Document.load(path).save()
            return json.loads(path.read_text(encoding="utf-8"))

    def test_an_unknown_block_is_saved_back_unchanged(self):
        d = chapter(heading("Intro", bullet("before"), copy.deepcopy(DRAWING), bullet("after")))
        self.assertEqual(self.roundtrip(d)["content"], d["content"])

    def test_unknown_fields_on_known_items_are_kept(self):
        d = chapter(heading("Intro", bullet("x", folded=True), folded=False),
                    {"kind": "table", "id": "t", "data": {"header": True, "rows": [[[{"t": "a"}]]]},
                     "caption": "kept"})
        self.assertEqual(self.roundtrip(d)["content"], d["content"])

    def test_exports_are_as_if_the_block_were_not_there(self):
        rules = Rules()
        cases = [
            lambda dr: [heading("Intro", bullet("a"), dr, bullet("b"))],
            lambda dr: [heading("Intro", heading("One"), dr, heading("Two"))],
            lambda dr: [heading("Intro"), dr, heading("Next")],
            lambda dr: [heading("Intro", heading("One", bullet("a"), dr))],
        ]
        for make in cases:
            with_block = Document.from_json(chapter(*make(copy.deepcopy(DRAWING)))).root
            without = Document.from_json(chapter(*_drop_none(make(None)))).root
            lines = layout(with_block, rules)
            self.assertIn("unknown", [ln.kind for ln in lines])
            self.assertEqual(to_plain(lines), to_plain(layout(without, rules)))
            html = to_html(lines)
            self.assertEqual(html, to_html(layout(without, rules)))
            self.assertNotIn("SECRET", html)

    def test_its_children_are_not_laid_out(self):
        root = Document.from_json(chapter(heading("Intro", copy.deepcopy(DRAWING)))).root
        laid = [ln.node.kind for ln in layout(root, Rules()) if ln.node is not None]
        self.assertEqual(laid, ["heading", "drawing"])

    def test_it_holds_no_text_of_its_own(self):
        node = Node.from_json(copy.deepcopy(DRAWING))
        self.assertEqual(node.text, "")
        self.assertEqual(node.children[0].text, "SECRET child")


def _drop_none(items):
    out = []
    for it in items:
        if it is None:
            continue
        it = dict(it)
        if "children" in it:
            it["children"] = _drop_none(it["children"])
        out.append(it)
    return out


if __name__ == "__main__":
    unittest.main()
