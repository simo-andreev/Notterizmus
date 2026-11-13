"""Real key presses (Broadway): each goes through GTK's whole event dispatch to whatever
has keyboard focus, as when you type. These catch what emitting signals can't, such as
Escape going to the wrong widget (the find bar once stayed open)."""
from pathlib import Path

from notterizmus.guide import b, h

from . import support as ui


class RealKeysTest(ui.UITestCase):
    def setUp(self):
        super().setUp()
        if ui.BROADWAY_PORT is None:
            self.skipTest("real key presses need the Broadway display (the default runner)")
        self.win.findbar.set_search_mode(False)
        self.win.set_zoom(100, save=True, announce=False)
        ui.pump(0.2)

    def tearDown(self):
        while self.win.get_visible_dialog() is not None:
            self.win.get_visible_dialog().force_close()
            ui.pump(0.3)
        ui.close_popovers()
        self.win.findbar.set_search_mode(False)
        self.win.set_zoom(100, save=True, announce=False)
        if not self.win.split.get_show_sidebar():
            self.win.lookup_action("sidebar").activate(None)
        ui.pump(0.2)

    def chapter(self, *nodes, **kw):
        doc = ui.open_chapter(list(nodes), **kw)
        ui.pump(0.2)
        return doc

    def bar_open(self):
        return self.win.findbar.get_search_mode()

    # -- Escape and the find bar ----------------------------------------------------------------

    def test_escape_closes_the_find_bar_from_the_search_field(self):
        self.chapter(h("Intro", b("find me")))
        ui.focus(self.win.doc.root.children[0].children[0])
        ui.real_key("f", ctrl=True)
        self.assertTrue(self.bar_open())
        ui.real_type("find")
        self.assertEqual(self.win.findbar.entry.get_text(), "find")
        ui.real_key("Escape")
        self.assertFalse(self.bar_open())

    def test_escape_closes_the_find_bar_from_the_replace_field(self):
        self.chapter(h("Intro", b("find me")))
        ui.focus(self.win.doc.root.children[0].children[0])
        ui.real_key("h", ctrl=True)
        self.win.findbar.replace_entry.grab_focus()
        ui.pump(0.1)
        ui.real_type("x")
        self.assertEqual(self.win.findbar.replace_entry.get_text(), "x", "typing goes into the replace field")
        ui.real_key("Escape")
        self.assertFalse(self.bar_open())

    def test_ctrl_r_also_opens_replace(self):
        self.chapter(h("Intro", b("find me")))
        ui.focus(self.win.doc.root.children[0].children[0])
        ui.real_key("r", ctrl=True)
        self.assertTrue(self.bar_open() and self.win.findbar.replacing.get_active())

    def test_escape_closes_the_find_bar_from_a_button(self):
        self.chapter(h("Intro", b("find me")))
        ui.focus(self.win.doc.root.children[0].children[0])
        ui.real_key("f", ctrl=True)
        self.win.findbar.case.grab_focus()
        ui.pump(0.1)
        ui.real_key("Escape")
        self.assertFalse(self.bar_open())

    def test_escape_in_the_text_closes_the_find_bar_and_keeps_the_cursor(self):
        doc = self.chapter(h("Intro", b("one find"), b("two")))
        ui.real_key("f", ctrl=True)
        ui.real_type("find")
        r = ui.focus(doc.root.children[0].children[1], 2)  # back in the text, elsewhere
        ui.real_key("Escape")
        self.assertFalse(self.bar_open())
        self.assertTrue(r.view.has_focus())
        self.assertEqual(r.view.cursor_offset(), 2)

    def test_escape_in_the_text_clears_extra_cursors_before_closing_the_bar(self):
        doc = self.chapter(h("Intro", b("one"), b("two")))
        ui.real_key("f", ctrl=True)
        r = ui.focus(doc.root.children[0].children[0], 0)
        self.ed.add_caret(r.view, 1)
        ui.pump(0.1)
        self.assertTrue(self.ed.mc_views)
        ui.real_key("Escape")
        self.assertFalse(self.ed.mc_views)
        self.assertTrue(self.bar_open(), "the first Escape only clears the extra cursors")
        ui.real_key("Escape")
        self.assertFalse(self.bar_open())

    def test_ctrl_f_starts_at_the_selected_word(self):
        doc = self.chapter(h("Intro", b("scale the scale"), b("scale")))
        r = ui.focus(doc.root.children[0].children[0], 0)
        r.view.select_range(10, 15)
        ui.real_key("f", ctrl=True)
        ui.pump(0.3)
        bar = self.win.findbar
        self.assertEqual(bar.entry.get_text(), "scale")
        self.assertEqual(bar.matches[bar.current], (r.view, 10, 15))

    # -- Search Commands --------------------------------------------------------------------------

    def test_search_commands_runs_bold_on_the_selection_and_escape_closes_it(self):
        doc = self.chapter(h("Intro", b("make me bold")))
        bullet = doc.root.children[0].children[0]
        r = ui.focus(bullet, 0)
        r.view.select_range(0, 4)
        ui.real_key("p", ctrl=True, shift=True)
        self.assertIsNotNone(self.win.get_visible_dialog())
        ui.real_type("bold")
        ui.real_key("Return", wait=0.6)
        self.assertEqual([(run.text, run.bold) for run in bullet.runs], [("make", True), (" me bold", False)])
        ui.real_key("p", ctrl=True, shift=True)
        ui.real_key("Escape", wait=0.6)
        self.assertIsNone(self.win.get_visible_dialog())

    # -- editing ------------------------------------------------------------------------------------

    def test_typing_enter_tab_and_undo(self):
        doc = self.chapter(h("Intro", b("")))
        intro = doc.root.children[0]
        ui.focus(intro.children[0], 0)
        ui.real_type("first")
        ui.real_key("Return")
        ui.real_type("second")
        self.assertEqual([c.text for c in intro.children], ["first", "second"])
        ui.real_key("Tab")
        self.assertEqual([c.text for c in intro.children[0].children], ["second"])
        ui.real_key("Tab", shift=True)
        self.assertEqual([c.text for c in intro.children], ["first", "second"])
        ui.real_key("z", ctrl=True)
        self.assertEqual([c.text for c in self.win.doc.root.children[0].children[0].children], ["second"])
        ui.real_key("z", ctrl=True, shift=True)
        self.assertEqual([c.text for c in self.win.doc.root.children[0].children], ["first", "second"])

    def test_ctrl_space_completes_with_a_digit(self):
        doc = self.chapter(h("Intro", b("completion matters"), b("")))
        target = doc.root.children[0].children[1]
        ui.focus(target, 0)
        ui.real_type("compl")
        ui.real_key("space", ctrl=True, wait=0.4)
        self.assertIsNotNone(self.ed._assist_pop)
        ui.real_key("1", wait=0.4)
        self.assertEqual(target.text, "completion")

    def test_alt_insert_and_a_digit_add_a_sub_item(self):
        doc = self.chapter(h("Intro"))
        intro = doc.root.children[0]
        ui.focus(intro)
        ui.real_key("Insert", alt=True, wait=0.4)
        pop = ui.open_popovers()[0]
        num = next(n for n, t, _r in ui.menu_choices(pop) if t.startswith("Sub-item"))
        ui.real_key(num, wait=0.4)
        self.assertEqual([c.kind for c in intro.children], ["heading"])

    def test_ctrl_t_inserts_a_table_and_tab_moves_between_cells(self):
        doc = self.chapter(h("Intro", b("before")))
        ui.focus(doc.root.children[0].children[0])
        ui.real_key("t", ctrl=True, wait=0.4)
        table = next(n for n in self.win.doc.root.walk() if n.kind == "table")
        ui.real_type("a")
        ui.real_key("Tab")
        ui.real_type("b")
        self.assertEqual(["".join(r.text for r in c) for c in table.data["rows"][0]][:2], ["a", "b"])

    # -- window keys --------------------------------------------------------------------------------

    def test_f2_opens_chapter_properties_and_escape_closes_it(self):
        doc = self.chapter(h("Intro"))
        ui.focus(doc.root.children[0])
        ui.real_key("F2", wait=0.5)
        dlg = self.win.get_visible_dialog()
        self.assertEqual(dlg.get_heading(), "Chapter Properties")
        ui.real_key("Escape", wait=0.6)
        self.assertIsNone(self.win.get_visible_dialog())

    def test_f9_and_ctrl_page_down(self):
        paths = [self.chapter(h(t), title=t, book="Real keys book").path for t in ("One", "Two")]
        self.win.open_path(paths[0])
        ui.settle()
        ui.focus(self.win.doc.root.children[0])
        ui.real_key("Page_Down", ctrl=True, wait=0.4)
        self.assertEqual(Path(self.win.doc.path).resolve(), paths[1].resolve())
        shown = self.win.split.get_show_sidebar()
        ui.real_key("F9")
        self.assertEqual(self.win.split.get_show_sidebar(), not shown)

    def test_zoom_keys(self):
        doc = self.chapter(h("Intro"))
        ui.focus(doc.root.children[0])
        ui.real_key("equal", ctrl=True)
        ui.real_key("plus", ctrl=True)
        self.assertEqual(self.win._zoom, 120)
        ui.real_key("minus", ctrl=True)
        self.assertEqual(self.win._zoom, 110)
        ui.real_key("0", ctrl=True)
        self.assertEqual(self.win._zoom, 100)

    def test_copy_for_topcoding_key(self):
        doc = self.chapter(h("Intro", b("note")))
        ui.focus(doc.root.children[0])
        ui.real_key("c", ctrl=True, shift=True, wait=0.3)
        self.assertIn("Ⅰ) ", ui.clipboard("text/html"))

    # -- typing fast ----------------------------------------------------------------------------------

    def test_enter_right_after_typing_runs_the_typed_command(self):
        self.chapter(h("Intro"))
        ui.focus(self.win.doc.root.children[0])
        shown = self.win.split.get_show_sidebar()
        ui.real_key("p", ctrl=True, shift=True, wait=0.4)
        ui.real_type("chapter list", wait=0)  # no pause before Enter, as a fast typist
        ui.real_key("Return", wait=0.6)
        self.assertEqual(self.win.split.get_show_sidebar(), not shown)
        self.assertIsNone(self.win.get_visible_dialog(), "no other command (like New Chapter) ran")

    def test_enter_right_after_typing_finds_the_typed_text(self):
        doc = self.chapter(h("Intro", b("alpha"), b("omega")))
        ui.focus(doc.root.children[0])
        ui.real_key("f", ctrl=True, wait=0.4)
        ui.real_type("omega", wait=0)
        ui.real_key("Return", wait=0.3)
        bar = self.win.findbar
        self.assertEqual(bar.entry.get_text(), "omega")
        self.assertEqual(bar.matches[bar.current][0], ui.row(doc.root.children[0].children[1]).view)
