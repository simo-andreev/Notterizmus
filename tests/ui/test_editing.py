"""Keys that change the outline, driven through the real editor."""
from notterizmus.guide import b, h

from . import support as ui


class EditingTest(ui.UITestCase):
    def test_enter_splits_the_item_at_the_cursor(self):
        doc = ui.open_chapter([h("Intro", b("first second"))])
        bullet = doc.root.children[0].children[0]
        r = ui.focus(bullet, len("first "))
        self.assertTrue(ui.press(r.view, "Return"))
        texts = [n.text for n in doc.root.children[0].children]
        self.assertEqual(texts, ["first ", "second"])

    def test_typing_a_trigger_changes_the_item_type(self):
        doc = ui.open_chapter([h("Intro", b("text"))])
        bullet = doc.root.children[0].children[0]
        r = ui.focus(bullet, 0)
        ui.type_text(r.view, "+ ", wait=0.3)
        self.assertEqual((bullet.kind, bullet.marker, bullet.text), ("bullet", "plus", "text"))

    def test_ctrl_enter_adds_the_next_numbered_item(self):
        doc = ui.open_chapter([h("Intro", h("One", b("note")))])
        one = doc.root.children[0].children[0]
        r = ui.focus(one.children[0])
        self.assertTrue(ui.press(r.view, "Return", ctrl=True))
        kids = doc.root.children[0].children
        self.assertEqual([k.kind for k in kids], ["heading", "heading"])
        self.assertIs(self.ed.current, kids[1], "the cursor moves to the new item")

    def test_enter_on_an_empty_bullet_leaves_the_list(self):
        doc = ui.open_chapter([h("Intro", h("One", b("note")))])
        one = doc.root.children[0].children[0]
        r = ui.focus(one.children[0])
        ui.press(r.view, "Return")
        self.assertEqual(len(one.children), 2)
        ui.press(ui.row(one.children[1]).view, "Return")
        self.assertEqual([k.kind for k in doc.root.children[0].children], ["heading", "heading"])
        self.assertEqual(len(one.children), 1, "the empty bullet became Ⅰ.2)")

    def test_tab_indents_and_undo_redo_restore_it(self):
        doc = ui.open_chapter([h("Intro", b("a"), b("b"))])
        intro = doc.root.children[0]
        second = intro.children[1]
        r = ui.focus(second)
        self.assertTrue(ui.press(r.view, "Tab"))
        self.assertIs(second.parent, intro.children[0])
        ui.press(ui.row(second).view, "z", ctrl=True)
        self.assertEqual([n.text for n in self.win.doc.root.children[0].children], ["a", "b"])
        ui.press(self.ed.cur_view, "z", ctrl=True, shift=True)
        self.assertEqual(len(self.win.doc.root.children[0].children), 1)
        ui.press(self.ed.cur_view, "Tab", shift=True)
        self.assertEqual(len(self.win.doc.root.children[0].children), 2, "Shift+Tab outdents it again")

    def test_backspace_on_an_empty_item_deletes_it(self):
        doc = ui.open_chapter([h("Intro", b("keep"), b(""))])
        intro = doc.root.children[0]
        r = ui.focus(intro.children[1], 0)
        self.assertTrue(ui.press(r.view, "BackSpace"))
        self.assertEqual([n.text for n in intro.children], ["keep"])
