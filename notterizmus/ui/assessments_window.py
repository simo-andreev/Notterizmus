"""The Assessments window: TopCoding assessment reports imported from their .txt files,
listed by the book and chapter they go with, and practicing one (assessment_page.py).

A window of its own rather than a dialog: a practice session lasts up to an hour, beside
the notes or instead of them. It has no parent, so it doesn't stay above the notes; the
main window closes it when it closes, so the app still quits as one, with the drafts on
disk first.

Files are read and written by helpers.WORKER, never on the main loop: listing, importing
(read, parse, look for the same report, then write), moving one to the Trash and back,
and the practice page's saves."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .. import assessments as store, library
from ..assessment_txt import Report
from ..spell import Speller
from .assessment_page import PracticePage
from .helpers import WORKER, assessments_root, notes_root, restore_from_trash, trash_path

PRACTICE_ACTIONS = ("prev-question", "next-question", "sidebar", "finish", "attach", "attempts", "highlights")


class AssessmentRow(Adw.ActionRow):
    """An assessment in the list, and the chapter its link found (or None)."""

    def __init__(self, assessment, chapter, **props):
        super().__init__(**props)
        self.assessment, self.chapter = assessment, chapter


@dataclass
class Import:
    """A file read for importing, and what to ask about it."""
    path: Path
    data: bytes
    report: Report
    duplicate: store.Assessment | None  # the assessment it is another download of
    books: list                         # library.scan()'s, to pick its chapter from
    chapter: library.Chapter | None     # the chapter to offer: its title's, or the one it was imported for
    for_chapter: bool = False           # imported for that chapter (from the chapter list): not asked


class AssessmentsWindow(Adw.ApplicationWindow):
    __gtype_name__ = "NtzAssessmentsWindow"

    def __init__(self, app, on_changed=None, on_closed=None, spell_on=True, spell_lang=None):
        """on_changed() after an import or a changed link (the main window's chapter buttons
        and menus open an assessment's chapter); on_closed(window) once it is closed.
        spell_on: the main window's Check Spelling (set_spelling follows it); spell_lang: the
        language last chosen there, for a chapter whose language can't be told."""
        super().__init__(application=app, title="Assessments", default_width=1040, default_height=780)
        self.set_size_request(400, 360)
        self.on_changed, self.on_closed = on_changed, on_closed
        # A speller of its own: the notes' follows the chapter open there, the answers'
        # the assessment's chapter (PracticePage.set_chapter).
        self.speller = Speller()
        self.languages = self.speller.languages()
        self.spell_on, self.spell_lang = spell_on and self.speller.available, spell_lang
        self.page = None        # the practice page, while one is open
        self.released = False
        self._discard = False   # close without saving: the user said so, after a save failed
        self._groups = []       # the list page's groups, to take away on the next listing
        self._titles = {}       # the listed assessments' titles by folder, for the trash buttons' toasts
        self._handlers = []

        self.toasts = Adw.ToastOverlay()
        self.nav = Adw.NavigationView(pop_on_escape=False)
        self.nav.add(self._build_list_page())
        self._handlers.append((self.nav, self.nav.connect("popped", _popped)))
        self._handlers.append((self.nav, self.nav.connect("notify::visible-page", _page_changed)))
        self.toasts.set_child(self.nav)
        self.set_content(self.toasts)
        self._add_actions()
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", _dropped)
        self.toasts.add_controller(drop)
        # Ctrl+PgUp/PgDn go to the previous or next question, before the answer's text view
        # can take them (it would move the cursor by a page).
        keys = Gtk.ShortcutController(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        for trigger, action in (("<Control>Page_Up", "win.prev-question"), ("<Control>Page_Down", "win.next-question")):
            keys.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(trigger), Gtk.NamedAction.new(action)))
        self.add_controller(keys)
        self._handlers.append((self, self.connect("close-request", _close_request)))
        self._handlers.append((self, self.connect("notify::is-active", _activated)))
        self.update_actions()
        self.refresh()

    # -- building ---------------------------------------------------------------------

    def _build_list_page(self):
        tv = Adw.ToolbarView()
        header = Adw.HeaderBar()
        imp = Gtk.Button(action_name="win.import", tooltip_text="Import a report downloaded from TopCoding as .txt")
        imp.set_child(Adw.ButtonContent(icon_name="document-open-symbolic", label="Import Report…"))
        header.pack_start(imp)
        tv.add_top_bar(header)
        self.list_stack = Gtk.Stack()
        self.list_stack.add_named(Adw.Spinner(), "loading")
        empty = Adw.StatusPage(icon_name="x-office-document-symbolic", title="No Assessments Yet",
                               description="On a TopCoding assessment report, choose Download .txt, then import "
                                           "the file here or drop it on this window.")
        empty.set_child(Gtk.Button(label="Import Report…", action_name="win.import", halign=Gtk.Align.CENTER,
                                   css_classes=["pill", "suggested-action"]))
        self.list_stack.add_named(empty, "empty")
        self.prefs = Adw.PreferencesPage()
        self.list_stack.add_named(self.prefs, "list")
        tv.set_content(self.list_stack)
        return Adw.NavigationPage(title="Assessments", tag="list", child=tv)

    def _add_actions(self):
        for name, cb in (("import", lambda *_: self.choose_file()),
                         ("prev-question", lambda *_: self.page.step(-1)),
                         ("next-question", lambda *_: self.page.step(1)),
                         ("finish", lambda *_: self.page.finish_attempt()),
                         ("attach", lambda *_: self.ask_chapter()),
                         ("attempts", lambda *_: self.page.show_attempts())):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", cb)
            self.add_action(a)
        # F9 (the app's key for win.sidebar): the question list
        a = Gio.SimpleAction.new_stateful("sidebar", None, GLib.Variant.new_boolean(True))
        a.connect("activate", lambda act, _p: self.page.show_list(not act.get_state().get_boolean()))
        self.add_action(a)
        # The original scores in TopCoding's colors: on each time the window opens (not saved)
        a = Gio.SimpleAction.new_stateful("highlights", None, GLib.Variant.new_boolean(True))
        a.connect("activate", lambda act, _p: self.set_highlights(not act.get_state().get_boolean()))
        self.add_action(a)
        # A row's trash button: its folder to the Trash
        a = Gio.SimpleAction.new("remove", GLib.VariantType.new("s"))
        a.connect("activate", lambda _a, folder: self.remove(Path(folder.get_string())))
        self.add_action(a)

    @property
    def highlights(self):
        """Whether the original scores are shown in TopCoding's colors (win.highlights)."""
        a = self.lookup_action("highlights")
        return a is None or a.get_state().get_boolean()

    def set_highlights(self, on):
        self.lookup_action("highlights").set_state(GLib.Variant.new_boolean(on))
        if self.page is not None:
            self.page.show_highlights()

    def set_spelling(self, on, lang=None):
        """The main window's Check Spelling was switched (on), or a language chosen there
        (lang: the fallback for a chapter whose language can't be told)."""
        self.spell_on = on and self.speller.available
        if lang is not None:
            self.spell_lang = lang
        if self.page is not None:
            self.page.spelling_changed()

    def language_chosen(self, path, lang):
        """A spelling language was chosen in the main window for the chapter at path: the
        answers to its assessment are checked in it too."""
        self.spell_lang = lang
        if self.page is not None and path is not None and self.page.goes_with(Path(path)):
            self.page.set_language(lang)

    def update_actions(self):
        """The practice page's actions work while it is shown and its draft was read."""
        if self.released:
            return
        page = self.page if self.page is not None and self.nav.get_visible_page() is self.page else None
        ready = page is not None and page.attempt is not None
        for name in PRACTICE_ACTIONS:
            self.lookup_action(name).set_enabled(ready)
        if ready and page.current in page.numbers:  # no previous question before the first, nor next after the last
            i = page.numbers.index(page.current)
            self.lookup_action("prev-question").set_enabled(i > 0)
            self.lookup_action("next-question").set_enabled(i + 1 < len(page.numbers))
        self.lookup_action("finish").set_enabled(ready and page.can_finish())
        if page is not None:
            self.lookup_action("sidebar").set_state(GLib.Variant.new_boolean(page.list_pane.get_visible()))

    def toast(self, msg, button=None, callback=None):
        if self.released:
            return None
        t = Adw.Toast(title=msg, timeout=6 if button else 4, use_markup=False)  # titles and errors, not markup (CR8)
        if button:
            t.set_button_label(button)
            t.set_priority(Adw.ToastPriority.HIGH)  # an Undo shows at once, not after the toasts before it
            t.connect("button-clicked", lambda *_: callback())
        self.toasts.add_toast(t)
        return t

    # -- the list ---------------------------------------------------------------------

    def refresh(self):
        """List the assessments again (in the background)."""
        WORKER.run(lambda root=assessments_root(), notes=notes_root(): _listing(root, notes),
                   done=self._listed, failed=self._list_failed)

    def _listed(self, result):
        if self.released:
            return
        resolved, broken = result
        for g in self._groups:
            self.prefs.remove(g)
        self._groups = []
        self._titles = {a.folder: a.report.title for a, _ch in resolved} | {f: f.name for f, _r in broken}
        books = {}
        for a, ch in resolved:
            books.setdefault(ch.path.parent.name if ch is not None else None, []).append((a, ch))
        for name in sorted((b for b in books if b is not None), key=str.casefold) + ([None] if None in books else []):
            group = Adw.PreferencesGroup(title=GLib.markup_escape_text(name) if name else "Not attached",
                                         description=None if name else "Attach one to its chapter from its menu")
            rows = sorted(books[name], key=lambda t: (t[1].number or 0) if t[1] is not None else 0)
            for a, ch in rows:
                row = AssessmentRow(a, ch, title=a.report.title, subtitle=_row_subtitle(a, ch),
                                    activatable=True, use_markup=False)
                row.add_suffix(_trash_button(a.folder, a.report.title))
                row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
                row.connect("activated", _row_activated)
                group.add(row)
            self._add_group(group)
        if broken:
            group = Adw.PreferencesGroup(title="Couldn't Be Read",
                                         description="These folders in the assessments folder aren't assessments "
                                                     "this version can read.")
            for folder, reason in broken:
                row = Adw.ActionRow(title=folder.name, subtitle=reason, use_markup=False)
                row.add_suffix(_trash_button(folder, folder.name))
                group.add(row)
            self._add_group(group)
        self.list_stack.set_visible_child_name("list" if self._groups else "empty")

    def _add_group(self, group):
        self.prefs.add(group)
        self._groups.append(group)

    def _list_failed(self, error):
        if self.released:
            return
        self.list_stack.set_visible_child_name("empty")
        self.toast(f"Couldn't list the assessments: {getattr(error, 'strerror', None) or error}")

    def remove(self, folder):
        """A row's trash button: move the assessment's folder, its report, draft and
        attempts, to the Trash, with Undo on the toast."""
        if self.page is not None and self.page.a.folder == folder:
            return  # the list is shown only once its page has gone
        title = self._titles.get(folder, folder.name)
        WORKER.run(lambda: trash_path(folder), done=lambda _r: self._removed(folder, title),
                   failed=lambda e: self.released or self.toast(
                       f"Couldn't move “{title}” to Trash: {getattr(e, 'message', None) or getattr(e, 'strerror', None) or e}"))

    def _removed(self, folder, title):
        if self.released:
            return
        self.toast(f"“{title}” moved to Trash", "Undo", lambda: self.restore(folder, title))
        self.refresh()
        self.assessments_changed()

    def restore(self, folder, title):
        """Undo on the toast: the folder back from the Trash."""
        WORKER.run(lambda: _untrash(folder), done=lambda result: self._restored(folder, title, result),
                   failed=lambda e: self.released or self.toast(
                       f"Couldn't put “{title}” back: {getattr(e, 'strerror', None) or e}"))

    def _restored(self, folder, title, result):
        if self.released:
            return
        if result == "exists":
            self.toast(f"{folder.name} exists again, so “{title}” was left in the Trash")
        elif result == "missing":
            self.toast(f"“{title}” wasn't found in the Trash")
        self.refresh()
        self.assessments_changed()

    def assessments_changed(self):
        """An import, a Replace, a finished attempt or a new link: the list and the main
        window's chapter buttons and menus show it."""
        if self.on_changed is not None:
            self.on_changed()

    # -- practicing -------------------------------------------------------------------

    def open_assessment(self, assessment, chapter):
        """Show the practice page of an assessment (chapter: the chapter it goes with, or None)."""
        if self.page is not None and self.page.a.folder == assessment.folder:
            self.nav.pop_to_page(self.page)
            return
        if self.page is not None:
            self.nav.pop_to_tag("list")  # the old page is saved and let go when it pops
        self.page = PracticePage(self, assessment, _chapter_label(chapter), chapter)
        self.nav.push(self.page)
        self.update_actions()

    def open_folder(self, folder):
        """Show the practice page of the assessment in folder (from the main window)."""
        WORKER.run(lambda notes=notes_root(): _one(Path(folder), notes),
                   done=lambda t: self.released or self.open_assessment(*t),
                   failed=lambda e: self.toast(f"Couldn't open the assessment: {getattr(e, 'strerror', None) or e}"))

    def _page_popped(self, page):
        if isinstance(page, PracticePage) and not page.released:
            page.flush()
            page.release()
        if page is self.page:
            self.page = None
        self.update_actions()
        self.refresh()

    # -- importing --------------------------------------------------------------------

    def choose_file(self, chapter=None):
        """Import Report…: pick a .txt file. chapter: the chapter it is imported for (its
        button or menu in the chapter list), which it then goes with without asking."""
        fd = Gtk.FileDialog(title="Import Assessment Report", modal=True)
        downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if downloads:
            fd.set_initial_folder(Gio.File.new_for_path(downloads))
        txt = Gtk.FileFilter(name="TopCoding reports (*.txt)")
        txt.add_pattern("*.txt")
        txt.add_pattern("*.TXT")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(txt)
        fd.set_filters(filters)
        fd.set_default_filter(txt)

        def done(dialog, res):
            try:
                gf = dialog.open_finish(res)
            except GLib.Error:
                return  # dismissed
            if gf is not None and not self.released:
                self.import_file(gf, chapter)

        fd.open(self, None, done)

    def import_file(self, gfile, chapter=None):
        """Read the file, then ask what to do with it: its chapter (unless it is imported
        for one: chapter, as in choose_file), or whether to replace the report it is
        another download of. Nothing is written before that."""
        path = gfile.get_path()
        if path is None:  # not a file on this computer (CR27)
            self.toast(f"{gfile.get_basename() or gfile.get_uri()} isn't on this computer, so it can't be imported")
            return
        path = Path(path)
        WORKER.run(lambda root=assessments_root(), notes=notes_root(): _prepare(path, root, notes, chapter),
                   done=self._ask_import, failed=lambda e: self._import_failed(path, e))

    def _ask_import(self, imp):
        if self.released:
            return
        if imp.duplicate is not None:
            self._ask_replace(imp)
            return
        if imp.for_chapter:
            self._import(imp, imp.chapter)
            return
        r = imp.report
        body = (f"{len(r.questions)} question{'s' if len(r.questions) != 1 else ''}"
                + (f", completed {_when(r)}" if _when(r) else "")
                + (f", scored {_final(r)}." if r.final_result is not None else ", not graded yet.")
                + " Which chapter does it go with?")
        chapter_dialog(self, f"Import “{r.title}”", body, imp.books, imp.chapter, "Import",
                       lambda ch: self._import(imp, ch))

    def _import(self, imp, chapter):
        link = store.link_for(chapter.path, notes_root()) if chapter is not None else None
        WORKER.run(lambda root=assessments_root(): store.import_report(root, imp.data, imp.report, imp.path.name, link),
                   done=lambda a: self._imported(a, chapter, f"Imported “{a.report.title}”"),
                   failed=lambda e: self._import_failed(imp.path, e))

    def _ask_replace(self, imp):
        old, new = imp.duplicate.report, imp.report
        body = f"“{old.title}”" + (f", completed {_when(old)}," if _when(old) else "") + " is already imported."
        if new.graded and not old.graded:
            body += " This file has its scores and feedback: Replace adds them."
        elif old.graded and not new.graded:
            body += " That one has scores and feedback, and this file has none: Replace would take them away."
        else:
            body += " Replace puts this file in its place."
        body += " Your practice drafts and earlier attempts stay either way."
        dlg = Adw.AlertDialog(heading="Report Already Imported", body=body)
        dlg.add_response("skip", "Skip")
        dlg.add_response("replace", "Replace")
        if new.graded and not old.graded:
            dlg.set_response_appearance("replace", Adw.ResponseAppearance.SUGGESTED)
        elif old.graded and not new.graded:
            dlg.set_response_appearance("replace", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("skip")
        dlg.set_close_response("skip")
        dlg.connect("response", lambda _d, response: self._replace(imp) if response == "replace"
                    else self.toast(f"Skipped: “{old.title}” was already imported"))
        dlg.present(self)

    def _replace(self, imp):
        if self.page is not None and self.page.a.folder == imp.duplicate.folder:
            self.page.flush()  # (written before the Replace: the worker runs them in turn)
        WORKER.run(lambda notes=notes_root(): _replaced(imp, notes),
                   done=lambda t: self._imported(*t, f"Replaced “{t[0].report.title}”"
                                                 + (": its scores and feedback are in" if t[0].report.graded and
                                                    not imp.duplicate.report.graded else "")),
                   failed=lambda e: self._import_failed(imp.path, e))

    def _imported(self, assessment, chapter, message):
        if self.released:
            return
        self.toast(message)
        self.assessments_changed()
        if self.page is not None and self.page.a.folder == assessment.folder:
            self.page.set_report(assessment, _chapter_label(chapter))
            self.nav.pop_to_page(self.page)
        else:
            self.open_assessment(assessment, chapter)

    def _import_failed(self, path, error):
        if self.released:
            return
        if isinstance(error, OSError):
            body = f"{path.name} can't be read: {error.strerror or error}."
        else:  # assessment_txt.ReportError: says where in the file
            body = f"{path.name}: {error}."
        dlg = Adw.AlertDialog(heading="Couldn't Import the Report", body=body + " Nothing was imported.")
        dlg.add_response("ok", "OK")
        dlg.present(self)

    def drop_files(self, files):
        """Files dropped on the window: the first is imported."""
        if not files:
            return False
        if len(files) > 1:
            self.toast("One report at a time: importing the first")
        self.import_file(files[0])
        return True

    # -- the chapter ------------------------------------------------------------------

    def ask_chapter(self):
        """Attach to Chapter…: the chapter the open assessment goes with."""
        page = self.page
        if page is None:
            return
        WORKER.run(lambda notes=notes_root(), a=page.a: _chapters(a, notes),
                   done=lambda t: self._ask_chapter(page, *t),
                   failed=lambda e: self.toast(f"Couldn't list the chapters: {getattr(e, 'strerror', None) or e}"))

    def _ask_chapter(self, page, books, current):
        if self.released or page is not self.page:
            return
        chapter_dialog(self, "Attach to Chapter", f"Which chapter does “{page.a.report.title}” go with?",
                       books, current, "Attach", lambda ch: self._attach(page, ch))

    def _attach(self, page, chapter):
        link = store.link_for(chapter.path, notes_root()) if chapter is not None else None
        WORKER.run(lambda a=page.a: store.set_chapter(a, link),
                   done=lambda a: self._attached(page, a, chapter),
                   failed=lambda e: self.toast(f"Couldn't attach it: {getattr(e, 'strerror', None) or e}"))

    def _attached(self, page, assessment, chapter):
        if self.released:
            return
        if page is self.page:
            page.a.chapter = assessment.chapter
            page.title.set_subtitle(_chapter_label(chapter))
            page.set_chapter(chapter)
        self.toast(f"Attached to “{chapter.label}”" if chapter is not None else "Not attached to a chapter now")
        self.assessments_changed()

    # -- closing ----------------------------------------------------------------------

    def close_request(self):
        """Save the practice page's draft before the window goes. If it can't be saved,
        ask whether to close anyway."""
        if self.page is not None and not self._discard:
            try:
                self.page.flush(wait=True)
            except OSError as e:
                self._ask_close_anyway(e)
                return True
        else:
            WORKER.wait()
        self._release()
        return False

    def _ask_close_anyway(self, error):
        dlg = Adw.AlertDialog(heading="Your Answers Weren't Saved",
                              body=f"The draft couldn't be written: {error.strerror or error}. Close anyway and lose "
                                   "the latest changes, or keep the window open to try again?")
        dlg.add_response("keep", "Keep Open")
        dlg.add_response("close", "Close Anyway")
        dlg.set_response_appearance("close", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("keep")
        dlg.set_close_response("keep")

        def answered(_d, response):
            if response == "close":
                self._discard = True
                self.close()
        dlg.connect("response", answered)
        dlg.present(self)

    def _release(self):
        """The window is going: let go of its content, whose handlers hold it (R29), as
        DrawingWindow does."""
        if self.released:
            return
        self.released = True
        if self.page is not None:
            self.page.release()
            self.page = None
        for obj, handler in self._handlers:
            obj.disconnect(handler)
        self._handlers = []
        for name in self.list_actions():
            self.remove_action(name)
        self.set_focus(None)
        self.set_content(None)
        self.toasts = self.nav = self.list_stack = self.prefs = None
        self._groups = []
        on_closed, self.on_changed, self.on_closed = self.on_closed, None, None
        if on_closed is not None:
            on_closed(self)


def chapter_dialog(parent, heading, body, books, selected, apply_label, on_apply):
    """Ask which chapter (of books, library.scan()'s) something goes with, selected
    first; on_apply(the chapter, or None for none)."""
    chapters = [ch for book in books for ch in book.chapters]
    labels = ["Not attached"] + [f"{ch.path.parent.name} · {ch.path.stem}" for ch in chapters]
    # the choice as the row's subtitle: the row's whole width, where its end would cut the name short
    combo = Adw.ComboRow(title="Chapter", model=Gtk.StringList.new(labels), use_markup=False, enable_search=True,
                         use_subtitle=True, expression=Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
    at = next((i for i, ch in enumerate(chapters) if selected is not None and library.same_file(ch.path, selected.path)),
              None)
    combo.set_selected(0 if at is None else at + 1)
    box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
    box.append(combo)
    dlg = Adw.AlertDialog(heading=heading, body=body)
    dlg.set_extra_child(box)
    dlg.add_response("cancel", "Cancel")
    dlg.add_response("apply", apply_label)
    dlg.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
    dlg.set_default_response("apply")
    dlg.set_close_response("cancel")
    dlg.connect("response", lambda _d, response: response == "apply" and on_apply(
        chapters[combo.get_selected() - 1] if combo.get_selected() > 0 else None))
    dlg.present(parent)
    return dlg


# -- jobs for the worker's thread (no GTK) -------------------------------------------------

def _listing(root, notes):
    found, broken = store.list_all(root)
    return store.resolve_links(found, library.scan(notes), notes), broken


def _one(folder, notes):
    a = store.load(folder)
    return a, store.resolve(a.chapter, library.scan(notes), notes)


def _prepare(path, root, notes, chapter=None):
    data, report = store.read_import(path)
    found, _broken = store.list_all(root)
    books = library.scan(notes)
    duplicate = store.find_duplicate(found, report)
    offered = chapter if chapter is not None else store.suggest(report.title, books)
    return Import(path, data, report, duplicate, books, offered, for_chapter=chapter is not None)


def _replaced(imp, notes):
    a = store.replace_report(imp.duplicate, imp.data, imp.report, imp.path.name)
    return a, store.resolve(a.chapter, library.scan(notes), notes)


def _untrash(folder):
    """'restored', 'exists' (something is in its place again) or 'missing' (not in the Trash)."""
    if folder.exists():
        return "exists"
    return "restored" if restore_from_trash(folder) else "missing"


def _chapters(a, notes):
    books = library.scan(notes)
    return books, store.resolve(a.chapter, books, notes)


# -- handlers that find their window when the event comes (CR18) ---------------------------

def _close_request(win):
    return win.close_request()


def _activated(win, _pspec):
    if win.is_active() and not win.released and win.page is None:
        win.refresh()  # a sync tool, or the main window, may have changed something


def _popped(nav, page):
    win = nav.get_root()
    if isinstance(win, AssessmentsWindow):
        win._page_popped(page)


def _page_changed(nav, _pspec):
    win = nav.get_root()
    if isinstance(win, AssessmentsWindow):
        win.update_actions()


def _row_activated(row):
    win = row.get_root()
    if isinstance(win, AssessmentsWindow):
        win.open_assessment(row.assessment, row.chapter)


def _dropped(target, value, _x, _y):
    win = target.get_widget().get_root()
    return isinstance(win, AssessmentsWindow) and win.drop_files(value.get_files())


def _trash_button(folder, title):
    """A row's button that moves its assessment (folder) to the Trash."""
    button = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Move to Trash", valign=Gtk.Align.CENTER,
                        css_classes=["flat"], action_name="win.remove",
                        action_target=GLib.Variant.new_string(str(folder)))
    button.update_property([Gtk.AccessibleProperty.LABEL], [f"Move “{title}” to Trash"])
    return button


# -- text ---------------------------------------------------------------------------------

def _chapter_label(chapter):
    if chapter is None:
        return "Not attached to a chapter"
    number = f"Chapter {chapter.number}" if chapter.number is not None else chapter.label
    return f"{chapter.path.parent.name} · {number}"


def _when(report):
    return f"{report.completed_at:%Y-%m-%d %H:%M}" if report.completed_at else report.completed


def _final(report):
    return f"{report.final_result}" + (f" ({report.final_percent}%)" if report.final_percent else "")


def _row_subtitle(a, chapter):
    """'Chapter 3 · 2026-11-23 19:05 · 7.10 / 19 (37.4%) · 2 attempts, one in progress'."""
    r = a.report
    parts = []
    if chapter is not None and chapter.number is not None:
        parts.append(f"Chapter {chapter.number}")
    elif chapter is None and a.chapter is not None:
        parts.append(f"its chapter “{a.chapter.title or a.chapter.file}” is gone")
    if _when(r):
        parts.append(_when(r))
    parts.append(_final(r) if r.final_result is not None else "not graded")
    attempts = f"{a.attempts} attempt{'s' if a.attempts != 1 else ''}" if a.attempts else "no attempts yet"
    parts.append(attempts + (", one in progress" if a.has_draft else ""))
    return " · ".join(parts)
