"""Real mouse drags (Broadway): selecting items by dragging across them, as with a mouse."""
from notterizmus.guide import b, h

from . import support as ui


class DragSelectTest(ui.UITestCase):
    def setUp(self):
        super().setUp()
        if not ui.REAL_INPUT:
            self.skipTest("real mouse input needs the Broadway display (the default runner)")
        self.win.findbar.set_search_mode(False)
        self.win.set_zoom(100, save=True, announce=False)
        ui.pump(0.6)  # past the double-click time of the previous test's clicks

    def tearDown(self):
        ui.release_mouse()

    def chapter(self):
        doc = ui.open_chapter([h("Intro", b("one two three"), b("four five six"),
                                 b("seven eight nine"), b("ten eleven"))])
        ui.pump(0.2)
        return doc.root.children[0].children

    def at(self, node, x=40):
        view = ui.row(node).view
        return (view, x, view.get_height() / 2)

    def selected(self):
        return {n.id for n in self.ed.sel}

    def test_dragging_down_across_items_selects_them(self):
        items = self.chapter()
        ui.real_drag(self.at(items[0]), self.at(items[2]))
        self.assertEqual(self.selected(), {n.id for n in items[:3]})
        for n in items[:3]:
            self.assertTrue(ui.row(n).has_css_class("node-selected"))
        self.assertFalse(ui.row(items[3]).has_css_class("node-selected"))
        self.assertFalse(ui.row(items[0]).view.has_selection(), "no text selection on top of the items")

    def test_dragging_up_selects_the_items_above(self):
        items = self.chapter()
        ui.real_drag(self.at(items[3]), self.at(items[1]))
        self.assertEqual(self.selected(), {n.id for n in items[1:]})

    def test_dragging_within_one_item_selects_text(self):
        items = self.chapter()
        ui.real_drag(self.at(items[1], 4), self.at(items[1], 70))
        self.assertEqual(self.ed.sel, [])
        self.assertTrue(ui.row(items[1]).view.has_selection())

    def test_dragging_back_into_the_first_item_selects_text_again(self):
        items = self.chapter()
        view = ui.row(items[0]).view
        ui.real_drag(self.at(items[0], 4), self.at(items[2]), self.at(items[0], 70))
        self.assertEqual(self.ed.sel, [])
        start, end = view.selection_offsets() or (0, 0)
        self.assertEqual(start, 0)
        self.assertGreater(end, 3, "the text from where the drag began to the pointer is selected")

    def test_dragged_items_can_be_deleted_and_restored(self):
        items = self.chapter()
        intro = self.win.doc.root.children[0]
        ui.real_drag(self.at(items[1]), self.at(items[2]))
        ui.real_key("Delete")
        self.assertEqual([n.runs[0].text for n in intro.children], ["one two three", "ten eleven"])
        ui.real_key("z", ctrl=True)
        self.assertEqual(len(self.win.doc.root.children[0].children), 4)

    def test_dragging_onto_a_section_heading_deletes_only_the_heading(self):
        doc = ui.open_chapter([h("Intro", b("one two three"), h("Sub", b("four five six"), b("seven eight")))])
        ui.pump(0.2)
        intro = doc.root.children[0]
        first, sub = intro.children
        ui.real_drag(self.at(first), self.at(sub))
        self.assertEqual(self.selected(), {first.id, sub.id})
        self.assertFalse(any(ui.row(n).has_css_class("node-selected") for n in sub.children),
                         "the items under the heading weren't dragged over")
        ui.real_key("Delete")
        self.assertEqual([n.runs[0].text for n in self.win.doc.root.children[0].children],
                         ["four five six", "seven eight"])

    def test_dragging_past_the_bottom_scrolls_and_keeps_selecting(self):
        doc = ui.open_chapter([h("Long list", *[b(f"note {i}") for i in range(80)])])
        ui.pump(0.2)
        items = doc.root.children[0].children
        adj = self.ed.get_vadjustment()
        adj.set_value(0)
        ui.pump(0.2)
        bottom = ui.surface_point(self.ed, 40, self.ed.get_height() + 30)
        ui.real_drag(self.at(items[0]), bottom, hold=True)
        ui.pump_until(lambda: adj.get_value() > 0 and len(self.ed.sel) > 20)
        self.assertGreater(adj.get_value(), 0, "the outline scrolls while the pointer is below it")
        self.assertGreater(len(self.ed.sel), 20, "the items scrolled into view get selected")
        ui.release_mouse()
        stopped = adj.get_value()
        ui.pump(0.3)
        self.assertEqual(adj.get_value(), stopped, "scrolling stops when the button is released")
