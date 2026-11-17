"""Drawing blocks without GTK: the file format, the outline's lines, the exports and the
preview cache."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from notterizmus import drawing, lexical
from notterizmus.export import to_html, to_plain
from notterizmus.layout import layout
from notterizmus.model import Document, Node, can_contain
from notterizmus.rules import Rules

SCENE = {
    "elements": [
        {"type": "rectangle", "id": "r1", "x": 10, "y": 10, "width": 200, "height": 80},
        {"type": "text", "id": "t1", "x": 30, "y": 35, "text": 'a "quoted" <b> & Здравей'},
    ],
    "appState": {"viewBackgroundColor": "#ffffff"},
    "files": {},
}


def drawing_json(**extra):
    return {"kind": "drawing", "id": "d1", "data": copy.deepcopy(SCENE), **extra}


def chapter(*content):
    return {"format": "notterizmus/1", "book": "B", "chapter": {"number": 1, "title": "T"},
            "content": list(content)}


def heading(text, *children):
    return {"kind": "heading", "id": text, "runs": [{"t": text}], "children": list(children)}


def bullet(text):
    return {"kind": "bullet", "id": text, "runs": [{"t": text}], "marker": "dot"}


class DrawingFileTest(unittest.TestCase):
    def roundtrip(self, d):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.notz"
            path.write_text(json.dumps(d), encoding="utf-8")
            Document.load(path).save()
            return json.loads(path.read_text(encoding="utf-8"))

    def test_a_drawing_is_saved_back_as_it_was_read(self):
        d = chapter(heading("Intro", bullet("before"), drawing_json(), bullet("after")))
        self.assertEqual(self.roundtrip(d), d)

    def test_fields_from_a_newer_version_are_kept(self):
        block = drawing_json(caption="later")
        block["data"]["layers"] = [1, 2]
        d = chapter(heading("Intro", block))
        self.assertEqual(self.roundtrip(d), d)

    def test_a_scene_with_parts_of_the_wrong_type_still_opens(self):
        for data in (None, [], {"elements": "x", "appState": 3, "files": []}, {"elements": [1, {"type": "text"}]}):
            node = Node.from_json({"kind": "drawing", "id": "d", "data": data})
            self.assertIsInstance(node.data["elements"], list)
            self.assertTrue(all(isinstance(e, dict) for e in node.data["elements"]))
            self.assertEqual((node.data["appState"], node.data["files"]), ({}, {}))

    def test_nothing_can_be_put_under_a_drawing(self):
        self.assertFalse(can_contain(Node("drawing"), Node("bullet")))
        self.assertTrue(can_contain(Node("bullet"), Node("drawing")))

    def test_only_erased_elements_make_an_empty_drawing(self):
        self.assertTrue(drawing.is_empty(drawing.new_data()))
        self.assertTrue(drawing.is_empty({"elements": [{"type": "text", "isDeleted": True}]}))
        self.assertFalse(drawing.is_empty(SCENE))


class DrawingExportTest(unittest.TestCase):
    def lines(self, *content):
        return layout(Document.from_json(chapter(*content)).root, Rules())

    def test_it_is_a_line_of_its_own_under_its_item(self):
        lines = self.lines(heading("Intro", bullet("before"), drawing_json(), bullet("after")))
        self.assertEqual([ln.kind for ln in lines], ["item", "item", "drawing", "item"])

    def test_html_leaves_it_out_without_breaking_the_paragraph(self):
        with_it = to_html(self.lines(heading("Intro", bullet("before"), drawing_json(), bullet("after"))))
        without = to_html(self.lines(heading("Intro", bullet("before"), bullet("after"))))
        self.assertEqual(with_it, without)

    def test_plain_text_names_it_where_it_is(self):
        text = to_plain(self.lines(heading("Intro", bullet("before"), drawing_json(), bullet("after"))))
        rows = text.splitlines()
        self.assertEqual(len(rows), 4)
        self.assertTrue(rows[2].endswith("[Drawing]"), rows[2])
        self.assertEqual(len(rows[2]) - len("[Drawing]"), rows[1].index("•"))

    def test_an_empty_drawing_is_left_out_of_both(self):
        empty = {"kind": "drawing", "id": "d1", "data": {"elements": []}}
        lines = self.lines(heading("Intro", bullet("before"), empty, bullet("after")))
        self.assertEqual(len(to_plain(lines).splitlines()), 3)
        self.assertFalse(lexical.has_drawing(lines))
        self.assertIsNone(lexical.clipboard_data(lines))


class LexicalClipboardTest(unittest.TestCase):
    """What Copy for TopCoding offers beside the HTML when the chapter has a drawing: the
    nodes of TopCoding's editor, as the editor itself writes them."""

    def lines(self, *content):
        return layout(Document.from_json(chapter(*content)).root, Rules())

    def table(self, header=True):
        cell = lambda t: [{"t": t}]
        return {"kind": "table", "id": "tb", "data": {"header": header, "rows": [[cell("H1"), cell("H2")],
                                                                                 [cell("a"), []]]}}

    def test_text_only_chapters_keep_to_html(self):
        lines = self.lines(heading("Intro", bullet("before"), self.table()))
        self.assertIsNone(lexical.clipboard_data(lines))

    def test_the_drawing_is_an_excalidraw_node_between_the_paragraphs_around_it(self):
        nodes = lexical.to_nodes(self.lines(heading("Intro", bullet("before"), drawing_json(), bullet("after"))))
        self.assertEqual([n["type"] for n in nodes], ["paragraph", "excalidraw", "paragraph"])
        self.assertEqual(nodes[1], {"type": "excalidraw", "version": 1, "data": nodes[1]["data"]})
        self.assertEqual(json.loads(nodes[1]["data"]), SCENE)

    def test_lines_of_a_paragraph_are_joined_by_line_breaks(self):
        nodes = lexical.to_nodes(self.lines(heading("Intro", bullet("one"), bullet("two"))))
        self.assertEqual(len(nodes), 1)
        kinds = [c["type"] for c in nodes[0]["children"]]
        self.assertEqual(kinds, ["text", "linebreak", "text", "linebreak", "text"])
        texts = [c["text"] for c in nodes[0]["children"] if c["type"] == "text"]
        self.assertEqual("\n".join(texts) + "\n", to_plain(self.lines(heading("Intro", bullet("one"), bullet("two")))))

    def test_bold_italic_and_code_connectors_are_text_formats(self):
        item = {"kind": "bullet", "id": "b", "marker": "dot",
                "runs": [{"t": "plain "}, {"t": "bold", "b": True}, {"t": "both", "b": True, "i": True}]}
        lines = self.lines(heading("Intro", item, heading("Sub")))
        formats = {c["text"]: c["format"] for n in lexical.to_nodes(lines, code_prefix=True)
                   for c in n["children"] if c["type"] == "text"}
        self.assertEqual(formats["bold"], lexical.BOLD)
        self.assertEqual(formats["both"], lexical.BOLD | lexical.ITALIC)
        self.assertIn(lexical.CODE, formats.values())
        plain = {c["format"] for n in lexical.to_nodes(lines) for c in n["children"] if c["type"] == "text"}
        self.assertNotIn(lexical.CODE, plain)

    def test_a_table_keeps_its_header_row_and_empty_cells(self):
        nodes = lexical.to_nodes(self.lines(heading("Intro", self.table(), drawing_json())))
        table = next(n for n in nodes if n["type"] == "table")
        states = [[c["headerState"] for c in row["children"]] for row in table["children"]]
        self.assertEqual(states, [[lexical.HEADER_ROW] * 2, [0, 0]])
        last = table["children"][1]["children"][1]
        self.assertEqual([p["type"] for p in last["children"]], ["paragraph"])
        self.assertEqual(last["children"][0]["children"], [])

    def test_a_block_from_a_newer_version_is_left_out(self):
        newer = {"kind": "mindmap", "id": "m", "data": {"x": 1}}
        nodes = lexical.to_nodes(self.lines(heading("Intro", bullet("a"), newer, bullet("b"), drawing_json())))
        self.assertEqual([n["type"] for n in nodes], ["paragraph", "excalidraw"])

    def test_the_clipboard_data_is_chromes_custom_format_holding_the_editors_json(self):
        lines = self.lines(heading("Intro", bullet("Здравей 😀"), drawing_json()))
        offered = dict(lexical.clipboard_data(lines))
        self.assertEqual(list(offered), ["chromium/x-web-custom-data", "application/x-moz-custom-clipdata"])
        items = lexical.read_web_custom_data(offered["chromium/x-web-custom-data"])
        self.assertEqual(lexical.read_moz_custom_data(offered["application/x-moz-custom-clipdata"]), items)
        self.assertEqual(list(items), ["application/x-lexical-editor"])
        payload = json.loads(items["application/x-lexical-editor"])
        self.assertEqual(payload["namespace"], "SummaryEditor")
        self.assertEqual(payload["nodes"], lexical.to_nodes(lines))
        self.assertIn("Здравей 😀", payload["nodes"][0]["children"][-1]["text"])

    def test_the_custom_format_is_packed_as_chrome_reads_it(self):
        # one item, "a/b" -> "xyz": sizes are little-endian, text is UTF-16 padded to 4 bytes
        self.assertEqual(lexical.web_custom_data({"a/b": "xyz"}).hex(),
                         "1c000000" "01000000" "03000000" "61002f006200" "0000" "03000000" "780079007a00" "0000")

    def test_the_custom_format_is_packed_as_firefox_reads_it(self):
        # one item, "a/b" -> "xyz": kind and byte lengths are big-endian, text is UTF-16LE unpadded, 0 ends it
        self.assertEqual(lexical.moz_custom_data({"a/b": "xyz"}).hex(),
                         "00000001" "00000006" "61002f006200" "00000006" "780079007a00" "00000000")


class PreviewCacheTest(unittest.TestCase):
    def test_the_key_follows_the_scene_and_nothing_else(self):
        key = drawing.preview_key(SCENE)
        reordered = {"files": {}, "appState": dict(SCENE["appState"]), "elements": copy.deepcopy(SCENE["elements"]),
                     "layers": "from a newer version"}
        self.assertEqual(drawing.preview_key(reordered), key)
        moved = copy.deepcopy(SCENE)
        moved["elements"][0]["x"] = 11
        self.assertNotEqual(drawing.preview_key(moved), key)

    def test_a_stored_preview_is_found_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"XDG_CACHE_HOME": tmp}
            path = drawing.store_preview(SCENE, b"png bytes", env)
            self.assertEqual(path, drawing.preview_path(SCENE, env))
            self.assertEqual(path.read_bytes(), b"png bytes")
            self.assertEqual([p.name for p in path.parent.iterdir()], [path.name], "no temporary file is left")

    def test_the_oldest_previews_are_dropped_past_the_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"XDG_CACHE_HOME": tmp}
            folder = drawing.cache_dir(env)
            folder.mkdir(parents=True)
            for i in range(drawing.CACHE_KEEP + 5):
                p = folder / f"old{i:04d}.png"
                p.write_bytes(b"x")
                os.utime(p, (1000 + i, 1000 + i))
            new = drawing.store_preview(SCENE, b"new", env)
            names = {p.name for p in folder.iterdir()}
            self.assertEqual(len(names), drawing.CACHE_KEEP)
            self.assertIn(new.name, names)
            self.assertNotIn("old0000.png", names)
            self.assertIn(f"old{drawing.CACHE_KEEP + 4:04d}.png", names)

    def test_a_cache_that_cannot_be_written_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "file"
            blocker.write_text("not a folder")
            self.assertIsNone(drawing.store_preview(SCENE, b"x", {"XDG_CACHE_HOME": str(blocker)}))


class BundleTest(unittest.TestCase):
    """The Excalidraw page shipped with the app (built by scripts/build-drawing-editor.sh)."""

    WEB = Path(drawing.__file__).resolve().parent / "drawing_web"

    def test_the_page_and_everything_it_names_are_there(self):
        page = (self.WEB / "index.html").read_text(encoding="utf-8")
        for name in ("main.js", "main.css", "env.js"):
            self.assertIn(name, page)
            self.assertTrue((self.WEB / name).is_file(), name)
        self.assertTrue(any((self.WEB / "fonts" / "Excalifont").iterdir()))

    def test_the_page_may_not_reach_the_network(self):
        page = (self.WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy", page)
        self.assertIn("default-src 'self' data: blob:", page)
        self.assertNotIn("http", page.split("Content-Security-Policy", 1)[1].split(">", 1)[0])


if __name__ == "__main__":
    unittest.main()
