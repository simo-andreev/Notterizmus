"""Text size (R5): Ctrl+= / Ctrl+- / Ctrl+0 and Ctrl + scroll wheel, remembered."""
import json

from notterizmus.guide import b, h, table
from notterizmus.rules import config_dir

from . import support as ui

LONG = "A line long enough to wrap when the text gets larger, so rows change height. " * 3


class ZoomTest(ui.UITestCase):
    def setUp(self):
        super().setUp()
        self.win.set_zoom(100, save=True, announce=False)
        self.doc = ui.open_chapter([h("Size", b("short"), b(LONG), table([["a", "b"]]))])
        ui.pump(0.3)

    def tearDown(self):
        self.win.set_zoom(100, save=True, announce=False)
        ui.pump(0.3)

    def zoom(self, action, times=1):
        for _ in range(times):
            self.win.lookup_action(action).activate(None)
        ui.settle()  # the new size takes effect in the next frame, the rows' heights after it

    def font_size(self, widget):
        """The widget's font size as Pango has it (GTK turns CSS points into pixels)."""
        return widget.get_pango_context().get_font_description().get_size() / ui.Pango.SCALE

    def saved(self):
        return json.loads((config_dir() / "state.json").read_text()).get("zoom")

    def test_keys(self):
        parse = ui.Gtk.accelerator_parse
        self.assertEqual([parse(a) for a in self.app.get_accels_for_action("win.zoom-in")],
                         [parse(a) for a in ("<Control>equal", "<Control>plus", "<Control>KP_Add")])
        self.assertEqual([parse(a) for a in self.app.get_accels_for_action("win.zoom-out")],
                         [parse(a) for a in ("<Control>minus", "<Control>KP_Subtract")])
        self.assertEqual([parse(a) for a in self.app.get_accels_for_action("win.zoom-reset")],
                         [parse(a) for a in ("<Control>0", "<Control>KP_0")])

    def test_zooming_changes_the_chapter_text_only_and_is_remembered(self):
        view = ui.row(self.doc.root.children[0].children[0]).view
        cell = ui.row(self.doc.root.children[0].children[2]).views()[0]
        normal = self.font_size(view)
        sidebar_label = next(w for w in ui.walk(self.win.sidebar) if isinstance(w, ui.Gtk.Label) and w.get_text())
        sidebar_size = self.font_size(sidebar_label)
        self.zoom("zoom-in", 5)
        self.assertEqual(self.win._zoom, 150)
        self.assertAlmostEqual(self.font_size(view), normal * 1.5, places=1)
        self.assertAlmostEqual(self.font_size(cell), normal * 1.5, places=1, msg="table cells too")
        self.assertEqual(self.win.zoom_label.get_label(), "150%")
        self.assertEqual(self.saved(), 150)
        self.assertEqual(self.font_size(sidebar_label), sidebar_size, "the rest of the window keeps its size")
        self.zoom("zoom-reset")
        self.assertEqual(self.win._zoom, 100)
        self.assertAlmostEqual(self.font_size(view), normal, places=1)

    def test_rows_follow_the_text_size_both_ways(self):
        # Rows added while editing get one line's height as their minimum; give these the
        # same, so a minimum left over from another size would show.
        self.ed.size_new_views(list(self.ed.all_views()))
        ui.pump(0.2)
        long_view = ui.row(self.doc.root.children[0].children[1]).view
        before = long_view.get_height()
        self.zoom("zoom-in", 6)
        self.assertGreater(long_view.get_height(), before)
        self.zoom("zoom-out", 10)  # down to 60%
        self.assertEqual(self.win._zoom, 60)
        # One-line rows must shrink to one line of the smaller text. (measure() can't
        # tell: it includes the minimum height, which is exactly what could be stale.)
        one_line = [v for v in self.ed.all_views() if v is not long_view]
        for v in one_line:
            line = v.create_pango_layout("Ag").get_pixel_size()[1] + v.get_top_margin() + v.get_bottom_margin()
            self.assertLessEqual(v.get_height(), line + 2, f"{v.get_plain()!r} kept a taller minimum height")

    def test_limits(self):
        self.zoom("zoom-out", 20)
        self.assertEqual(self.win._zoom, 60)
        self.assertFalse(self.win.lookup_action("zoom-out").get_enabled())
        self.zoom("zoom-in", 30)
        self.assertEqual(self.win._zoom, 250)
        self.assertFalse(self.win.lookup_action("zoom-in").get_enabled())

    def test_ctrl_scroll_zooms_and_plain_scroll_scrolls(self):
        self.assertFalse(self.win.scroll_zoom(False, -1), "without Ctrl the editor scrolls as usual")
        self.assertTrue(self.win.scroll_zoom(True, -1))  # wheel up: larger
        self.assertEqual(self.win._zoom, 110)
        for _ in range(4):  # a touchpad sends small steps; they add up
            self.win.scroll_zoom(True, 0.5)
        self.assertEqual(self.win._zoom, 90)

    def test_the_menu_has_a_zoom_row(self):
        menu = next(w for w in ui.walk(self.win) if isinstance(w, ui.Gtk.MenuButton)
                    and w.get_icon_name() == "open-menu-symbolic").get_popover()
        self.assertTrue(self.win.zoom_label.get_parent().is_ancestor(menu))
        self.zoom("zoom-in")
        self.assertEqual(self.win.zoom_label.get_label(), "110%")
