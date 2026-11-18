"""The window's own actions: saving, new chapters, plain text, rules, spelling, dialogs."""
import json
from pathlib import Path

from notterizmus import APP_NAME, VERSION
from notterizmus.export import to_plain
from notterizmus.guide import b, h
from notterizmus.layout import layout
from notterizmus.model import Document
from notterizmus.rules import config_dir, user_rules_path

from . import support as ui


def state():
    return json.loads((config_dir() / "state.json").read_text())


class WindowTest(ui.UITestCase):
    def setUp(self):
        super().setUp()
        self.toasts = []
        self.win.toast = lambda msg, button=None, cb=None: self.toasts.append(msg)
        self.addCleanup(lambda: self.win.__dict__.pop("toast", None))

    def activate(self, action, target=None):
        self.win.lookup_action(action).activate(ui.GLib.Variant.new_string(target) if target is not None else None)

    def dialog(self):
        ui.wait_for(lambda: self.win.get_visible_dialog() is not None, "the dialog to open")
        return self.win.get_visible_dialog()

    def close(self, dlg):
        dlg.force_close()
        ui.wait_for(lambda: self.win.get_visible_dialog() is None, "the dialog to close")

    # -- files ------------------------------------------------------------------------------------

    def test_ctrl_s_saves_now_and_says_so(self):
        self.assertEqual(self.app.get_accels_for_action("win.save"), ["<Control>s"])
        doc = ui.open_chapter([h("Intro", b("note"))])
        ui.type_text(ui.focus(doc.root.children[0]).view, " typed")
        self.activate("save")
        self.assertEqual(Document.load(doc.path).root.children[0].text, "Intro typed")
        self.assertEqual(self.toasts, ["Saved"])

    def test_closing_the_window_saves_what_autosave_has_not_yet(self):
        doc = ui.open_chapter([h("Intro")])
        ui.type_text(ui.focus(doc.root.children[0]).view, " unsaved")
        self.assertEqual(Document.load(doc.path).root.children[0].text, "Intro")
        self.assertFalse(self.win._on_close(), "and lets the window close")
        self.assertEqual(Document.load(doc.path).root.children[0].text, "Intro unsaved")
        self.assertIsNone(self.win._save_src, "nothing left to save later")

    def test_the_title_shows_the_chapter_and_its_book(self):
        ui.open_chapter([h("x")], title="Named", book="Title book")
        number = self.win.doc.chapter_no
        self.assertEqual((self.win.wtitle.get_title(), self.win.wtitle.get_subtitle()),
                         (f"Chapter {number} — Named", "Title book"))
        self.assertEqual(self.win.get_title(), f"Chapter {number} — Named · {APP_NAME}")
        ui.open_chapter([h("x")], title="", book="Title book")
        self.assertEqual(self.win.wtitle.get_title(), f"Chapter {self.win.doc.chapter_no}")

    def test_a_file_that_cannot_be_read_is_reported_and_the_open_chapter_stays(self):
        doc = ui.open_chapter([h("Still here")])
        broken = doc.path.parent / "98 Broken.notz"
        broken.write_text("{not json", encoding="utf-8")
        self.win.open_path(broken)
        self.assertIs(self.win.doc, doc)
        self.assertEqual(len(self.toasts), 1)
        self.assertTrue(self.toasts[0].startswith("Could not open 98 Broken.notz"), self.toasts)
        self.win.open_path(doc.path.parent / "99 Missing.notz")
        self.assertTrue(self.toasts[1].startswith("Could not open 99 Missing.notz"))
        broken.unlink()

    def test_a_file_that_is_json_but_not_a_chapter_is_reported_the_same_way(self):
        # These raised errors the window didn't expect, so nothing was said at all.
        doc = ui.open_chapter([h("Still here")])
        other = doc.path.parent / "97 Other.notz"
        for text in ("[]", "null", '{"content": [1, 2]}', '{"chapter": "one"}'):
            del self.toasts[:]
            other.write_text(text, encoding="utf-8")
            self.win.open_path(other)
            self.assertIs(self.win.doc, doc, text)
            self.assertEqual(self.toasts, ["Could not open 97 Other.notz: this isn't a Notterizmus chapter file"])
            self.assertEqual(other.read_text(encoding="utf-8"), text, "and it is left as it is")
        del self.toasts[:]
        self.activate("chapter-props", str(other))
        self.assertEqual(self.toasts, ["Could not read 97 Other.notz: this isn't a Notterizmus chapter file"])
        self.assertIsNone(self.win.get_visible_dialog())
        other.unlink()

    def test_the_app_starts_when_the_chapter_open_last_is_no_longer_one(self):
        # With such a file as the last one open, the window could not be created: the app
        # didn't start until state.json was edited by hand.
        doc = ui.open_chapter([h("Before")])
        broken = doc.path.parent / "96 Was a chapter.notz"
        broken.write_text("[]", encoding="utf-8")
        state_file = config_dir() / "state.json"
        saved = state_file.read_text()
        state_file.write_text(json.dumps({**json.loads(saved), "last_file": str(broken)}))
        try:
            again = type(self.win)(self.app)
            try:
                self.assertIsNone(again.doc)
                self.assertEqual(again.stack.get_visible_child_name(), "empty")
                self.assertFalse(again.lookup_action("copy").get_enabled())
            finally:
                again.destroy()
        finally:
            state_file.write_text(saved)
            broken.unlink()

    def test_closing_a_chapter_leaves_the_empty_page_and_turns_chapter_actions_off(self):
        ui.open_chapter([h("Intro")])
        self.win._close_doc()
        self.assertEqual(self.win.stack.get_visible_child_name(), "empty")
        self.assertEqual(self.win.wtitle.get_title(), APP_NAME)
        for name in ("copy", "save", "find", "replace", "insert-table", "show-plain"):
            self.assertFalse(self.win.lookup_action(name).get_enabled(), name)
        self.assertNotIn("last_file", state())
        self.activate("rename")
        self.activate("prev-chapter")
        self.activate("versions")
        self.assertEqual(self.toasts, ["Open a chapter of a book first"] * 3)
        ui.open_chapter([h("Back")])
        self.assertTrue(self.win.lookup_action("copy").get_enabled())

    def test_a_file_given_to_the_app_is_opened(self):
        first = ui.open_chapter([h("First")], title="Given").path
        ui.open_chapter([h("Second")])
        self.app.open([ui.Gio.File.new_for_path(str(first))], "")
        ui.settle()
        self.assertEqual(Path(self.win.doc.path), first)

    def test_a_new_window_opens_the_chapter_that_was_open_last(self):
        doc = ui.open_chapter([h("Remembered")])
        self.assertEqual(state()["last_file"], str(doc.path))
        again = type(self.win)(self.app)
        try:
            self.assertEqual(Path(again.doc.path), doc.path)
            self.assertEqual(again.doc.root.children[0].text, "Remembered")
        finally:
            again.destroy()

    # -- the ends of a book -------------------------------------------------------------------------

    def test_stepping_past_the_first_or_last_chapter_says_so(self):
        ui.open_chapter([h("x")], title="Only", book="Lonely book")
        self.activate("next-chapter")
        self.activate("prev-chapter")
        self.assertEqual(self.toasts, ["No next chapter in “Lonely book”", "No previous chapter in “Lonely book”"])
        self.assertEqual(self.win.doc.chapter_title, "Only")

    def test_the_guide_has_no_neighbours_or_properties(self):
        ui.open_chapter([h("Mine")])
        self.activate("guide")
        ui.settle()
        del self.toasts[:]
        self.activate("next-chapter")
        self.activate("rename")
        self.assertEqual(self.toasts, ["Open a chapter of a book first"] * 2)
        self.assertIsNone(self.win.get_visible_dialog())

    # -- New Chapter --------------------------------------------------------------------------------

    def new_chapter(self, book=None, number=None, title=None):
        self.activate("new")
        dlg = self.dialog()
        self.assertEqual(dlg.get_heading(), "New Chapter")
        entries = [w for w in ui.walk(dlg) if isinstance(w, ui.Adw.EntryRow)]
        spin = next(w for w in ui.walk(dlg) if isinstance(w, ui.Adw.SpinRow))
        if book is not None:
            entries[0].set_text(book)
        if number is not None:
            spin.set_value(number)
        if title is not None:
            entries[1].set_text(title)
        return dlg, entries, spin

    def test_new_chapter_suggests_the_book_and_the_next_number(self):
        ui.open_chapter([h("x")], title="Current", book="Series")
        dlg, entries, spin = self.new_chapter()
        self.assertEqual(entries[0].get_text(), "Series")
        self.assertEqual(int(spin.get_value()), self.win.doc.chapter_no + 1)
        self.close(dlg)

    def test_new_chapter_creates_the_file_and_opens_it(self):
        dlg, _entries, _spin = self.new_chapter(book="Fresh book", number=4, title="  Made here ")
        dlg.emit("response", "create")
        self.close(dlg)
        ui.settle()
        path = self.win.notes_root_path() / "Fresh book" / "04 Made here.notz"
        self.assertTrue(path.is_file())
        doc = self.win.doc
        self.assertEqual((Path(doc.path), doc.book, doc.chapter_no, doc.chapter_title), (path, "Fresh book", 4, "Made here"))
        self.assertEqual([(n.kind, n.text) for n in doc.root.children], [("heading", "")])
        self.assertIs(self.ed.current, doc.root.children[0], "ready to type")
        self.assertIn("Made here", [label for label, _p, _s in self.win.sidebar.chapter_rows()])
        self.assertEqual(state()["last_book"], "Fresh book")

    def test_new_chapter_with_a_number_that_exists_opens_that_chapter(self):
        existing = ui.open_chapter([h("Already written")], title="Here", book="Taken numbers")
        ui.open_chapter([h("elsewhere")])
        dlg, _entries, _spin = self.new_chapter(book="Taken numbers", number=existing.chapter_no, title="Another")
        dlg.emit("response", "create")
        self.close(dlg)
        ui.settle()
        self.assertEqual(Path(self.win.doc.path), existing.path)
        self.assertEqual(self.win.doc.root.children[0].text, "Already written")
        self.assertEqual(self.toasts, ["That chapter already exists — opened it"])
        self.assertEqual(len(list(existing.path.parent.glob("*.notz"))), 1)

    def test_new_chapter_cancelled_or_without_a_book(self):
        doc = ui.open_chapter([h("Stays")])
        dlg, _entries, _spin = self.new_chapter(book="Never made", number=1)
        dlg.emit("response", "cancel")
        self.close(dlg)
        self.assertIs(self.win.doc, doc)
        self.assertFalse((self.win.notes_root_path() / "Never made").exists())
        dlg, _entries, _spin = self.new_chapter(book="   ", number=77, title="No book")
        dlg.emit("response", "create")
        self.close(dlg)
        ui.settle()
        self.assertEqual((self.win.doc.book, Path(self.win.doc.path).parent.name), ("Unsorted", "Unsorted"))

    # -- dialogs ------------------------------------------------------------------------------------

    def test_show_plain_text_shows_the_chapter_as_it_is_copied(self):
        doc = ui.open_chapter([h("Intro", b("note"), h("Sub")), h("Next")])
        self.activate("show-plain")
        dlg = self.dialog()
        view = next(w for w in ui.walk(dlg) if isinstance(w, ui.Gtk.TextView))
        buf = view.get_buffer()
        self.assertEqual(buf.get_text(*buf.get_bounds(), True), to_plain(layout(doc.root, self.win.rules)))
        self.assertFalse(view.get_editable())
        self.close(dlg)

    def test_about_shows_this_version_and_its_release_notes(self):
        self.activate("about")
        dlg = self.dialog()
        self.assertIsInstance(dlg, ui.Adw.AboutDialog)
        self.assertEqual((dlg.get_application_name(), dlg.get_version()), (APP_NAME, VERSION))
        self.assertEqual(dlg.get_release_notes_version(), VERSION)
        self.assertIn("<p>", dlg.get_release_notes())
        self.close(dlg)

    def test_keyboard_shortcuts_opens(self):
        self.assertEqual(self.app.get_accels_for_action("win.shortcuts"), ["<Control>question"])
        self.activate("shortcuts")
        dlg = self.dialog()
        self.assertIsInstance(dlg, ui.Adw.ShortcutsDialog)
        self.close(dlg)

    # -- copying ------------------------------------------------------------------------------------

    def test_copy_for_topcoding_saves_and_follows_the_code_prefix_rule(self):
        doc = ui.open_chapter([h("Intro", b("note"), h("Sub"))])
        ui.type_text(ui.focus(doc.root.children[0]).view, "!")
        self.activate("copy")
        self.assertEqual(Document.load(doc.path).root.children[0].text, "Intro!", "copying saves first")
        self.assertEqual(self.toasts, ["Copied — paste into TopCoding with Ctrl+V"])
        self.assertNotIn("<code>", ui.clipboard("text/html"))
        self.win.rules.data["export"]["code_prefix"] = True
        try:
            self.activate("copy")
            self.assertIn("<code>", ui.clipboard("text/html"))
        finally:
            self.win.rules.data["export"]["code_prefix"] = False

    def test_copy_puts_the_same_text_under_both_plain_text_types(self):
        doc = ui.open_chapter([h("Заглавие", b("бележка"))])
        self.activate("copy")
        plain = to_plain(layout(doc.root, self.win.rules))
        self.assertEqual(ui.clipboard("text/plain"), plain)
        self.assertEqual(ui.clipboard("text/plain;charset=utf-8"), plain)


class RulesFileTest(ui.UITestCase):
    """Reload Formatting Rules applies the user's rules.toml to the open chapter."""

    def setUp(self):
        super().setUp()
        self.toasts = []
        self.win.toast = lambda msg, button=None, cb=None: self.toasts.append(msg)
        self.addCleanup(lambda: self.win.__dict__.pop("toast", None))
        self.addCleanup(self.restore)

    def restore(self):
        user_rules_path().unlink(missing_ok=True)
        self.win.lookup_action("reload-rules").activate(None)
        ui.pump(0.1)

    def reload(self, text):
        user_rules_path().parent.mkdir(parents=True, exist_ok=True)
        user_rules_path().write_text(text, encoding="utf-8")
        self.win.lookup_action("reload-rules").activate(None)
        ui.settle()

    def prefixes(self, doc):
        return [ui.row(n).prefix.get_text() for n in doc.root.walk() if n is not doc.root]

    def test_reloading_applies_the_rules_to_the_open_chapter(self):
        doc = ui.open_chapter([h("Intro", b("note"), h("Sub"))])
        self.assertEqual(self.prefixes(doc), ["Ⅰ) ", "│    • ", "└ Ⅰ.1) "])
        self.reload('[numbering]\nlevels = ["arabic"]\nsuffix = "."\n[markers.dot]\nsymbol = "→"\n')
        self.assertEqual(self.prefixes(doc), ["1. ", "│    → ", "└ 1.1. "])
        self.assertEqual(self.toasts, ["Formatting rules reloaded"])
        self.assertEqual(to_plain(layout(doc.root, self.win.rules)).split("\n")[0], "1. Intro", "exports follow")

    def test_your_own_marker_can_be_typed_and_is_offered_in_the_menus(self):
        self.reload('[markers.idea]\nsymbol = "→"\ntrigger = ">"\nlabel = "Idea"\n')
        doc = ui.open_chapter([h("Intro", b("why"))])
        item = doc.root.children[0].children[0]
        ui.type_text(ui.focus(item, 0).view, "> ", wait=0.3)
        self.assertEqual((item.kind, item.marker, item.text), ("bullet", "idea", "why"))
        self.assertEqual(ui.row(item).prefix.get_text(), "     → ")
        self.ed.show_item_menu(ui.row(item))
        ui.pump(0.2)
        labels = [text for _n, text, _r in ui.menu_choices(ui.open_popovers()[0])]
        self.assertIn("→   Idea      >␣", labels)
        self.assertIn("→   Idea", labels, "under Add as well")

    def test_a_rules_file_with_a_mistake_is_reported_and_the_defaults_stay(self):
        doc = ui.open_chapter([h("Intro", b("note"))])
        for text in ("this is not toml", '[markers]\nstar = "★"\n', "[numbering]\nlevels = []\n"):
            del self.toasts[:]
            self.reload(text)
            self.assertEqual(len(self.toasts), 1, text)
            self.assertTrue(self.toasts[0].startswith("Rules error: "), self.toasts)
            self.assertIn("rules.toml", self.toasts[0])
            self.assertEqual(self.prefixes(doc), ["Ⅰ) ", "     • "], "the chapter is still drawn, with the defaults")


class SpellingSwitchTest(ui.UITestCase):
    def setUp(self):
        super().setUp()
        if not self.win.speller.available or "en_US" not in self.win.languages:
            self.skipTest("no en_US dictionary")
        self.addCleanup(self.switch_on)

    def switch_on(self):
        action = self.win.lookup_action("spell")
        if not action.get_state().get_boolean():
            action.activate(None)
            ui.pump(0.1)

    def marked(self, view):
        buf = view.get_buffer()
        it = buf.get_start_iter()
        return it.starts_tag(view.tag_spell) or it.forward_to_tag_toggle(view.tag_spell)

    def test_check_spelling_can_be_switched_off_and_on_and_is_remembered(self):
        doc = ui.open_chapter([h("Intro", b("a mispeled word"))])
        view = ui.row(doc.root.children[0].children[0]).view
        ui.wait_for(lambda: self.marked(view), "the misspelled word to be underlined")
        self.assertEqual(self.win.lang_btn.get_label(), "EN-US")
        self.win.lookup_action("spell").activate(None)
        ui.pump(0.1)
        self.assertFalse(self.marked(view), "the underlines go at once")
        self.assertFalse(state()["spell"])
        self.assertEqual(self.win.lang_btn.get_label(), "EN-US (off)")
        self.win.lookup_action("spell").activate(None)
        ui.pump(0.1)
        self.assertTrue(self.marked(view))
        self.assertTrue(state()["spell"])

    def test_the_language_is_picked_from_the_chapters_text_and_a_choice_is_saved_in_it(self):
        if "bg_BG" not in self.win.languages:
            self.skipTest("no bg_BG dictionary")
        from notterizmus.model import Node, chapter_filename
        folder = self.win.notes_root_path() / "Spelling book"
        path = folder / chapter_filename(1, "Български")
        Document(Node("root", children=[h("Мащабируемост на системите", b("Kafka е брокер"))]), "Spelling book", 1,
                 "Български", path).save()  # no language stored yet
        self.win.open_path(path)
        ui.settle()
        self.assertEqual(self.win.speller.lang, "bg_BG", "mostly Cyrillic: Bulgarian")
        self.assertEqual(self.win.lang_btn.get_label(), "BG-BG")
        self.win.lookup_action("spell-lang").activate(ui.GLib.Variant.new_string("en_US"))
        self.assertEqual((self.win.doc.lang, self.win.speller.lang), ("en_US", "en_US"))
        self.win._flush_save()
        self.assertEqual(Document.load(path).lang, "en_US")
        self.assertEqual(state()["spell_lang"], "en_US")
