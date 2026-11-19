"""A block type from a newer version: shown read-only, skipped by the cursor, kept in the file."""
import json
from pathlib import Path

from notterizmus.guide import b, h
from notterizmus.model import Node

from . import support as ui

MINDMAP = {"kind": "mindmap", "id": "d1", "runs": [{"t": "SECRET caption"}],
           "data": {"elements": [{"type": "rect"}]}, "zoom": 2}


def mindmap():
    return Node.from_json(json.loads(json.dumps(MINDMAP)))


def saved_block(path):
    content = json.loads(path.read_text(encoding="utf-8"))["content"]
    return next(c for c in content[0]["children"] if c["kind"] == "mindmap")


class UnknownBlockTest(ui.UITestCase):
    def open(self):
        doc = ui.open_chapter([h("Intro", b("before"), mindmap(), b("after"))])
        intro = doc.root.children[0]
        return doc, intro, intro.children[0], intro.children[1], intro.children[2]

    def test_it_is_shown_as_a_read_only_note(self):
        _doc, _intro, _before, block, _after = self.open()
        from notterizmus.ui.rows import UnknownRow  # needs GTK, so not at the top
        r = ui.row(block)
        self.assertIsInstance(r, UnknownRow)
        self.assertEqual(r.views(), [])
        self.assertIn("“mindmap”", r.label.get_text())

    def test_the_cursor_skips_it(self):
        _doc, _intro, before, _block, after = self.open()
        r = ui.focus(before)
        self.assertTrue(ui.press(r.view, "Down"))
        self.assertIs(self.ed.current, after)
        self.assertTrue(ui.press(ui.row(after).view, "Up"))
        self.assertIs(self.ed.current, before)

    def test_backspace_and_delete_do_not_join_into_it(self):
        _doc, intro, before, block, after = self.open()
        ui.press(ui.focus(after, 0).view, "BackSpace")
        ui.press(ui.focus(before, -1).view, "Delete")
        self.assertEqual([c.kind for c in intro.children], ["bullet", "mindmap", "bullet"])
        self.assertEqual((before.text, after.text), ("before", "after"))

    def test_keys_next_to_one_with_sub_items_leave_them_alone(self):
        """The cursor's order went into the block's sub-items, which the editor doesn't
        show: Backspace at the start of the next item joined its text into a hidden sub-item,
        which was saved, and then raised KeyError (CR12 in CODE_REVIEW.md)."""
        with_items = {"kind": "mindmap", "id": "d2", "data": {"x": 1},
                      "children": [{"kind": "bullet", "id": "c1", "runs": [{"t": "inside"}], "marker": "dot"}]}
        doc = ui.open_chapter([h("Intro", b("before"), Node.from_json(json.loads(json.dumps(with_items))),
                                 b("after"))])
        before, _block, after = doc.root.children[0].children
        self.assertTrue(ui.press(ui.focus(after, 0).view, "Up"))
        self.assertIs(self.ed.current, before)
        self.assertTrue(ui.press(ui.focus(before, -1).view, "Down"))
        self.assertIs(self.ed.current, after)
        ui.press(ui.focus(after, 0).view, "BackSpace")
        ui.press(ui.focus(before, -1).view, "Delete")
        self.assertEqual((before.text, after.text), ("before", "after"))
        self.win.save(quiet=True)
        self.assertEqual(saved_block(doc.path), with_items)

    def test_delete_block_removes_it_with_its_sub_items(self):
        """The item menu's Delete Block moved the sub-items of a block from a newer version
        up into the chapter; its trash button removed it whole (CR13)."""
        with_items = {"kind": "mindmap", "id": "d3", "children": [
            {"kind": "bullet", "id": "c3", "runs": [{"t": "inside"}], "marker": "dot"}]}
        doc = ui.open_chapter([h("Intro", b("before"), Node.from_json(json.loads(json.dumps(with_items))),
                                 b("after"))])
        self.ed.delete_node(doc.root.children[0].children[1])  # what Delete Block in its menu runs
        ui.wait_editor()
        self.assertEqual([c.text for c in self.win.doc.root.children[0].children], ["before", "after"])
        self.ed.undo()
        intro = self.win.doc.root.children[0]
        self.assertEqual([c.kind for c in intro.children], ["bullet", "mindmap", "bullet"])
        self.assertEqual(intro.children[1].children[0].text, "inside")

    def test_editing_around_it_keeps_its_data_in_the_file(self):
        doc, _intro, before, _block, _after = self.open()
        ui.type_text(ui.focus(before).view, " edited")
        ui.wait_for(lambda: "before edited" in doc.path.read_text(encoding="utf-8"), "the autosave")
        self.assertEqual(saved_block(doc.path), MINDMAP)

    def test_copy_for_topcoding_leaves_it_out(self):
        self.open()
        self.win.lookup_action("copy").activate(None)
        ui.pump(0.2)
        self.assertNotIn("SECRET", ui.clipboard("text/html"))
        self.assertNotIn("mindmap", ui.clipboard("text/plain"))

    def test_it_can_be_deleted_and_the_delete_undone(self):
        doc, intro, before, block, _after = self.open()
        ui.focus(before)
        trash = next(w for w in ui.walk(ui.row(block)) if isinstance(w, ui.Gtk.Button))
        trash.emit("clicked")
        ui.pump(0.3)
        self.assertEqual([c.kind for c in self.win.doc.root.children[0].children], ["bullet", "bullet"])
        ui.press(self.ed.cur_view or ui.row(before).view, "z", ctrl=True)
        kids = self.win.doc.root.children[0].children
        self.assertEqual([c.kind for c in kids], ["bullet", "mindmap", "bullet"])
        self.assertEqual(kids[1].to_json(), MINDMAP)


class UnknownFileFieldsTest(ui.UITestCase):
    """Fields of the file itself from a newer version, and its format name, stay in the
    file through editing, autosave and a rename."""

    NEWER = {"format": "notterizmus/2", "book": "Newer book", "tags": ["draft"], "created": {"by": "2.0"},
             "chapter": {"number": 1, "title": "From the future", "subtitle": "kept"},
             "content": [{"kind": "heading", "id": "h1", "runs": [{"t": "Intro"}]}]}

    def test_editing_and_renaming_keep_what_this_version_does_not_know(self):
        path = self.win.notes_root_path() / "Newer book" / "01 From the future.notz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.NEWER), encoding="utf-8")
        self.win.open_path(path)
        ui.settle()
        self.assertEqual(self.win.wtitle.get_title(), "Chapter 1 — From the future")
        ui.type_text(ui.focus(self.win.doc.root.children[0]).view, " edited")
        ui.wait_for(lambda: "Intro edited" in path.read_text(encoding="utf-8"), "the autosave")

        def unknown(p):
            d = json.loads(Path(p).read_text(encoding="utf-8"))
            return d["format"], d["tags"], d["created"], d["chapter"].get("subtitle")

        expected = ("notterizmus/2", ["draft"], {"by": "2.0"}, "kept")
        self.assertEqual(unknown(path), expected)
        self.win.apply_chapter_props(path, path.parent, 5, "Renamed")
        ui.pump(0.2)
        renamed = path.parent / "05 Renamed.notz"
        self.assertEqual(Path(self.win.doc.path), renamed)
        self.assertEqual(unknown(renamed), expected)
        ui.type_text(ui.row(self.win.doc.root.children[0]).view, " again")
        ui.wait_for(lambda: "edited again" in renamed.read_text(encoding="utf-8"), "the autosave after the rename")
        self.assertEqual(unknown(renamed), expected, "the open chapter kept them through the rename")
        self.assertEqual(json.loads(renamed.read_text(encoding="utf-8"))["chapter"],
                         {"subtitle": "kept", "number": 5, "title": "Renamed"})
