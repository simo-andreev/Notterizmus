"""Keys that change the outline, driven through the real editor."""
from notterizmus.guide import b, h, key, table

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

    def test_backspace_at_the_start_joins_the_item_with_the_one_above(self):
        doc = ui.open_chapter([h("Intro", b("one"), b((key("two"), " more")))])
        intro = doc.root.children[0]
        r = ui.focus(intro.children[1], 0)
        self.assertTrue(ui.press(r.view, "BackSpace"))
        self.assertEqual([(run.text, run.bold) for run in intro.children[0].runs],
                         [("one", False), ("two", True), (" more", False)], "formatting comes along")
        self.assertEqual(len(intro.children), 1)
        self.assertEqual((self.ed.current, self.ed.cur_view.cursor_offset()), (intro.children[0], 3),
                         "the cursor stays where the two met")
        ui.press(self.ed.cur_view, "z", ctrl=True)
        self.assertEqual([n.text for n in self.win.doc.root.children[0].children], ["one", "two more"])

    def test_backspace_does_not_join_an_item_that_has_sub_items_or_sits_under_a_table(self):
        doc = ui.open_chapter([h("Intro", b("one"), b("two", b("kid")), table([["x"]]), b("after"))])
        intro = doc.root.children[0]
        self.assertTrue(ui.press(ui.focus(intro.children[1], 0).view, "BackSpace"))
        self.assertTrue(ui.press(ui.focus(intro.children[3], 0).view, "BackSpace"))
        self.assertEqual([n.text for n in intro.children], ["one", "two", "", "after"])
        self.assertEqual([n.text for n in intro.children[1].children], ["kid"])

    def test_backspace_in_the_middle_of_the_text_is_left_to_the_text(self):
        doc = ui.open_chapter([h("Intro", b("one"), b("two"))])
        intro = doc.root.children[0]
        self.assertFalse(ui.press(ui.focus(intro.children[1], 2).view, "BackSpace"))
        self.assertEqual(len(intro.children), 2)

    def test_delete_at_the_end_pulls_up_the_next_item(self):
        doc = ui.open_chapter([h("Intro", b("one"), b("two"), b("three", b("kid")))])
        intro = doc.root.children[0]
        r = ui.focus(intro.children[0], -1)
        self.assertTrue(ui.press(r.view, "Delete"))
        self.assertEqual([n.text for n in intro.children], ["onetwo", "three"])
        self.assertEqual(self.ed.cur_view.cursor_offset(), 3)
        self.assertTrue(ui.press(ui.focus(intro.children[0], -1).view, "Delete"))
        self.assertEqual([n.text for n in intro.children], ["onetwo", "three"], "not an item with sub-items")

    def test_the_only_item_cannot_be_deleted_with_backspace(self):
        doc = ui.open_chapter([h("")])
        self.assertTrue(ui.press(ui.focus(doc.root.children[0], 0).view, "BackSpace"))
        self.assertEqual([n.kind for n in self.win.doc.root.children], ["heading"])

    def test_alt_arrows_move_the_item_among_its_siblings(self):
        doc = ui.open_chapter([h("Intro", b("a"), b("b"), b("c"))])
        intro = doc.root.children[0]
        item = intro.children[0]
        r = ui.focus(item, 1)
        self.assertTrue(ui.press(r.view, "Down", alt=True))
        self.assertEqual([n.text for n in intro.children], ["b", "a", "c"])
        self.assertEqual((self.ed.current, self.ed.cur_view.cursor_offset()), (item, 1), "the cursor moves with it")
        ui.press(ui.row(item).view, "Down", alt=True)
        ui.press(ui.row(item).view, "Down", alt=True)  # already last
        self.assertEqual([n.text for n in intro.children], ["b", "c", "a"])
        ui.press(ui.row(item).view, "Up", alt=True)
        self.assertEqual([n.text for n in intro.children], ["b", "a", "c"])

    def test_ctrl_shift_space_goes_round_the_item_types(self):
        doc = ui.open_chapter([h("Intro", b("x", b("nested")))])
        item = doc.root.children[0].children[0]
        seen = []
        ui.focus(item)
        for _ in range(4):
            self.assertTrue(ui.press(ui.row(item).view, "space", ctrl=True, shift=True))
            seen.append((item.kind, item.marker) if item.kind == "bullet" else item.kind)
        self.assertEqual(seen, [("bullet", "plus"), ("bullet", "minus"), "heading", ("bullet", "dot")])
        nested = item.children[0]
        seen = []
        ui.focus(nested)
        for _ in range(3):
            ui.press(ui.row(nested).view, "space", ctrl=True, shift=True)
            seen.append(nested.marker if nested.kind == "bullet" else nested.kind)
        self.assertEqual(seen, ["plus", "minus", "dot"], "under a bullet, numbered is skipped")

    def test_typing_the_number_trigger_under_a_bullet_is_refused_with_a_message(self):
        doc = ui.open_chapter([h("Intro", b("outer", b("inner")))])
        inner = doc.root.children[0].children[0].children[0]
        said = []
        self.win.toast = lambda msg, *a: said.append(msg)
        try:
            ui.type_text(ui.focus(inner, 0).view, "# ", wait=0.3)
        finally:
            del self.win.toast
        self.assertEqual((inner.kind, inner.text), ("bullet", "inner"), "the trigger is removed, the type stays")
        self.assertEqual(said, ["A numbered item can't sit under a bullet."])

    def test_enter_at_the_start_of_an_item_adds_an_empty_one_above(self):
        doc = ui.open_chapter([h("Intro", b("text"))])
        intro = doc.root.children[0]
        item = intro.children[0]
        ui.press(ui.focus(item, 0).view, "Return")
        self.assertEqual([n.text for n in intro.children], ["", "text"])
        self.assertEqual((self.ed.current, self.ed.cur_view.cursor_offset()), (item, 0), "the cursor stays with the text")

    def test_enter_at_the_end_of_an_item_with_sub_items_adds_the_first_sub_item(self):
        doc = ui.open_chapter([h("Notes", b("existing")), h("Parts", h("Part one"))])
        notes, parts = doc.root.children
        ui.press(ui.focus(notes).view, "Return")
        self.assertEqual([(n.kind, n.text) for n in notes.children], [("bullet", ""), ("bullet", "existing")])
        self.assertIs(self.ed.current, notes.children[0])
        ui.press(ui.focus(parts).view, "Return")
        self.assertEqual([(n.kind, n.text) for n in parts.children], [("heading", ""), ("heading", "Part one")])

    def test_shift_enter_does_nothing(self):
        doc = ui.open_chapter([h("Intro", b("text"))])
        intro = doc.root.children[0]
        self.assertTrue(ui.press(ui.focus(intro.children[0], 2).view, "Return", shift=True))
        self.assertEqual([n.text for n in intro.children], ["text"], "an item is one paragraph")

    def test_ctrl_b_and_ctrl_i_format_the_selection_or_what_is_typed_next(self):
        doc = ui.open_chapter([h("Intro", b("plain"))])
        item = doc.root.children[0].children[0]
        r = ui.focus(item)
        self.assertTrue(ui.press(r.view, "b", ctrl=True))
        ui.type_text(r.view, " bold")
        self.assertEqual([(run.text, run.bold) for run in item.runs], [("plain", False), (" bold", True)])
        r.view.select_range(0, 5)
        ui.press(r.view, "i", ctrl=True)
        self.assertEqual([(run.text, run.bold, run.italic) for run in item.runs],
                         [("plain", False, True), (" bold", True, False)])
        ui.press(r.view, "i", ctrl=True)
        self.assertFalse(any(run.italic for run in item.runs), "again takes it off")
        r.view.select_range(3, 8)  # partly bold: the whole selection becomes bold
        ui.press(r.view, "b", ctrl=True)
        self.assertEqual([(run.text, run.bold) for run in item.runs], [("pla", False), ("in bold", True)])

    def test_undo_takes_back_one_word_at_a_time(self):
        doc = ui.open_chapter([h("Intro", b(""))])
        r = ui.focus(doc.root.children[0].children[0], 0)
        for ch in "one two":
            ui.type_text(r.view, ch, wait=0)

        def text():
            return self.win.doc.root.children[0].children[0].text

        self.assertEqual(text(), "one two")
        ui.press(r.view, "z", ctrl=True)
        self.assertEqual(text(), "one ", "the space belongs to the word before it")
        ui.press(self.ed.cur_view, "z", ctrl=True)
        self.assertEqual(text(), "")
        ui.press(self.ed.cur_view, "y", ctrl=True)
        self.assertEqual(text(), "one ", "Ctrl+Y redoes")
        ui.press(self.ed.cur_view, "z", ctrl=True, shift=True)
        self.assertEqual(text(), "one two")

    def test_a_new_edit_ends_redo_and_the_ends_of_history_say_so(self):
        doc = ui.open_chapter([h("Intro", b("start"))])
        r = ui.focus(doc.root.children[0].children[0])
        said = []
        self.win.toast = lambda msg, *a: said.append(msg)
        try:
            ui.press(r.view, "z", ctrl=True)
            self.assertEqual(said, ["Nothing to undo"])
            ui.type_text(r.view, " one")
            ui.press(r.view, "z", ctrl=True)
            ui.type_text(r.view, " two")
            ui.press(r.view, "z", ctrl=True, shift=True)
            self.assertEqual(said, ["Nothing to undo", "Nothing to redo"])
        finally:
            del self.win.toast
        self.assertEqual(self.win.doc.root.children[0].children[0].text, "start two")

    def test_after_an_undo_the_editor_still_knows_where_the_cursor_is(self):
        # Undo keeps the row and the focus in it, so no focus event followed and the editor
        # forgot its text view: Ctrl+W then selected the whole item instead of the word.
        doc = ui.open_chapter([h("Intro", b("alpha beta"))])
        item = doc.root.children[0].children[0]
        r = ui.focus(item)
        ui.type_text(r.view, " gamma")
        ui.type_text(r.view, " delta")
        ui.press(r.view, "z", ctrl=True)
        self.assertEqual(self.win.doc.root.children[0].children[0].text, "alpha beta gamma")
        self.assertIs(self.ed.cur_view, r.view)
        ui.press(r.view, "w", ctrl=True)
        self.assertEqual((r.view.selection_offsets(), self.ed.sel), ((11, 16), []), "the word, not the item")

    def test_arrow_keys_cross_from_item_to_item(self):
        doc = ui.open_chapter([h("Intro", b("first"), b("second"))])
        intro = doc.root.children[0]
        first, second = intro.children
        self.assertTrue(ui.press(ui.focus(first, 2).view, "Down"))
        self.assertEqual((self.ed.current, self.ed.cur_view.cursor_offset()), (second, 0))
        self.assertTrue(ui.press(self.ed.cur_view, "Up"))
        self.assertEqual((self.ed.current, self.ed.cur_view.cursor_offset()), (first, 5), "upwards: to the end")
        ui.press(ui.focus(intro, 0).view, "Up")
        self.assertIs(self.ed.current, intro, "nothing above the first item")
        ui.press(ui.focus(second).view, "Down")
        self.assertIs(self.ed.current, second, "nor below the last")

    def test_the_item_menu_deletes_an_item_and_keeps_its_sub_items(self):
        doc = ui.open_chapter([h("Intro", h("Going", b("stays"), h("Stays too")), h("Next"))])
        intro = doc.root.children[0]
        self.ed.show_item_menu(ui.row(intro.children[0]))
        ui.pump(0.2)
        pop = ui.open_popovers()[0]
        row = next(r for _n, text, r in ui.menu_choices(pop) if text == "Delete Item")
        row.get_parent().emit("row-activated", row)
        ui.wait_for(lambda: len(intro.children) == 3, "the item to be deleted")
        self.assertEqual([(n.kind, n.text) for n in intro.children],
                         [("bullet", "stays"), ("heading", "Stays too"), ("heading", "Next")])

    def test_backspace_on_an_empty_top_level_item_numbers_the_bullets_it_leaves(self):
        # They used to stay bullets, at the top level, where every item is numbered.
        doc = ui.open_chapter([h("First"), h("", b("was a bullet", b("nested")), h("Sub")), h("Last")])
        root = doc.root
        self.assertTrue(ui.press(ui.focus(root.children[1], 0).view, "BackSpace"))
        self.assertEqual([(n.kind, n.text) for n in root.children],
                         [("heading", "First"), ("heading", "was a bullet"), ("heading", "Sub"), ("heading", "Last")])
        self.assertEqual([(n.kind, n.text) for n in root.children[1].children], [("bullet", "nested")])
        self.assertEqual([ui.row(n).prefix.get_text() for n in root.walk() if n is not root],
                         ["Ⅰ) ", "Ⅱ) ", "     • ", "Ⅲ) ", "Ⅳ) "])
        self.assertTrue(ui.row(root.children[1]).has_css_class("kind-heading"))
        self.assertIs(self.ed.current, root.children[0], "the cursor goes to the item above")
        ui.press(self.ed.cur_view, "z", ctrl=True)
        again = self.win.doc.root.children[1]
        self.assertEqual([(again.kind, again.text), [(n.kind, n.text) for n in again.children]],
                         [("heading", ""), [("bullet", "was a bullet"), ("heading", "Sub")]], "undo: bullets again")

    def test_deleting_a_top_level_item_from_its_menu_numbers_its_bullets_too(self):
        doc = ui.open_chapter([h("Going", b("one"), table([["x"]]), b("two")), h("Stays")])
        root = doc.root
        self.ed.delete_node(root.children[0])
        ui.wait_editor()
        self.assertEqual([(n.kind, n.text) for n in root.children],
                         [("heading", "one"), ("table", ""), ("heading", "two"), ("heading", "Stays")])
        self.assertEqual([ui.row(n).prefix.get_text() for n in root.children if n.kind == "heading"], ["Ⅰ) ", "Ⅱ) ", "Ⅲ) "])
