"""Selecting whole items with the keyboard (Ctrl+A, Ctrl+W, Shift+arrows) and acting on them."""
from notterizmus.guide import b, h, table

from . import support as ui


class SelectionTest(ui.UITestCase):
    def chapter(self):
        doc = ui.open_chapter([h("Intro", b("alpha beta"), b("gamma"), b("delta")), h("Other", b("omega"))])
        self.intro, self.other = doc.root.children
        self.a, self.g, self.d = self.intro.children
        return doc

    def selected(self):
        return [n.text for n in self.ed.sel]

    def marked(self):
        """Texts of the rows drawn as selected."""
        return [n.text for n in self.win.doc.root.walk() if n.id in self.ed.rows
                and ui.row(n).has_css_class("node-selected")]

    def test_ctrl_a_selects_every_item(self):
        self.chapter()
        r = ui.focus(self.g)
        self.assertTrue(ui.press(r.view, "a", ctrl=True))
        self.assertEqual(self.selected(), ["Intro", "Other"], "the top-level items stand for everything under them")
        self.assertEqual(self.marked(), ["Intro", "alpha beta", "gamma", "delta", "Other", "omega"])
        ui.press(r.view, "Escape")
        self.assertEqual((self.selected(), self.marked()), ([], []))

    def test_ctrl_w_selects_a_little_more_each_time_and_ctrl_shift_w_goes_back(self):
        self.chapter()
        r = ui.focus(self.a, 2)
        steps = []
        for _ in range(5):
            ui.press(r.view, "w", ctrl=True)
            steps.append((r.view.selection_offsets(), self.selected()))
        self.assertEqual(steps, [((0, 5), []),                      # the word
                                 ((0, 10), []),                     # the item's text
                                 (None, ["alpha beta"]),            # the item
                                 (None, ["Intro"]),                 # its section
                                 (None, ["Intro", "Other"])])       # everything
        ui.press(r.view, "w", ctrl=True)
        self.assertEqual(self.selected(), ["Intro", "Other"], "nothing larger to select")
        back = []
        for _ in range(5):
            ui.press(r.view, "w", ctrl=True, shift=True)
            back.append((r.view.selection_offsets(), self.selected()))
        self.assertEqual(back, [(None, ["Intro"]), (None, ["alpha beta"]), ((0, 10), []), ((0, 5), []), (None, [])])
        self.assertEqual(r.view.cursor_offset(), 2, "the cursor is back where it was")

    def test_ctrl_w_on_a_one_word_item_goes_straight_to_its_text(self):
        self.chapter()
        r = ui.focus(self.g, 1)
        ui.press(r.view, "w", ctrl=True)
        self.assertEqual(r.view.selection_offsets(), (0, 5))
        ui.press(r.view, "w", ctrl=True)
        self.assertEqual(self.selected(), ["gamma"])

    def test_shift_arrows_extend_the_selection_item_by_item(self):
        self.chapter()
        r = ui.focus(self.a)
        self.assertTrue(ui.press(r.view, "Down", shift=True))
        self.assertEqual(self.selected(), ["alpha beta", "gamma"])
        ui.press(r.view, "Down", shift=True)
        self.assertEqual(self.selected(), ["alpha beta", "gamma", "delta"])
        ui.press(r.view, "Up", shift=True)
        self.assertEqual(self.selected(), ["alpha beta", "gamma"])
        ui.press(r.view, "Up", shift=True)
        ui.press(r.view, "Up", shift=True)
        self.assertEqual(self.selected(), ["Intro"], "going above the start selects upwards; a parent stands for its items")
        self.assertEqual(self.marked(), ["Intro", "alpha beta", "gamma", "delta"])

    def test_delete_removes_the_selected_items_and_undo_restores_them(self):
        self.chapter()
        r = ui.focus(self.a)
        ui.press(r.view, "Down", shift=True)
        self.assertTrue(ui.press(r.view, "Delete"))
        self.assertEqual([n.text for n in self.intro.children], ["delta"])
        self.assertEqual(self.selected(), [])
        self.assertIs(self.ed.current, self.intro, "the cursor moves to the item above")
        ui.press(self.ed.cur_view, "z", ctrl=True)
        self.assertEqual([n.text for n in self.win.doc.root.children[0].children], ["alpha beta", "gamma", "delta"])

    def test_deleting_everything_leaves_one_empty_item(self):
        self.chapter()
        r = ui.focus(self.g)
        ui.press(r.view, "a", ctrl=True)
        ui.press(r.view, "BackSpace")
        root = self.win.doc.root
        self.assertEqual([(n.kind, n.text) for n in root.walk() if n is not root], [("heading", "")])
        self.assertIs(self.ed.current, root.children[0])

    def test_tab_and_shift_tab_move_the_selected_items_together(self):
        self.chapter()
        r = ui.focus(self.g)
        ui.press(r.view, "Down", shift=True)
        self.assertTrue(ui.press(r.view, "Tab"))
        self.assertEqual([n.text for n in self.a.children], ["gamma", "delta"])
        self.assertEqual(self.selected(), ["gamma", "delta"], "still selected, so Tab can repeat")
        ui.press(ui.row(self.g).view, "Tab", shift=True)
        self.assertEqual([n.text for n in self.intro.children], ["alpha beta", "gamma", "delta"])
        self.assertEqual(self.a.children, [])

    def test_ctrl_b_makes_the_selected_items_bold_and_then_plain_again(self):
        doc = ui.open_chapter([h("Intro", b("one"), table([["cell", ""]]), b("two"))])
        intro = doc.root.children[0]
        r = ui.focus(intro.children[0])
        ui.press(r.view, "Down", shift=True)
        ui.press(r.view, "Down", shift=True)
        self.assertEqual(len(self.ed.sel), 3)
        self.assertTrue(ui.press(r.view, "b", ctrl=True))
        self.assertEqual([[run.bold for run in n.runs] for n in (intro.children[0], intro.children[2])], [[True], [True]])
        self.assertTrue(intro.children[1].data["rows"][0][0][0].bold, "table cells too")
        self.assertTrue(ui.row(intro.children[0]).view.get_runs()[0].bold, "and it shows in the text")
        ui.press(r.view, "b", ctrl=True)
        self.assertFalse(any(run.bold for n in (intro.children[0], intro.children[2]) for run in n.runs))
        ui.press(r.view, "z", ctrl=True)
        self.assertTrue(self.win.doc.root.children[0].children[0].runs[0].bold, "each step can be undone")

    def test_typing_drops_the_selection_and_goes_into_the_text(self):
        self.chapter()
        r = ui.focus(self.g)
        ui.press(r.view, "Down", shift=True)
        self.assertFalse(ui.press(r.view, "x"), "an ordinary key isn't taken by the selection")
        self.assertEqual(self.selected(), [])
        self.assertEqual([n.text for n in self.intro.children], ["alpha beta", "gamma", "delta"])

    def test_a_selection_survives_only_while_its_items_exist(self):
        self.chapter()
        r = ui.focus(self.g)
        ui.press(r.view, "Down", shift=True)
        self.ed.delete_node(self.d)
        ui.wait_editor()
        self.assertEqual(self.selected(), ["gamma"])


class ItemClipboardTest(ui.UITestCase):
    def test_copying_selected_items_and_pasting_them_elsewhere(self):
        doc = ui.open_chapter([h("From", b("one", b("under one")), b("two")), h("To", b("here"))])
        src, dst = doc.root.children
        r = ui.focus(src.children[0])
        ui.press(r.view, "Down", shift=True)
        ui.press(r.view, "Down", shift=True)
        self.assertEqual(len(self.ed.sel), 2)
        self.assertTrue(ui.press(r.view, "c", ctrl=True))
        self.assertEqual(ui.clipboard("text/plain"), "     • one\n         • under one\n     • two\n")
        self.assertIn("under one", ui.clipboard("application/x-notterizmus-nodes+json"))
        target = ui.focus(dst.children[0])
        target.view.emit("paste-clipboard")
        ui.wait_for(lambda: len(dst.children) == 3, "the copied items to be pasted")
        self.assertEqual([(n.text, [c.text for c in n.children]) for n in dst.children],
                         [("here", []), ("one", ["under one"]), ("two", [])])
        ids = [n.id for n in doc.root.walk()]
        self.assertEqual(len(ids), len(set(ids)), "pasted copies get ids of their own")
        self.assertEqual([n.text for n in src.children], ["one", "two"], "copying leaves the originals")

    def test_cutting_items_removes_them_and_paste_puts_them_back(self):
        doc = ui.open_chapter([h("Intro", b("keep"), b("cut me"), b("and me"))])
        intro = doc.root.children[0]
        r = ui.focus(intro.children[1])
        ui.press(r.view, "Down", shift=True)
        self.assertTrue(ui.press(r.view, "x", ctrl=True))
        self.assertEqual([n.text for n in intro.children], ["keep"])
        ui.wait_editor()
        ui.row(intro.children[0]).view.emit("paste-clipboard")
        ui.wait_for(lambda: len(intro.children) == 3, "the cut items to be pasted")
        self.assertEqual([n.text for n in intro.children], ["keep", "cut me", "and me"])
