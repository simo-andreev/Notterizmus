"""Popup menus: Alt+Insert, the item menu and Ctrl+Space, picked with their number keys."""
from notterizmus.guide import b, h

from . import support as ui


class MenusTest(ui.UITestCase):
    def pick(self, pop, label_start):
        choices = ui.menu_choices(pop)
        num = next((n for n, text, _row in choices if text.startswith(label_start)), None)
        self.assertTrue(num, f"no numbered choice starting with {label_start!r} in {[c[:2] for c in choices]}")
        self.assertTrue(ui.press(pop, num))
        ui.wait_for(lambda: not ui.open_popovers(), "the menu to close after a pick")
        ui.wait_editor()

    def test_alt_insert_adds_a_sub_item_by_its_number(self):
        doc = ui.open_chapter([h("Intro")])
        intro = doc.root.children[0]
        r = ui.focus(intro)
        self.assertTrue(ui.press(r.view, "Insert", alt=True))
        pops = ui.open_popovers()
        self.assertEqual(len(pops), 1)
        numbers = [n for n, _t, _r in ui.menu_choices(pops[0])]
        self.assertEqual(numbers[:3], ["1", "2", "3"], "choices are numbered from 1")
        self.pick(pops[0], "Sub-item")
        self.assertEqual([c.kind for c in intro.children], ["heading"])
        self.assertFalse(ui.open_popovers(), "the menu closes after a pick")

    def test_item_menu_changes_the_type_by_its_number(self):
        doc = ui.open_chapter([h("Intro", b("keep"), b("pro or con"))])
        item = doc.root.children[0].children[1]
        self.ed.show_item_menu(ui.row(item))
        ui.wait_for(ui.open_popovers, "the item menu")
        choices = ui.menu_choices(ui.open_popovers()[0])
        self.assertEqual([n for n, _t, _r in choices][:10], list("1234567890"))
        self.assertEqual(choices[10][0], "", "only the first ten choices get a number")
        self.pick(ui.open_popovers()[0], "-   Con")
        self.assertEqual((item.kind, item.marker), ("bullet", "minus"))

    def test_ctrl_space_completes_from_the_chapter(self):
        doc = ui.open_chapter([h("Intro", b("completion matters"), b(""))])
        target = doc.root.children[0].children[1]
        r = ui.focus(target, 0)
        ui.type_text(r.view, "compl")
        self.assertTrue(ui.press(r.view, "space", ctrl=True))
        pop = self.ed._assist_pop
        self.assertIsNotNone(pop)
        first = ui.menu_choices(pop)[0]
        self.assertEqual(first[:2], ("1", "completion"))
        ui.press(pop, "1")
        ui.wait_for(lambda: target.text == "completion", "the first completion to be picked")

    def test_ctrl_space_narrows_as_you_type_and_escape_closes(self):
        doc = ui.open_chapter([h("Intro", b("complete completion compliance"), b(""))])
        target = doc.root.children[0].children[1]
        r = ui.focus(target, 0)
        ui.type_text(r.view, "comp")
        ui.press(r.view, "space", ctrl=True)
        pop = self.ed._assist_pop
        before = [t for _n, t, _r in ui.menu_choices(pop)]
        self.assertTrue({"complete", "completion", "compliance"} <= set(before), before)
        ui.press(pop, "l")
        ui.press(pop, "e")
        after = [t for _n, t, _r in ui.menu_choices(self.ed._assist_pop)]
        self.assertTrue(after and all(t.startswith("comple") for t in after), after)
        self.assertEqual(target.text, "comple", "typing goes into the text")
        ui.press(self.ed._assist_pop, "Escape")
        self.assertFalse(ui.open_popovers())
