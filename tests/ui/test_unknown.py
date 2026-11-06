"""A block type from a newer version: shown read-only, skipped by the cursor, kept in the file."""
import json

from notterizmus.guide import b, h
from notterizmus.model import Node

from . import support as ui

DRAWING = {"kind": "drawing", "id": "d1", "runs": [{"t": "SECRET caption"}],
           "data": {"elements": [{"type": "rect"}]}, "zoom": 2}


def drawing():
    return Node.from_json(json.loads(json.dumps(DRAWING)))


def saved_block(path):
    content = json.loads(path.read_text(encoding="utf-8"))["content"]
    return next(c for c in content[0]["children"] if c["kind"] == "drawing")


class UnknownBlockTest(ui.UITestCase):
    def open(self):
        doc = ui.open_chapter([h("Intro", b("before"), drawing(), b("after"))])
        intro = doc.root.children[0]
        return doc, intro, intro.children[0], intro.children[1], intro.children[2]

    def test_it_is_shown_as_a_read_only_note(self):
        _doc, _intro, _before, block, _after = self.open()
        from notterizmus.ui.rows import UnknownRow  # needs GTK, so not at the top
        r = ui.row(block)
        self.assertIsInstance(r, UnknownRow)
        self.assertEqual(r.views(), [])
        self.assertIn("“drawing”", r.label.get_text())

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
        self.assertEqual([c.kind for c in intro.children], ["bullet", "drawing", "bullet"])
        self.assertEqual((before.text, after.text), ("before", "after"))

    def test_editing_around_it_keeps_its_data_in_the_file(self):
        doc, _intro, before, _block, _after = self.open()
        ui.type_text(ui.focus(before).view, " edited")
        ui.pump(1.2)  # autosave
        self.assertIn("before edited", doc.path.read_text(encoding="utf-8"))
        self.assertEqual(saved_block(doc.path), DRAWING)

    def test_copy_for_topcoding_leaves_it_out(self):
        self.open()
        self.win.lookup_action("copy").activate(None)
        ui.pump(0.2)
        self.assertNotIn("SECRET", ui.clipboard("text/html"))
        self.assertNotIn("drawing", ui.clipboard("text/plain"))

    def test_it_can_be_deleted_and_the_delete_undone(self):
        doc, intro, before, block, _after = self.open()
        ui.focus(before)
        trash = next(w for w in ui.walk(ui.row(block)) if isinstance(w, ui.Gtk.Button))
        trash.emit("clicked")
        ui.pump(0.3)
        self.assertEqual([c.kind for c in self.win.doc.root.children[0].children], ["bullet", "bullet"])
        ui.press(self.ed.cur_view or ui.row(before).view, "z", ctrl=True)
        kids = self.win.doc.root.children[0].children
        self.assertEqual([c.kind for c in kids], ["bullet", "drawing", "bullet"])
        self.assertEqual(kids[1].to_json(), DRAWING)
