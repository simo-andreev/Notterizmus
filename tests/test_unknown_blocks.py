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

MINDMAP = {
    "kind": "mindmap", "id": "d1",
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
        d = chapter(heading("Intro", bullet("before"), copy.deepcopy(MINDMAP), bullet("after")))
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
            with_block = Document.from_json(chapter(*make(copy.deepcopy(MINDMAP)))).root
            without = Document.from_json(chapter(*_drop_none(make(None)))).root
            lines = layout(with_block, rules)
            self.assertIn("unknown", [ln.kind for ln in lines])
            self.assertEqual(to_plain(lines), to_plain(layout(without, rules)))
            html = to_html(lines)
            self.assertEqual(html, to_html(layout(without, rules)))
            self.assertNotIn("SECRET", html)

    def test_its_children_are_not_laid_out(self):
        root = Document.from_json(chapter(heading("Intro", copy.deepcopy(MINDMAP)))).root
        laid = [ln.node.kind for ln in layout(root, Rules()) if ln.node is not None]
        self.assertEqual(laid, ["heading", "mindmap"])

    def test_it_holds_no_text_of_its_own(self):
        node = Node.from_json(copy.deepcopy(MINDMAP))
        self.assertEqual(node.text, "")
        self.assertEqual(node.children[0].text, "SECRET child")


class UnknownFileFieldsTest(unittest.TestCase):
    """The same for the file as a whole: its own fields, its "chapter" entry, its format name."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def newer(self):
        d = chapter(heading("Intro", bullet("note")))
        d.update(format="notterizmus/2", lang="en_US", tags=["draft", "ch1"], created={"by": "2.0", "at": 1},
                 chapter={"number": 1, "title": "T", "subtitle": "kept", "part": 2})
        return d

    def write(self, d, name="01 T.notz", book="B"):
        path = self.dir / book / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d), encoding="utf-8")
        return path

    def read(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def test_fields_of_the_file_and_of_its_chapter_entry_are_saved_back(self):
        d = self.newer()
        path = self.write(d)
        Document.load(path).save()
        self.assertEqual(self.read(path), d)

    def test_they_survive_editing_what_this_version_does_know(self):
        d = self.newer()
        path = self.write(d)
        doc = Document.load(path)
        doc.chapter_title, doc.chapter_no, doc.book, doc.lang = "New title", 7, "Other", "bg_BG"
        doc.root.children[0].children[0].runs = []
        doc.save()
        got = self.read(path)
        self.assertEqual(got["chapter"], {"number": 7, "title": "New title", "subtitle": "kept", "part": 2})
        self.assertEqual((got["book"], got["lang"], got["tags"], got["created"]),
                         ("Other", "bg_BG", ["draft", "ch1"], {"by": "2.0", "at": 1}))
        self.assertEqual(got["format"], "notterizmus/2", "a newer file isn't relabelled as an older one")

    def test_a_field_cannot_shadow_one_this_version_writes(self):
        doc = Document.load(self.write(self.newer()))
        doc.extra["book"] = "from extra"
        doc.chapter_extra["title"] = "from extra"
        got = doc.to_json()
        self.assertEqual((got["book"], got["chapter"]["title"]), ("B", "T"))

    def test_a_file_without_a_format_name_gets_this_versions(self):
        path = self.write({"book": "B", "chapter": {"number": 1, "title": "T"}, "content": []})
        Document.load(path).save()
        self.assertEqual(self.read(path)["format"], "notterizmus/1")
        self.assertEqual(Document.new("B", 1, "T").to_json()["format"], "notterizmus/1")

    def test_renaming_renumbering_and_moving_a_chapter_keep_them(self):
        from notterizmus.library import rename_book, renumber, set_chapter
        d = self.newer()
        path = self.write(d)
        moved = set_chapter(path, 4, "Renamed")
        path = moved[path]
        moved = renumber({path: 9})
        path = moved[path]
        moved = set_chapter(path, 9, "Renamed", self.dir / "Second book")
        path = moved[path]
        rename_book(self.dir / "Second book", "Third book")
        got = self.read(self.dir / "Third book" / "09 Renamed.notz")
        self.assertEqual(got["chapter"], {"number": 9, "title": "Renamed", "subtitle": "kept", "part": 2})
        self.assertEqual((got["book"], got["format"], got["tags"], got["created"]),
                         ("Third book", "notterizmus/2", d["tags"], d["created"]))
        self.assertEqual(got["content"], d["content"])


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
