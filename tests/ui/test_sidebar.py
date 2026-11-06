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
