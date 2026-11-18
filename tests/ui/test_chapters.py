"""Renaming, renumbering, reordering and trashing chapters; renaming books (R2, R28)."""
import json
import shutil
from pathlib import Path

from notterizmus.guide import b, h
from notterizmus.library import parse_name
from notterizmus.model import Document
from notterizmus.rules import config_dir

from . import support as ui


def names(folder):
    return sorted(f.name for f in Path(folder).glob("*.notz"))


def number(path):
    """The chapter number in a file name (it isn't always two digits)."""
    return parse_name(Path(path).stem)[0]


class ChaptersTest(ui.UITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A stand-in Trash inside the scratch folder: the real one would show test files in Files.
        from notterizmus.ui import window as w
        cls.w, cls.saved = w, (w._trash_file, w._restore_from_trash)
        cls.trash = ui.scratch() / "Trash"
        cls.trash.mkdir(exist_ok=True)

        def trash(path):
            shutil.move(str(path), cls.trash / Path(path).name)

        def restore(path):
            src = cls.trash / Path(path).name
            return src.exists() and bool(shutil.move(str(src), path))

        w._trash_file, w._restore_from_trash = trash, restore

    @classmethod
    def tearDownClass(cls):
        cls.w._trash_file, cls.w._restore_from_trash = cls.saved

    def setUp(self):
        super().setUp()
        if not self.win.split.get_show_sidebar():
            self.win.lookup_action("sidebar").activate(None)
            ui.pump(0.2)

    def book(self, name, titles):
        paths = [ui.open_chapter([h(t, b(f"{t} notes"))], title=t, book=name).path for t in titles]
        ui.pump(0.2)
        return paths

    def dialog(self):
        ui.pump_until(lambda: self.win.get_visible_dialog() is not None)
        return self.win.get_visible_dialog()

    def respond(self, dlg, response):
        dlg.emit("response", response)
        dlg.force_close()
        # wait until it's gone: a closing dialog still counts as visible, and it hands
        # focus back to the widget that had it when its animation ends
        ui.pump_until(lambda: self.win.get_visible_dialog() is None)
        ui.pump(0.2)

    def field(self, dlg, cls, title=None):
        return next(w for w in ui.walk(dlg) if isinstance(w, cls) and (title is None or w.get_title() == title))

    def sidebar_row(self, path=None, book=None):
        return next(r for r in self.win.sidebar.rows()
                    if (path and r._path and Path(r._path).resolve() == Path(path).resolve())
                    or (book and r._book == book))

    def test_f2_renames_the_open_chapter_and_autosave_follows_it(self):
        self.assertEqual(self.app.get_accels_for_action("win.rename"), ["F2"])
        old = self.book("Rename open", ["Draft"])[0]
        self.win.lookup_action("rename").activate(None)
        dlg = self.dialog()
        self.assertEqual(dlg.get_heading(), "Chapter Properties")
        self.field(dlg, ui.Adw.EntryRow).set_text("Final")
        self.respond(dlg, "apply")
        self.assertEqual(names(old.parent), [old.name.replace("Draft", "Final")])
        self.assertEqual(self.win.doc.chapter_title, "Final")
        self.assertIn("Final", self.win.wtitle.get_title())
        self.assertIn("Final", [label for label, _p, _s in self.win.sidebar.chapter_rows()])
        ui.type_text(ui.row(self.win.doc.root.children[0]).view, " more")
        # autosave goes to the new file, and the old one doesn't come back
        ui.wait_for(lambda: " more" in Document.load(self.win.doc.path).root.children[0].text, "the autosave")
        self.assertFalse(old.exists())
        self.assertEqual(json.loads((config_dir() / "state.json").read_text())["last_file"], str(self.win.doc.path))

    def test_a_taken_number_is_swapped_and_the_dialog_says_so(self):
        first, second = self.book("Swap", ["One", "Two"])
        self.win.lookup_action("chapter-props").activate(ui.GLib.Variant.new_string(str(first)))
        dlg = self.dialog()
        spin = self.field(dlg, ui.Adw.SpinRow)
        spin.set_value(spin.get_value() + 1)
        hint = next(w for w in ui.walk(dlg) if isinstance(w, ui.Gtk.Label) and "swap" in w.get_text())
        self.assertTrue(hint.get_visible())
        self.respond(dlg, "apply")
        n1 = number(first)
        self.assertEqual(names(first.parent), [f"{n1:02d} Two.notz", f"{n1 + 1:02d} One.notz"])
        self.assertEqual(Document.load(first.parent / f"{n1:02d} Two.notz").chapter_no, n1)

    def test_moving_to_another_book_is_blocked_while_its_number_is_taken(self):
        mine = self.book("Move from", ["Wanderer"])[0]
        self.book("Move to", ["Resident"])
        resident_no = number(names(ui.scratch() / "Documents" / "Notterizmus" / "Move to")[0])
        self.win.lookup_action("chapter-props").activate(ui.GLib.Variant.new_string(str(mine)))
        dlg = self.dialog()
        combo = self.field(dlg, ui.Adw.ComboRow)
        books = [combo.get_model().get_string(i) for i in range(combo.get_model().get_n_items())]
        combo.set_selected(books.index("Move to"))
        self.field(dlg, ui.Adw.SpinRow).set_value(resident_no)
        self.assertFalse(dlg.get_response_enabled("apply"))
        self.field(dlg, ui.Adw.SpinRow).set_value(resident_no + 50)
        self.assertTrue(dlg.get_response_enabled("apply"))
        self.respond(dlg, "apply")
        target = mine.parent.parent / "Move to"
        self.assertIn(f"{resident_no + 50:02d} Wanderer.notz", names(target))
        self.assertEqual(names(mine.parent), [])
        self.assertEqual(self.win.doc.book, "Move to")

    def test_alt_down_in_the_list_swaps_with_the_next_chapter(self):
        a, b2 = self.book("Alt keys", ["Aa", "Bb"])
        row = self.sidebar_row(path=a)
        row.grab_focus()
        ui.pump(0.1)
        self.assertTrue(ui.press(self.win.sidebar.list, "Down", alt=True, wait=0.4))
        na, nb = number(a), number(b2)
        self.assertEqual(names(a.parent), [f"{na:02d} Bb.notz", f"{nb:02d} Aa.notz"])
        focused = self.win.sidebar.focused_row()
        self.assertTrue(focused is not None and focused._path.name == f"{nb:02d} Aa.notz",
                        "focus follows the moved chapter, so Alt+↓ can repeat")

    def test_dragging_a_chapter_reorders_the_book(self):
        x, y, z = self.book("Drag", ["X", "Y", "Z"])
        nums = sorted(number(p) for p in (x, y, z))
        self.assertTrue(self.win.sidebar.drop_chapter(str(z), x, after=False))
        ui.pump(0.3)
        self.assertEqual(names(x.parent), [f"{nums[0]:02d} Z.notz", f"{nums[1]:02d} X.notz", f"{nums[2]:02d} Y.notz"])
        self.assertFalse(self.win.sidebar.drop_chapter(str(x.parent / f"{nums[0]:02d} Z.notz"),
                                                       ui.scratch() / "elsewhere.notz"))

    def test_moving_the_open_chapter_to_trash_closes_it_and_undo_brings_it_back(self):
        path = self.book("Trash", ["Doomed"])[0]
        toasts = []
        self.win.toast = lambda msg, button=None, cb=None: toasts.append((msg, button, cb))
        try:
            self.win.lookup_action("chapter-trash").activate(ui.GLib.Variant.new_string(str(path)))
            ui.pump(0.3)
            self.assertFalse(path.exists())
            self.assertIsNone(self.win.doc)
            self.assertEqual(self.win.stack.get_visible_child_name(), "empty")
            msg, button, undo = toasts[-1]
            self.assertEqual((msg, button), ("“Doomed” moved to Trash", "Undo"))
            undo()
            ui.settle()
            self.assertTrue(path.exists())
            self.assertEqual(Path(self.win.doc.path).resolve(), path.resolve())
        finally:
            del self.win.toast

    def type_into_first_item(self, text):
        r = ui.focus(self.win.doc.root.children[0])
        ui.type_text(r.view, text)

    def test_a_chapter_opened_from_files_saves_the_open_one_first(self):
        """A chapter opened from Files (App.do_open) replaced the open one while its
        autosave was still pending, which then saved the new chapter instead: the last
        edits of the old one were lost, and reopening the same chapter dropped them (CR4)."""
        first, second = self.book("From Files", ["First", "Second"])
        self.win.open_path(first)
        ui.settle()
        self.type_into_first_item(" typed")
        ui.app().do_open([ui.Gio.File.new_for_path(str(second))], 1, "")  # before the autosave
        ui.settle()
        self.assertIn("First typed", first.read_text(encoding="utf-8"))
        self.type_into_first_item(" again")
        ui.app().do_open([ui.Gio.File.new_for_path(str(second))], 1, "")  # the open chapter itself
        ui.settle()
        self.assertEqual(self.win.doc.root.children[0].text, "Second again")
        self.assertIn("Second again", second.read_text(encoding="utf-8"))

    def test_undoing_a_trash_saves_the_chapter_opened_meanwhile(self):
        doomed, other = self.book("Untrash", ["Doomed", "Other"])
        toasts = []
        self.win.toast = lambda msg, button=None, cb=None: toasts.append((msg, button, cb))
        try:
            self.win.open_path(doomed)
            ui.settle()
            self.win.lookup_action("chapter-trash").activate(ui.GLib.Variant.new_string(str(doomed)))
            ui.wait_for(lambda: self.win.doc is None, "the trashed chapter to close")
            undo = toasts[-1][2]
            self.win.open_path(other)
            ui.settle()
            self.type_into_first_item(" typed")
            undo()  # reopens the trashed chapter before the autosave
            ui.settle()
            self.assertIn("Other typed", other.read_text(encoding="utf-8"))
            self.assertEqual(Path(self.win.doc.path).resolve(), doomed.resolve())
        finally:
            del self.win.toast

    def test_a_chapter_left_hidden_by_an_interrupted_change_can_be_restored(self):
        """A crash or power cut in the middle of a reorder leaves a chapter under a hidden
        staging name, gone from the list: the app offers to give it back (CR6)."""
        path = self.book("Stranded", ["Lost"])[0]
        path.rename(path.parent / ".moving-0123abcd.notz")
        toasts = []
        self.win.toast = lambda msg, button=None, cb=None: toasts.append((msg, button, cb))
        try:
            self.win._offer_stranded()  # as when the app starts
            msg, button, restore = toasts[-1]
            self.assertEqual((msg, button), ("An interrupted change left 1 chapter hidden", "Restore"))
            restore()
            self.assertEqual(toasts[-1][0], "Restored 1 chapter")
            self.assertEqual(names(path.parent), [path.name])
        finally:
            del self.win.toast

    def test_rename_book_renames_the_folder_and_its_chapters(self):
        a, _b = self.book("Old title", ["Ch A", "Ch B"])
        self.book("Taken title", ["Other"])
        self.win.open_path(a)  # the open chapter moves with its book
        ui.settle()
        self.sidebar_row(book="Old title").grab_focus()
        self.win.lookup_action("rename").activate(None)  # F2 on a book row
        dlg = self.dialog()
        self.assertEqual(dlg.get_heading(), "Rename Book")
        entry = self.field(dlg, ui.Adw.EntryRow)
        entry.set_text("taken title")
        self.assertFalse(dlg.get_response_enabled("apply"))
        entry.set_text("New title")
        self.assertTrue(dlg.get_response_enabled("apply"))
        self.respond(dlg, "apply")
        new = a.parent.parent / "New title"
        self.assertFalse(a.parent.exists())
        self.assertEqual({Document.load(f).book for f in new.glob("*.notz")}, {"New title"})
        self.assertEqual(self.win.wtitle.get_subtitle(), "New title")
        self.assertEqual(Path(self.win.doc.path).parent.name, "New title")
        self.assertIn("New title", [r._book for r in self.win.sidebar.rows() if r._book])
        self.assertEqual(len(self.win.sidebar.chapter_rows()) >= 2, True)

    def test_the_list_menu_has_numbered_choices(self):
        path = self.book("Menu", ["Only"])[0]
        # with the Menu key, on the focused row: the list scrolls to the row first (a menu
        # for a row that is out of sight has nowhere to appear)
        self.sidebar_row(path=path).grab_focus()
        ui.pump(0.2)
        self.assertTrue(ui.press(self.win.sidebar.list, "Menu"))
        ui.wait_for(ui.open_popovers, "the chapter's menu")
        choices = [(n, t) for n, t, _r in ui.menu_choices(ui.open_popovers()[0])]
        self.assertEqual(choices, [("1", "Chapter Properties…"), ("2", "Move Up"), ("3", "Move Down"),
                                   ("4", "Move to Trash")])

    # -- a file in the book that isn't a chapter (damaged, or put there by something else) --------

    def broken_book(self, name):
        a, b2 = self.book(name, ["Aa", "Bb"])
        broken = a.parent / "03 Broken.notz"
        broken.write_text("[]", encoding="utf-8")
        self.win._reload_sidebar()
        return a, b2, broken

    def test_reordering_past_a_file_that_is_not_a_chapter_is_refused_and_nothing_moves(self):
        a, b2, broken = self.broken_book("Broken order")
        before = sorted(f.name for f in a.parent.iterdir())
        toasts = []
        self.win.toast = lambda msg, button=None, cb=None: toasts.append(msg)
        try:
            self.assertTrue(self.win.sidebar.drop_chapter(str(broken), a, after=False))  # dragged to the top
            ui.pump(0.2)
        finally:
            del self.win.toast
        self.assertEqual(toasts, ["Could not reorder the chapters: this isn't a Notterizmus chapter file"])
        self.assertEqual(sorted(f.name for f in a.parent.iterdir()), before,
                         "every chapter keeps its name; none is left under a hidden one")
        self.assertEqual(Path(self.win.doc.path).resolve(), b2.resolve())
        self.assertEqual([label for label, p, _s in self.win.sidebar.chapter_rows() if Path(p).parent == a.parent],
                         ["Aa", "Bb", "Broken"])

    def test_renaming_a_book_takes_a_file_that_is_not_a_chapter_along(self):
        a, b2, broken = self.broken_book("Broken rename")
        self.win.apply_book_rename(a.parent, "Renamed with it")
        ui.pump(0.2)
        new = a.parent.parent / "Renamed with it"
        self.assertFalse(a.parent.exists())
        self.assertEqual(names(new), [a.name, b2.name, "03 Broken.notz"])
        self.assertEqual((new / "03 Broken.notz").read_text(encoding="utf-8"), "[]")
        self.assertEqual({Document.load(new / f).book for f in (a.name, b2.name)}, {"Renamed with it"})
        self.assertEqual((Path(self.win.doc.path), self.win.doc.book), (new / b2.name, "Renamed with it"),
                         "the open chapter follows its book")
