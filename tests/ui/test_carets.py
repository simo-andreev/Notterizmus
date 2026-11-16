"""Multiple cursors: Ctrl tapped twice and held, then ↑/↓; typing goes to every cursor."""
from notterizmus.guide import b, h, table

from . import support as ui


class CaretsTest(ui.UITestCase):
    def chapter(self):
        doc = ui.open_chapter([h("Intro", b("one"), b("two"), table([["cell"]]), b("three"))])
        self.one, self.two, _table, self.three = doc.root.children[0].children
        return doc

    def texts(self):
        return [n.text for n in (self.one, self.two, self.three)]

    def test_double_ctrl_then_ctrl_down_adds_a_cursor_below(self):
        self.chapter()
        r = ui.focus(self.one, 1)
        self.assertFalse(ui.press(r.view, "Down", ctrl=True, wait=0), "a plain Ctrl+↓ adds nothing")
        self.assertEqual(self.ed.mc_views, [])
        ui.press(r.view, "Control_L", wait=0)
        ui.press(r.view, "Control_L", wait=0)  # the second tap, within the double-tap time
        self.assertTrue(ui.press(r.view, "Down", ctrl=True))
        self.assertEqual(self.ed.mc_views, [ui.row(self.two).view])
        self.assertEqual([it.get_offset() for it in ui.row(self.two).view.caret_iters()], [1])
        ui.press(r.view, "Down", ctrl=True)
        self.assertEqual(self.ed.mc_views, [ui.row(self.two).view, ui.row(self.three).view], "tables are stepped over")
        ui.key_controller(r.view).emit("key-released", ui.Gdk.keyval_from_name("Control_L"), 0, ui.Gdk.ModifierType(0))
        self.assertFalse(ui.press(r.view, "Down", ctrl=True, wait=0), "Ctrl let go: back to plain Ctrl+↓")

    def test_typing_and_backspace_work_at_every_cursor_and_undo_as_one_step(self):
        self.chapter()
        r = ui.focus(self.one, 0)
        self.ed.add_caret(r.view, 1)
        self.ed.add_caret(r.view, 1)
        for key in ("N", "o", "minus"):
            self.assertTrue(ui.press(r.view, key, wait=0))
        ui.pump(0.1)
        self.assertEqual(self.texts(), ["No-one", "No-two", "No-three"])
        ui.press(r.view, "BackSpace")
        self.assertEqual(self.texts(), ["Noone", "Notwo", "Nothree"])
        ui.press(r.view, "z", ctrl=True)
        doc = self.win.doc
        self.assertEqual([n.text for n in doc.root.children[0].children if n.kind == "bullet"], ["one", "two", "three"])
        self.assertEqual(self.ed.mc_views, [], "undo goes back to one cursor")

    def test_arrow_keys_move_every_cursor(self):
        self.chapter()
        r = ui.focus(self.one, 0)
        self.ed.add_caret(r.view, 1)
        two = ui.row(self.two).view
        ui.press(r.view, "Right")
        ui.press(r.view, "Right")
        self.assertEqual((r.view.cursor_offset(), [it.get_offset() for it in two.caret_iters()]), (2, [2]))
        ui.press(r.view, "End")
        ui.press(r.view, "x")
        self.assertEqual(self.texts()[:2], ["onex", "twox"])
        ui.press(r.view, "Home")
        ui.press(r.view, "Delete")
        self.assertEqual(self.texts()[:2], ["nex", "wox"])
        ui.press(r.view, "Left")
        self.assertEqual((r.view.cursor_offset(), [it.get_offset() for it in two.caret_iters()]), (0, [0]))

    def test_escape_and_other_keys_go_back_to_one_cursor(self):
        self.chapter()
        r = ui.focus(self.one, 0)
        self.ed.add_caret(r.view, 1)
        self.assertTrue(ui.press(r.view, "Escape"))
        self.assertEqual((self.ed.mc_views, ui.row(self.two).view.carets), ([], []))
        self.ed.add_caret(r.view, 1)
        ui.press(r.view, "Tab")  # a key the cursors don't share
        self.assertEqual(self.ed.mc_views, [])

    def test_a_cursor_can_be_added_above_and_not_past_the_ends(self):
        self.chapter()
        r = ui.focus(self.two, 2)
        self.ed.add_caret(r.view, -1)
        self.assertEqual(self.ed.mc_views, [ui.row(self.one).view])
        self.ed.add_caret(r.view, -1)
        intro_view = ui.row(self.win.doc.root.children[0]).view
        self.assertEqual(self.ed.mc_views, [ui.row(self.one).view, intro_view])
        self.ed.add_caret(r.view, -1)
        self.assertEqual(len(self.ed.mc_views), 2, "nothing above the first item")
        self.assertEqual([it.get_offset() for it in ui.row(self.one).view.caret_iters()], [2])

    def test_a_cursor_in_a_shorter_line_sits_at_its_end(self):
        doc = ui.open_chapter([h("Intro", b("a long line of text"), b("short"))])
        long, short = doc.root.children[0].children
        r = ui.focus(long, 15)
        self.ed.add_caret(r.view, 1)
        self.assertEqual([it.get_offset() for it in ui.row(short).view.caret_iters()], [5])
        ui.press(r.view, "exclam")
        self.assertEqual((long.text, short.text), ("a long line of !text", "short!"))
