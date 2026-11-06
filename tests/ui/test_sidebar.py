"""The chapter sidebar (F9) and Ctrl+PgUp / Ctrl+PgDn."""
import json
from pathlib import Path

from notterizmus.guide import b, h
from notterizmus.rules import config_dir

from . import support as ui


class SidebarTest(ui.UITestCase):
    def setUp(self):
        super().setUp()
        if not self.win.split.get_show_sidebar():
            self.win.lookup_action("sidebar").activate(None)
            ui.pump(0.2)

    def make_book(self, name, titles):
        """Chapters in their own book; returns their paths, with the last one open."""
        paths = [ui.open_chapter([h(t, b("note"))], title=t, book=name).path for t in titles]
        ui.pump(0.2)
        return paths

    def rows_of(self, paths):
        wanted = {Path(p).resolve() for p in paths}
        return [(label, sel) for label, path, sel in self.win.sidebar.chapter_rows()
                if Path(path).resolve() in wanted]

    def test_lists_the_book_in_order_and_marks_the_open_chapter(self):
        paths = self.make_book("Sidebar order", ["Alpha", "Beta", "Gamma"])
        self.assertEqual(self.rows_of(paths), [("Alpha", False), ("Beta", False), ("Gamma", True)])

    def test_clicking_a_chapter_opens_it(self):
        paths = self.make_book("Sidebar click", ["One", "Two"])
        row = next(r for r in self.win.sidebar.rows() if r._path and Path(r._path).resolve() == paths[0].resolve())
        self.win.sidebar.list.emit("row-activated", row)
        ui.settle()
        self.assertEqual(Path(self.win.doc.path).resolve(), paths[0].resolve())
        self.assertEqual(self.rows_of(paths), [("One", True), ("Two", False)])

    def test_ctrl_pgup_and_pgdn_step_through_the_book(self):
        paths = self.make_book("Sidebar keys", ["First", "Second", "Third"])
        view = ui.row(self.win.doc.root.children[0]).view
        self.assertTrue(ui.press(view, "Page_Up", ctrl=True, wait=0.3))
        self.assertEqual(Path(self.win.doc.path).resolve(), paths[1].resolve())
        ui.press(ui.row(self.win.doc.root.children[0]).view, "Page_Up", ctrl=True, wait=0.3)
        ui.press(ui.row(self.win.doc.root.children[0]).view, "Page_Up", ctrl=True, wait=0.3)
        self.assertEqual(Path(self.win.doc.path).resolve(), paths[0].resolve(), "stops at the first chapter")
        self.win.lookup_action("next-chapter").activate(None)
        ui.settle()
        self.assertEqual(Path(self.win.doc.path).resolve(), paths[1].resolve())
        self.assertEqual(self.app.get_accels_for_action("win.next-chapter"), ["<Control>Page_Down"])
        self.assertEqual(self.app.get_accels_for_action("win.prev-chapter"), ["<Control>Page_Up"])

    def test_a_book_row_folds_its_chapters(self):
        paths = self.make_book("Sidebar fold", ["Only"])
        book_row = next(r for r in self.win.sidebar.rows() if r._book == "Sidebar fold")
        self.win.sidebar.list.emit("row-activated", book_row)
        ui.pump(0.1)
        self.assertEqual(self.rows_of(paths), [])
        book_row = next(r for r in self.win.sidebar.rows() if r._book == "Sidebar fold")
        self.win.sidebar.list.emit("row-activated", book_row)
        ui.pump(0.1)
        self.assertEqual(self.rows_of(paths), [("Only", True)])

    def test_f9_hides_it_and_the_choice_is_remembered(self):
        self.assertEqual(self.app.get_accels_for_action("win.sidebar"), ["F9"])
        self.win.lookup_action("sidebar").activate(None)
        ui.pump(0.2)
        self.assertFalse(self.win.split.get_show_sidebar())
        self.assertFalse(json.loads((config_dir() / "state.json").read_text())["sidebar"])
        self.win.lookup_action("sidebar").activate(None)
        ui.pump(0.2)
        self.assertTrue(self.win.split.get_show_sidebar())
        self.assertTrue(json.loads((config_dir() / "state.json").read_text())["sidebar"])

    def test_a_narrow_window_turns_it_into_an_overlay(self):
        if not ui.FRAMES:
            self.skipTest("window resizing is checked on Weston")
        paths = self.make_book("Sidebar narrow", ["One", "Two"])
        try:
            self.win.set_default_size(700, 600)
            self.assertTrue(ui.pump_until(lambda: self.win.split.get_collapsed()))
            ui.pump(0.3)
            self.assertFalse(self.win.split.get_show_sidebar(), "hidden at first in a narrow window")
            self.assertTrue(json.loads((config_dir() / "state.json").read_text()).get("sidebar", True),
                            "collapsing isn't saved as a choice to hide it")
            self.win.lookup_action("sidebar").activate(None)
            ui.pump(0.3)
            self.assertTrue(self.win.split.get_show_sidebar())
            row = next(r for r in self.win.sidebar.rows() if r._path and Path(r._path).resolve() == paths[0].resolve())
            self.win.sidebar.list.emit("row-activated", row)
            ui.settle()
            self.assertEqual(Path(self.win.doc.path).resolve(), paths[0].resolve())
            self.assertFalse(self.win.split.get_show_sidebar(), "picking a chapter closes the overlay")
        finally:
            self.win.set_default_size(1100, 800)
            ui.pump_until(lambda: not self.win.split.get_collapsed())
            ui.pump(0.3)
        self.assertTrue(self.win.split.get_show_sidebar(), "back beside the text in a wide window")

    def test_getting_started_is_not_listed(self):
        self.make_book("Sidebar guide", ["Mine"])
        self.win.lookup_action("guide").activate(None)
        ui.settle()
        self.assertFalse(any(sel for _l, _p, sel in self.win.sidebar.chapter_rows()))
        self.assertFalse(any("Getting Started" in str(p) for _l, p, _s in self.win.sidebar.chapter_rows()))

    def test_switching_back_to_the_window_keeps_focus_in_the_list(self):
        paths = self.make_book("Sidebar focus", ["Kept"])
        row = next(r for r in self.win.sidebar.rows() if r._path and Path(r._path).resolve() == paths[0].resolve())
        row.grab_focus()
        ui.pump(0.1)
        self.win._reload_sidebar()  # what happens when the window becomes active again
        ui.pump(0.1)
        focused = self.win.sidebar.focused_row()
        self.assertIsNotNone(focused)
        self.assertEqual(Path(focused._path).resolve(), paths[0].resolve())
        (paths[0].parent / "99 Added outside.notz").write_text(paths[0].read_text(encoding="utf-8"), encoding="utf-8")
        self.win._reload_sidebar()  # the folder changed: rebuilt, focus stays on the same chapter
        ui.pump(0.1)
        self.assertIn("Added outside", [label for label, _p, _s in self.win.sidebar.chapter_rows()])
        self.assertEqual(Path(self.win.sidebar.focused_row()._path).resolve(), paths[0].resolve())


class SidebarWidthTest(ui.UITestCase):
    def setUp(self):
        super().setUp()
        if not self.win.split.get_show_sidebar():
            self.win.lookup_action("sidebar").activate(None)
        self.win.set_sidebar_width(260, save=True)
        ui.pump(0.3)

    def tearDown(self):
        self.win.set_sidebar_width(260, save=True)
        ui.pump(0.2)

    def drag(self, dx):
        """Drag the handle by dx, as the overlay's drag gesture reports it."""
        gesture = next(c for c in self.ctrls(self.win._overlay) if isinstance(c, ui.Gtk.GestureDrag))
        ok, box = self.win.handle.compute_bounds(self.win._overlay)
        self.win._handle_drag_begin(gesture, box.origin.x + 3, 200)
        self.win._handle_drag_update(gesture, dx, 0)
        ui.pump(0.2)
        self.win._handle_drag_end(gesture, dx, 0)
        ui.pump(0.3)

    @staticmethod
    def ctrls(widget):
        lst = widget.observe_controllers()
        return [lst.get_item(i) for i in range(lst.get_n_items())]

    def saved(self):
        return json.loads((config_dir() / "state.json").read_text()).get("sidebar_width")

    def test_the_handle_sits_on_the_edge(self):
        self.assertEqual(self.win.sidebar.get_width(), 260)
        self.assertTrue(self.win.handle.get_visible())
        ok, box = self.win.handle.compute_bounds(self.win._overlay)
        self.assertLessEqual(abs(box.origin.x + box.size.width / 2 - 260), 1)

    def test_dragging_the_edge_resizes_the_list_and_is_remembered(self):
        self.drag(80)
        self.assertEqual(self.win.sidebar.get_width(), 340)
        self.assertEqual(self.saved(), 340)
        self.assertFalse(self.win.split.get_collapsed())
        again = type(self.win)(self.app)  # a new window starts at the saved width
        try:
            self.assertEqual(again._sidebar_w, 340)
        finally:
            again.destroy()

    def test_dragging_stops_at_the_limits(self):
        self.drag(-500)
        self.assertEqual(self.win.sidebar.get_width(), 180)
        self.drag(3000)
        room = self.win.get_width() - self.win._text_min_width() - 21
        self.assertEqual(self.win.sidebar.get_width(), min(520, room))
        self.assertFalse(self.win.split.get_collapsed(), "dragging never pushes the text out")

    def test_a_drag_that_starts_elsewhere_does_nothing(self):
        gesture = next(c for c in self.ctrls(self.win._overlay) if isinstance(c, ui.Gtk.GestureDrag))
        self.win._handle_drag_begin(gesture, 700, 200)  # in the text, not on the handle
        self.win._handle_drag_update(gesture, 100, 0)
        self.win._handle_drag_end(gesture, 100, 0)
        ui.pump(0.2)
        self.assertEqual(self.win.sidebar.get_width(), 260)

    def test_double_click_on_the_handle_restores_the_default(self):
        self.drag(100)
        click = next(c for c in self.ctrls(self.win.handle) if isinstance(c, ui.Gtk.GestureClick))
        click.emit("pressed", 2, 3, 100)
        ui.pump(0.3)
        self.assertEqual(self.win.sidebar.get_width(), 260)
        self.assertEqual(self.saved(), 260)

    def test_a_wide_list_turns_into_an_overlay_sooner(self):
        if not ui.FRAMES:
            self.skipTest("window resizing is checked on Weston")
        self.win.set_sidebar_width(400, save=True)
        try:
            self.win.set_default_size(1000, 800)  # 400 + the text column don't fit in 1000
            self.assertTrue(ui.pump_until(lambda: self.win.split.get_collapsed()))
            self.assertFalse(self.win.handle.get_visible())
        finally:
            self.win.set_default_size(1100, 800)
            ui.pump_until(lambda: not self.win.split.get_collapsed())
            ui.pump(0.3)
        self.assertTrue(self.win.handle.get_visible())

    def test_a_click_without_moving_changes_nothing(self):
        gesture = next(c for c in self.ctrls(self.win._overlay) if isinstance(c, ui.Gtk.GestureDrag))
        ok, box = self.win.handle.compute_bounds(self.win._overlay)
        self.win._handle_drag_begin(gesture, box.origin.x + 3, 200)
        self.win._handle_drag_update(gesture, 1, 0)  # a wobble, not a drag
        self.win._handle_drag_end(gesture, 1, 0)
        ui.pump(0.2)
        self.assertEqual(self.win.sidebar.get_width(), 260)
        self.assertFalse(self.win.handle.has_css_class("dragging"))
