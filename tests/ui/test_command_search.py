"""Search Commands (Ctrl+Shift+P): find a command by name, see its key, run it."""
from notterizmus.guide import b, h

from . import support as ui


class CommandSearchTest(ui.UITestCase):
    def tearDown(self):
        while (dlg := self.win.get_visible_dialog()) is not None:
            dlg.force_close()
            ui.wait_for(lambda: self.win.get_visible_dialog() is not dlg, "a dialog to close")

    def open_search(self, text=""):
        self.win.lookup_action("commands").activate(None)
        ui.wait_for(lambda: self.win.get_visible_dialog() is not None, "Search Commands")
        dlg = self.win.get_visible_dialog()
        self.search(dlg, text)
        return dlg

    def search(self, dlg, text):
        dlg.entry.set_text(text)
        ui.wait_for(lambda: dlg._filled_for == text, "the list to follow the search")

    def titles(self, dlg):
        return [r._cmd.title for r in dlg.rows()]

    def pick(self, dlg, title):
        row = next(r for r in dlg.rows() if r._cmd.title == title)
        ran, run = [], row._cmd.run
        row._cmd.run = lambda: (run(), ran.append(True))  # it runs once the dialog has gone
        dlg.list.emit("row-activated", row)
        ui.wait_for(lambda: ran, f"“{title}” to run")
        ui.settle()

    def test_ctrl_shift_p_opens_it(self):
        accels = self.app.get_accels_for_action("win.commands")
        self.assertEqual([ui.Gtk.accelerator_parse(a) for a in accels],
                         [ui.Gtk.accelerator_parse("<Control><Shift>p")])

    def test_finds_by_name_or_keyword_and_shows_the_key(self):
        ui.open_chapter([h("Intro", b("note"))])
        dlg = self.open_search("rename")
        self.assertEqual(self.titles(dlg)[0], "Chapter Properties…")
        self.search(dlg, "new chap")
        first = dlg.list.get_row_at_index(0)
        self.assertEqual(first._cmd.title, "New Chapter")
        shown = [w for w in ui.walk(first) if isinstance(w, ui.Adw.ShortcutLabel)]
        self.assertEqual([w.get_accelerator() for w in shown], ["<Control>n"])

    def test_runs_an_editor_action_on_the_selection(self):
        doc = ui.open_chapter([h("Intro", b("make me bold"))])
        r = ui.focus(doc.root.children[0].children[0], 0)
        r.view.select_range(0, 4)
        self.pick(self.open_search("bold"), "Bold")
        self.assertEqual([(run.text, run.bold) for run in doc.root.children[0].children[0].runs],
                         [("make", True), (" me bold", False)])

    def test_runs_key_only_behaviour_by_replaying_the_key(self):
        doc = ui.open_chapter([h("Intro", b("first"), b("second"))])
        intro = doc.root.children[0]
        second = intro.children[1]
        ui.focus(second)
        self.pick(self.open_search("indent"), "Indent Item")
        self.assertIs(second.parent, intro.children[0])
        ui.focus(second)
        self.pick(self.open_search("outdent"), "Outdent Item")
        self.assertIs(second.parent, intro)
        ui.focus(second)
        self.pick(self.open_search("move up"), "Move Item Up")
        self.assertEqual([c.text for c in intro.children], ["second", "first"])

    def test_arrow_keys_and_enter_pick_from_the_list(self):
        ui.open_chapter([h("Intro")])
        dlg = self.open_search("chapter")
        rows = list(dlg.rows())
        self.assertGreater(len(rows), 2)
        self.assertTrue(ui.press(dlg.entry, "Down"))
        self.assertIs(dlg.list.get_selected_row(), rows[1])
        ui.press(dlg.entry, "Up")
        self.assertIs(dlg.list.get_selected_row(), rows[0])
        self.assertFalse(ui.press(dlg.entry, "2"), "digits are typed into the search")

    def test_enter_runs_the_first_match(self):
        ui.open_chapter([h("Intro")])
        dlg = self.open_search("chapter list")
        self.assertEqual(self.titles(dlg)[0], "Show or Hide the Chapter List")
        shown = self.win.split.get_show_sidebar()
        dlg.entry.emit("activate")
        ui.wait_for(lambda: self.win.split.get_show_sidebar() != shown, "the chapter list to be toggled")
        self.assertIsNone(self.win.get_visible_dialog())
        self.win.lookup_action("sidebar").activate(None)  # put it back
        ui.wait_for(lambda: self.win.split.get_show_sidebar() == shown, "the chapter list back")

    def test_without_an_open_chapter_only_window_commands_are_offered(self):
        ui.open_chapter([h("Intro")])
        self.win._close_doc()
        titles = self.titles(self.open_search())
        self.assertIn("New Chapter", titles)
        self.assertNotIn("Bold", titles)
        self.assertNotIn("Chapter Properties…", titles)
        self.assertNotIn("Copy for TopCoding", titles, "disabled commands are left out")

    def test_nothing_matching_shows_a_note(self):
        ui.open_chapter([h("Intro")])
        dlg = self.open_search("zzzz qqq")
        self.assertEqual(self.titles(dlg), [])
