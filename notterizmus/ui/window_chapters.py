"""The window's chapter files (CR38 in CODE_REVIEW.md): new, open, Getting Started,
previous and next, Chapter Properties, renaming a book, and reordering and trashing
chapters from the chapter list.

Uses the window's doc, sidebar, split, state, rules, toast(), set_doc(), open_path(),
_close_doc(), _update_title(), _reload_sidebar() and WindowSaving's _flush_save()."""
from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk

from .. import assessments, backups, guide, library, paths
from ..model import Document, chapter_filename
from .helpers import WORKER, assessments_root, notes_root, run_once, save_state


class WindowChapters:
    def on_new(self, *_):
        last = self.state.get("last_book", "")
        number = self.doc.chapter_no + 1 if self.doc and self.doc.book == last else 1
        self._new_chapter_dialog(last, number, "")

    def _new_chapter_dialog(self, book_text, number, title_text):
        dlg = Adw.AlertDialog(heading="New Chapter",
                              body="Each book + chapter is saved as its own file.")
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        book = Adw.EntryRow(title="Book")
        book.set_text(book_text)
        num = Adw.SpinRow.new_with_range(1, 999, 1)
        num.set_title("Chapter number")
        num.set_value(number)
        title = Adw.EntryRow(title="Chapter title (optional)")
        title.set_text(title_text)
        for r in (book, num, title):
            lb.append(r)
        dlg.set_extra_child(lb)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("create", "Create")
        dlg.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("create")
        dlg.set_close_response("cancel")

        def on_resp(_d, resp):
            if resp != "create":
                return
            b = book.get_text().strip() or "Unsorted"
            n = int(num.get_value())
            t = title.get_text().strip()
            folder = notes_root() / library.safe_name(b)
            existing = library.chapter_numbered(folder, n)  # by number: 10 isn't 100 (CR16)
            if existing:
                self.open_path(existing.path)
                self.toast("That chapter already exists — opened it")
                return
            doc = Document.new(b, n, t, folder / chapter_filename(n, t))
            try:
                doc.save()
            except OSError as e:  # an unwritable folder, a full disk (CR15)
                self.toast(f"Could not create the chapter: {e.strerror or e}")
                dlg.connect("closed", lambda *_: self._new_chapter_dialog(b, n, t))  # asked again, as typed
                return
            self.set_doc(doc)

        dlg.connect("response", on_resp)
        dlg.present(self)
        GLib.idle_add(run_once, lambda: (title if book.get_text() else book).grab_focus())

    def on_open(self, *_):
        fd = Gtk.FileDialog(title="Open Chapter")
        root = notes_root()
        root.mkdir(parents=True, exist_ok=True)
        start = Path(self.doc.path).parent if self.doc and self.doc.path and not self._is_guide() else root
        fd.set_initial_folder(Gio.File.new_for_path(str(start)))
        f = Gtk.FileFilter(name="Chapter notes (*.notz)")
        f.add_pattern("*.notz")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(f)
        fd.set_filters(filters)

        def done(dialog, res):
            try:
                gf = dialog.open_finish(res)
            except GLib.Error:
                return
            if gf:
                self.open_path(gf.get_path())

        fd.open(self, None, done)

    def on_guide(self, *_):
        """Open a fresh practice copy of the Getting Started chapter."""
        self._flush_save()  # now, and not after the fresh copy is written: it may be the guide
        doc = guide.document(paths.guide_path(), self.rules)
        try:
            doc.save()
        except OSError as e:
            self.toast(f"Could not create the guide: {e}")
            return
        self.set_doc(doc)
        self.toast("A practice copy: change anything. F1 brings back a fresh one.")

    def _open_from_sidebar(self, path):
        if not (self.doc and self.doc.path and Path(self.doc.path).resolve() == Path(path).resolve()):
            self.open_path(path)
        if self.split.get_collapsed():
            self.split.set_show_sidebar(False)

    def on_chapter_step(self, delta):
        """Open the previous (-1) or next (+1) chapter of the current book."""
        if not self.doc or self._is_guide():
            self.toast("Open a chapter of a book first")
            return
        books = library.scan(notes_root())
        book, _i = library.find(books, self.doc.path)
        if book is None:
            self.toast("This chapter isn't in the notes folder")
            return
        ch = library.neighbor(books, self.doc.path, delta)
        if ch is None:
            self.toast(f"No {'next' if delta > 0 else 'previous'} chapter in “{book.name}”")
            return
        self.open_path(ch.path)

    def on_rename(self, *_):
        """F2: the focused sidebar row (chapter or book), else the open chapter."""
        focus = self.get_focus()
        target = self.sidebar.focused_target() if focus is not None and focus.is_ancestor(self.sidebar) else None
        if target is not None:
            kind, path = target
            if kind == "book":
                return self.on_book_rename(str(path))
            return self.on_chapter_props(str(path))
        if not self.doc or self._is_guide() or not self.doc.path:
            self.toast("Open a chapter of a book first")
            return
        self.on_chapter_props(str(self.doc.path))

    def _dialog(self, heading, rows, apply_label):
        dlg = Adw.AlertDialog(heading=heading)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        for r in rows:
            lb.append(r)
        hint = Gtk.Label(xalign=0, wrap=True, css_classes=["dim-label"], visible=False)
        box.append(lb)
        box.append(hint)
        dlg.set_extra_child(box)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("apply", apply_label)
        dlg.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("apply")
        dlg.set_close_response("cancel")
        return dlg, hint

    def on_chapter_props(self, path):
        """Rename a chapter, change its number, or move it to another book."""
        if self.doc and library.same_file(self.doc.path, path):
            self._flush_save()
        path = Path(path)
        try:
            doc = Document.load(path)
        except (OSError, ValueError) as e:
            self.toast(f"Could not read {path.name}: {e}")
            return
        books = [b.path for b in library.scan(notes_root())]
        if not any(library.same_file(b, path.parent) for b in books):
            books.append(path.parent)
        names = Gtk.StringList.new([b.name for b in books])
        book = Adw.ComboRow(title="Book", model=names)
        book.set_selected(next(i for i, b in enumerate(books) if library.same_file(b, path.parent)))
        num = Adw.SpinRow.new_with_range(1, 999, 1)
        num.set_title("Chapter number")
        num.set_value(doc.chapter_no or 1)
        title = Adw.EntryRow(title="Chapter title (optional)")
        title.set_text(doc.chapter_title)
        dlg, hint = self._dialog("Chapter Properties", [book, num, title], "Apply")

        def target():
            return books[book.get_selected()], int(num.get_value())

        def validate(*_):
            folder, n = target()
            other = library.chapter_numbered(folder, n, exclude=path)
            ok, msg = True, ""
            if other is not None and not library.same_file(folder, path.parent):
                ok, msg = False, f"“{folder.name}” already has chapter {n}, “{other.label}”."
            elif other is not None:
                msg = f"Chapter {n}, “{other.label}”, gets number {doc.chapter_no} (they swap)."
            hint.set_text(msg)
            hint.set_visible(bool(msg))
            dlg.set_response_enabled("apply", ok)

        book.connect("notify::selected", validate)
        num.connect("notify::value", validate)
        validate()

        def on_resp(_d, resp):
            if resp == "apply":
                folder, n = target()
                self.apply_chapter_props(path, folder, n, title.get_text().strip())

        dlg.connect("response", on_resp)
        dlg.present(self)
        GLib.idle_add(run_once, title.grab_focus)

    def apply_chapter_props(self, path, folder, number, title):
        self._flush_save()
        same_book = library.same_file(folder, Path(path).parent)
        try:
            moved = library.set_chapter(path, number, title, None if same_book else folder)
        except FileExistsError:
            self.toast(f"“{Path(folder).name}” already has a chapter {number}")
            self._offer_stranded()
            return
        except (OSError, ValueError) as e:  # ValueError: a file that isn't a chapter
            self.toast(f"Could not change the chapter: {e}")
            self._offer_stranded()
            return
        if not same_book:
            self.sidebar.expanded.add(Path(folder).name)
        self._after_move(moved)

    def on_book_rename(self, folder):
        folder = Path(folder)
        old = library.book_name(folder)
        entry = Adw.EntryRow(title="Book name")
        entry.set_text(old)
        dlg, hint = self._dialog("Rename Book", [entry], "Rename")
        others = {d.name.casefold() for d in notes_root().iterdir()
                  if d.is_dir() and not library.same_file(d, folder)} if notes_root().exists() else set()

        def validate(*_):
            name = entry.get_text().strip()
            taken = library.safe_name(name).casefold() in others
            hint.set_text("Another book already has that name." if taken else "")
            hint.set_visible(taken)
            dlg.set_response_enabled("apply", bool(name) and not taken and name != old)

        entry.connect("changed", validate)
        validate()
        dlg.connect("response", lambda _d, resp: resp == "apply" and self.apply_book_rename(
            folder, entry.get_text().strip()))
        dlg.present(self)
        GLib.idle_add(run_once, entry.grab_focus)

    def apply_book_rename(self, folder, name):
        self._flush_save()
        old_folder = Path(folder)
        failed = []
        try:
            moved = library.rename_book(old_folder, name, failed)
        except FileExistsError:
            self.toast("Another book already has that name")
            return
        except (OSError, ValueError) as e:
            self.toast(f"Could not rename the book: {e}")
            return
        if old_folder.name in self.sidebar.expanded:
            self.sidebar.expanded.discard(old_folder.name)
            self.sidebar.expanded.add(library.safe_name(name))
        self._after_move(moved)
        if failed:
            self.toast(f"Renamed, but {len(failed)} chapter(s) kept the old book name: "
                       + ", ".join(f.name for f in failed))

    def _reorder_chapters(self, order, moving):
        self._flush_save()
        try:
            moved = library.reorder(order)
        except (OSError, ValueError) as e:  # FileExistsError is an OSError
            self.toast(f"Could not reorder the chapters: {e}")
            self._reload_sidebar()
            self._offer_stranded()
            return
        self._after_move(moved, focus=moving)

    def _after_move(self, moved, focus=None):
        """Point the open chapter at its new file and refresh the list."""
        try:
            backups.move(moved, notes_root(), paths.backups_dir())  # earlier versions follow
        except OSError as e:
            self._versions_failed("Earlier Versions couldn't follow the renamed chapters", e)
        if moved:  # and assessments, in the background
            WORKER.run(lambda m=dict(moved), root=assessments_root(), notes=notes_root():
                       assessments.follow_moves(root, m, notes),
                       done=lambda _changed: self.refresh_linked(),
                       failed=lambda e: self.toast(f"Assessments couldn't follow the chapter: {e}"))
        if self.doc and self.doc.path:
            new = next((n for o, n in moved.items() if library.same_file(o, self.doc.path)), None)
            if new is not None:
                new = Path(new)
                try:
                    fresh = Document.load(new)
                    book, number, title = fresh.book, fresh.chapter_no, fresh.chapter_title
                except (OSError, ValueError) as e:
                    # Follow it anyway, or the next autosave would write the chapter back under
                    # its old name, beside the moved one (RV5 in PLAN.md): the number and title
                    # come from the new name, and the next save writes this version there.
                    number, title = library.parse_name(new.stem)
                    number = self.doc.chapter_no if number is None else number
                    same_book = library.same_file(new.parent, Path(self.doc.path).parent)
                    book = self.doc.book if same_book else library.book_name(new.parent)
                    self.toast(f"“{new.name}” couldn't be read back after the change "
                               f"({e.strerror if isinstance(e, OSError) and e.strerror else 'not a chapter file'}): "
                               "this window's version will be saved there")
                self.doc.path = new
                self.doc.book, self.doc.chapter_no, self.doc.chapter_title = book, number, title
                self.doc.remember_disk()  # written by the move, not by another program
                self.state["last_file"] = str(new)
                self.state["last_book"] = book
                save_state(self.state)
                self._update_title()
        self._reload_sidebar()
        if focus is not None:
            self.sidebar.focus_path(moved.get(Path(focus), focus))

    def _offer_stranded(self):
        """Offer to give back chapters that a change left under a hidden staging name
        (CR6): at start-up, after a crash or power cut in the middle of a reorder, and
        after a change that failed and couldn't be wholly undone."""
        lost = library.stranded(notes_root())
        if lost:
            n = len(lost)
            self.toast(f"An interrupted change left {n} chapter{'s' if n > 1 else ''} hidden", "Restore",
                       lambda: self._restore_stranded(lost))

    def _restore_stranded(self, lost):
        failed = []
        for path in lost:
            try:
                library.restore_stranded(path)
            except (OSError, ValueError) as e:
                failed.append(f"{path.name}: {e}")
        self._reload_sidebar()
        n = len(lost) - len(failed)
        self.toast(f"Could not restore {failed[0]}" if failed else f"Restored {n} chapter{'s' if n > 1 else ''}")

    def on_chapter_move(self, path, delta):
        """Alt+↑/↓ in the sidebar: swap places (and numbers) with the neighbour."""
        books = library.scan(notes_root())
        book, i = library.find(books, path)
        if book is None or not 0 <= i + delta < len(book.chapters):
            return
        order = list(book.chapters)
        order[i], order[i + delta] = order[i + delta], order[i]
        self._reorder_chapters(order, book.chapters[i].path)

    def on_chapter_trash(self, path):
        path = Path(path)
        is_open = bool(self.doc and library.same_file(self.doc.path, path))
        if is_open:
            self._flush_save()
        label = library.Chapter(*library.parse_name(path.stem), path).label
        try:
            data = path.read_bytes()
            _trash_file(path)
        except (OSError, GLib.Error) as e:
            self.toast(f"Could not move “{label}” to Trash: {getattr(e, 'message', e)}")
            return
        if is_open:
            self._close_doc()
        self._reload_sidebar()
        self.toast(f"“{label}” moved to Trash", "Undo", lambda: self._untrash(path, data, is_open))

    def _untrash(self, path, data, reopen):
        if path.exists():
            self.toast(f"{path.name} exists again, so it was left in the Trash")
            return
        if not _restore_from_trash(path):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)  # no trash access (e.g. inside a sandbox): write it back
            except OSError as e:  # (CR27)
                self.toast(f"Could not put “{path.stem}” back: {e.strerror or e}")
                return
        if reopen:
            self.open_path(path)
        self._reload_sidebar()


def _trash_file(path):
    Gio.File.new_for_path(str(path)).trash(None)


def _restore_from_trash(path):
    """Move the most recently trashed copy of path back. False if it can't be found."""
    try:
        trash = Gio.File.new_for_uri("trash:///")
        found = None
        it = trash.enumerate_children("standard::name,trash::orig-path,trash::deletion-date",
                                      Gio.FileQueryInfoFlags.NONE, None)
        for info in it:
            if info.get_attribute_byte_string("trash::orig-path") == str(path):
                date = info.get_attribute_string("trash::deletion-date") or ""
                if found is None or date > found[0]:
                    found = (date, it.get_child(info))
        if found is None:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        found[1].move(Gio.File.new_for_path(str(path)), Gio.FileCopyFlags.NONE, None, None, None)
        return True
    except GLib.Error:
        return False
