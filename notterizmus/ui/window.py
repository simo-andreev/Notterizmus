from __future__ import annotations

import json
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .. import APP_ID, APP_NAME, VERSION, backups, guide, library, paths, state
from ..export import to_plain
from ..layout import layout
from ..model import Document, chapter_filename
from ..rules import Rules, config_dir, user_rules_path
from ..spell import Speller, guess_language
from . import command_search
from .findbar import FindBar
from .outline import OutlineEditor
from .outline_clipboard import export_formats
from .sidebar import ChapterSidebar

RULES_TEMPLATE = Path(__file__).resolve().parent.parent / "rules.example.toml"
SIDEBAR_DEFAULT, SIDEBAR_MIN, SIDEBAR_MAX = 260, 180, 520  # chapter list width, px
TEXT_ROOM = 20  # spare px beside the text column's minimum width
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, TEXT_PT = 60, 250, 10, 11  # chapter text zoom, % and base size
DOC_ACTIONS = ("copy", "insert-table", "insert-drawing", "show-plain", "save", "find", "replace", "find-next", "find-prev")


def notes_root():
    return paths.notes_root(glib_documents=GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS))


def load_state():
    return state.load()


def save_state(settings):
    try:
        state.save(settings)
    except OSError:
        pass  # not remembered this time; nothing else depends on it


class Window(Adw.ApplicationWindow):
    __gtype_name__ = "NtzWindow"

    def __init__(self, app):
        super().__init__(application=app, default_width=1100, default_height=800, title=APP_NAME)
        self.rules = Rules.load()
        self.state = load_state()
        self.doc = None
        self._save_src = None
        self._disk_dialog = None  # asking what to do about a chapter changed on disk (CR10)
        self.speller = Speller()
        self.languages = self.speller.languages()

        self.toasts = Adw.ToastOverlay()
        tv = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.wtitle = Adw.WindowTitle(title=APP_NAME, subtitle="")
        header.set_title_widget(self.wtitle)
        header.pack_start(Gtk.ToggleButton(icon_name="sidebar-show-symbolic", tooltip_text="Chapters (F9)",
                                           action_name="win.sidebar"))
        header.pack_start(Gtk.Button(icon_name="document-new-symbolic", tooltip_text="New chapter (Ctrl+N)",
                                     action_name="win.new"))
        header.pack_start(Gtk.Button(icon_name="document-open-symbolic", tooltip_text="Open chapter (Ctrl+O)",
                                     action_name="win.open"))
        menu = Gio.Menu()
        s1 = Gio.Menu()
        s1.append("Insert Table", "win.insert-table")
        s1.append("Insert Drawing", "win.insert-drawing")
        s1.append("Show Plain Text", "win.show-plain")
        s2 = Gio.Menu()
        s2.append("Edit Formatting Rules", "win.edit-rules")
        s2.append("Reload Formatting Rules", "win.reload-rules")
        s2.append("Open Notes Folder", "win.open-folder")
        s0 = Gio.Menu()
        s0.append("Chapter Properties…", "win.rename")
        s0.append("Earlier Versions…", "win.versions")
        spell = Gio.Menu()
        spell.append("Check Spelling", "win.spell")
        langs = Gio.Menu()
        for tag in self.languages:
            item = Gio.MenuItem.new(Speller.language_name(tag), None)
            item.set_action_and_target_value("win.spell-lang", GLib.Variant.new_string(tag))
            langs.append_item(item)
        spell.append_section("Language", langs)
        self.spell_menu = spell
        s1.append_submenu("Spelling", spell)
        s3 = Gio.Menu()
        s3.append("Search Commands…", "win.commands")
        s3.append("Getting Started", "win.guide")
        s3.append("Keyboard Shortcuts", "win.shortcuts")
        s3.append(f"About {APP_NAME}", "win.about")
        zoom_item = Gio.MenuItem.new(None, None)
        zoom_item.set_attribute_value("custom", GLib.Variant.new_string("zoom"))
        sz = Gio.Menu()
        sz.append_item(zoom_item)
        for s in (sz, s0, s1, s2, s3):
            menu.append_section(None, s)
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Menu")
        # "−  100%  +" row at the top of the menu, as in other GNOME apps
        zoom_row = Gtk.Box(spacing=0, homogeneous=True, margin_start=12, margin_end=12)
        zoom_row.add_css_class("linked")
        zoom_row.append(Gtk.Button(icon_name="zoom-out-symbolic", tooltip_text="Smaller text (Ctrl+-)",
                                   action_name="win.zoom-out", css_classes=["flat"]))
        self.zoom_label = Gtk.Button(label="100%", tooltip_text="Normal size (Ctrl+0)",
                                     action_name="win.zoom-reset", css_classes=["flat", "numeric"])
        zoom_row.append(self.zoom_label)
        zoom_row.append(Gtk.Button(icon_name="zoom-in-symbolic", tooltip_text="Larger text (Ctrl+=)",
                                   action_name="win.zoom-in", css_classes=["flat"]))
        menu_btn.get_popover().add_child(zoom_row, "zoom")
        header.pack_end(menu_btn)
        copy = Gtk.Button(tooltip_text="Copy formatted notes, then paste into TopCoding (Ctrl+Shift+C)",
                          action_name="win.copy")
        copy.set_child(Adw.ButtonContent(icon_name="edit-copy-symbolic", label="Copy for TopCoding"))
        copy.add_css_class("suggested-action")
        header.pack_end(copy)
        self.lang_btn = Gtk.MenuButton(menu_model=spell, tooltip_text="Spell-check language",
                                       visible=bool(self.languages))
        self.lang_btn.add_css_class("flat")
        header.pack_end(self.lang_btn)
        tv.add_top_bar(header)

        self.editor = OutlineEditor(self.rules)
        self.editor.spell_menu = spell
        self.editor.connect("changed", lambda *_: (self._schedule_save(), self.findbar.schedule_refresh()))
        self.editor.connect("message", lambda _e, msg: self.toast(msg))
        self.editor.connect("toast", lambda _e, msg, button, cb: self._editor_toast(msg, button, cb))
        self.findbar = FindBar(self.editor, self.toast)
        tv.add_top_bar(self.findbar)
        self.editor.on_escape = lambda: self.findbar.get_search_mode() and (
            self.findbar.close(focus_match=False) or True)
        # Zoom changes only the chapter text, through one app-wide provider above style.css
        # (one per window would pile up on the display, and a closed window's would win).
        self._zoom_css = _zoom_provider(self.get_display())
        self._zoom, self._zoom_toast, self._scroll_zoom = 100, None, 0.0
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL,
                                           propagation_phase=Gtk.PropagationPhase.CAPTURE)
        scroll.connect("scroll", lambda c, _dx, dy: self.scroll_zoom(
            bool(c.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK), dy))
        self.editor.add_controller(scroll)

        empty = Adw.StatusPage(icon_name=APP_ID, title="No Chapter Open",
                               description="Create a chapter for a book or open an existing one. "
                                           "New here? Getting Started shows the controls.")
        bb = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        nb = Gtk.Button(label="New Chapter", action_name="win.new", css_classes=["pill", "suggested-action"])
        ob = Gtk.Button(label="Open…", action_name="win.open", css_classes=["pill"])
        gb = Gtk.Button(label="Getting Started", action_name="win.guide", css_classes=["pill"])
        bb.append(nb)
        bb.append(ob)
        bb.append(gb)
        empty.set_child(bb)

        self.stack = Gtk.Stack()
        self.stack.add_named(empty, "empty")
        self.stack.add_named(self.editor, "editor")
        tv.set_content(self.stack)

        # Chapter list on the left; it becomes an overlay when the window is narrow.
        self.sidebar = ChapterSidebar()
        self.sidebar.connect("open-chapter", lambda _s, path: self._open_from_sidebar(path))
        self.sidebar.on_reorder = self._reorder_chapters
        self.sidebar.popup = self.editor.popup_menu
        self.split = Adw.OverlaySplitView(sidebar=self.sidebar, content=tv)
        # Collapse when the text column doesn't fit beside the list; set_sidebar_width
        # keeps this condition in step with the list's width.
        self._collapse = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 900px"))
        self._collapse.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(self._collapse)
        self.set_size_request(640, 400)
        # The split view has no resize handle: a thin strip over the edge does it. The
        # drag is tracked on the overlay, which doesn't move while the handle does.
        self.handle = Gtk.Box(css_classes=["sidebar-handle"],
                              tooltip_text="Drag to resize the chapter list · double-click for the default width")
        self.handle.set_cursor_from_name("col-resize")
        reset = Gtk.GestureClick()
        reset.connect("pressed", lambda _g, n, *_: n == 2 and self.set_sidebar_width(SIDEBAR_DEFAULT, save=True))
        self.handle.add_controller(reset)
        overlay = Gtk.Overlay(child=self.split)
        overlay.add_overlay(self.handle)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._handle_drag_begin)
        drag.connect("drag-update", self._handle_drag_update)
        drag.connect("drag-end", self._handle_drag_end)
        overlay.add_controller(drag)
        self._overlay = overlay
        self.toasts.set_child(overlay)
        self.set_content(self.toasts)
        self._sidebar_w = SIDEBAR_DEFAULT
        self._drag_from = None
        self.set_sidebar_width(self.state.get("sidebar_width", SIDEBAR_DEFAULT))
        self.split.connect("notify::collapsed", lambda *_: self._update_handle())

        for name, cb in (("new", self.on_new), ("open", self.on_open), ("save", lambda *_: self.save()),
                         ("copy", self.on_copy), ("insert-table", lambda *_: self.editor.insert_table()),
                         ("insert-drawing", lambda *_: self.editor.insert_drawing()),
                         ("show-plain", self.on_show_plain), ("edit-rules", self.on_edit_rules),
                         ("reload-rules", self.on_reload_rules), ("open-folder", self.on_open_folder),
                         ("guide", self.on_guide), ("shortcuts", self.on_shortcuts), ("about", self.on_about),
                         ("prev-chapter", lambda *_: self.on_chapter_step(-1)),
                         ("next-chapter", lambda *_: self.on_chapter_step(1)),
                         ("rename", self.on_rename), ("versions", self.on_versions),
                         ("commands", self.on_commands),
                         ("find", lambda *_: self.on_find()), ("replace", lambda *_: self.on_find(replace=True)),
                         ("zoom-in", lambda *_: self.set_zoom(self._zoom + ZOOM_STEP)),
                         ("zoom-out", lambda *_: self.set_zoom(self._zoom - ZOOM_STEP)),
                         ("zoom-reset", lambda *_: self.set_zoom(100)),
                         ("find-next", lambda *_: self.findbar.step(1)),
                         ("find-prev", lambda *_: self.findbar.step(-1))):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", cb)
            self.add_action(a)
        for name, cb in (("chapter-props", self.on_chapter_props), ("book-rename", self.on_book_rename),
                         ("chapter-up", lambda path: self.on_chapter_move(path, -1)),
                         ("chapter-down", lambda path: self.on_chapter_move(path, 1)),
                         ("chapter-trash", self.on_chapter_trash)):
            a = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            a.connect("activate", lambda _a, p, f=cb: f(p.get_string()))
            self.add_action(a)
        for act in DOC_ACTIONS:
            self.lookup_action(act).set_enabled(False)

        show = bool(self.state.get("sidebar", True))
        a = Gio.SimpleAction.new_stateful("sidebar", None, GLib.Variant.new_boolean(show))
        a.connect("activate", lambda act, _p: self.split.set_show_sidebar(not act.get_state().get_boolean()))
        self.add_action(a)
        self.split.set_show_sidebar(show)
        self.split.connect("notify::show-sidebar", self._on_sidebar_shown)
        self.connect("notify::is-active", lambda *_: self.is_active() and self._reload_sidebar())
        self._reload_sidebar()

        spell_on = bool(self.state.get("spell", True)) and self.speller.available
        a = Gio.SimpleAction.new_stateful("spell", None, GLib.Variant.new_boolean(spell_on))
        a.connect("activate", self._on_spell_toggle)
        a.set_enabled(self.speller.available)
        self.add_action(a)
        default_lang = self._pick_lang(self.state.get("spell_lang"))
        a = Gio.SimpleAction.new_stateful("spell-lang", GLib.VariantType.new("s"),
                                          GLib.Variant.new_string(default_lang or ""))
        a.connect("activate", self._on_spell_lang)
        a.set_enabled(self.speller.available)
        self.add_action(a)
        self._apply_spelling(default_lang)

        self.set_zoom(self.state.get("zoom", 100), save=False, announce=False)
        self.connect("close-request", self._on_close)
        if self.rules.error:
            GLib.idle_add(lambda: (self.toast("Rules file error — using defaults"), False)[1])

        last = self.state.get("last_file")
        if last and Path(last).exists():
            self.open_path(last)
        self._offer_stranded()

    # -- helpers ------------------------------------------------------------------

    def toast(self, msg, button=None, callback=None):
        t = Adw.Toast(title=msg, timeout=6 if button else 3, use_markup=False)  # titles and errors, not markup (CR8)
        if button:
            t.set_button_label(button)
            t.connect("button-clicked", lambda *_: callback())
        self.toasts.add_toast(t)
        return t

    def _editor_toast(self, msg, button, callback):
        """A toast about what the editor just did. Its button acts on that, so the toast
        goes as soon as the chapter changes again (CR3)."""
        t = self.toast(msg, button, callback)
        if t is None or not button:  # (the UI tests replace toast())
            return
        handler = self.editor.connect("changed", lambda *_: t.dismiss())

        def stop_watching(*_):
            nonlocal handler
            if handler:
                self.editor.disconnect(handler)
                handler = 0

        t.connect("dismissed", stop_watching)

    # -- spelling ---------------------------------------------------------------------

    def _pick_lang(self, wanted, text=""):
        if wanted in self.languages:
            return wanted
        if any(c.isalpha() for c in text):
            g = guess_language(text, self.languages)
            if g:
                return g
        for cand in (self.state.get("spell_lang"), "en_US", "en_GB", "en"):
            if cand in self.languages:
                return cand
        return self.languages[0] if self.languages else None

    def _apply_spelling(self, lang):
        enabled = self.lookup_action("spell").get_state().get_boolean()
        if lang:
            self.speller.set_language(lang)
            self.lookup_action("spell-lang").set_state(GLib.Variant.new_string(lang))
        self.editor.set_spelling(self.speller, enabled and self.speller.dict is not None)
        tag = self.speller.lang or ""
        short = tag.replace("_", "-").upper() if tag else "—"
        self.lang_btn.set_label(short if enabled else f"{short} (off)")
        self.lang_btn.set_tooltip_text(
            f"Spell check: {Speller.language_name(tag)}" + ("" if enabled else " — off") +
            "\nWords in the other alphabet use a matching dictionary automatically")

    def _on_spell_toggle(self, action, _p):
        on = not action.get_state().get_boolean()
        action.set_state(GLib.Variant.new_boolean(on))
        self.state["spell"] = on
        save_state(self.state)
        self._apply_spelling(self.speller.lang)

    def _on_spell_lang(self, action, param):
        tag = param.get_string()
        self.state["spell_lang"] = tag
        save_state(self.state)
        if self.doc:
            self.doc.lang = tag
            self._schedule_save()
        self._apply_spelling(tag)
        self.toast(f"Spelling: {Speller.language_name(tag)}")

    def _is_guide(self, doc=None):
        doc = doc or self.doc
        return bool(doc and doc.path) and Path(doc.path) == paths.guide_path()

    def _update_title(self):
        d = self.doc
        if self._is_guide(d):
            title, subtitle = guide.TITLE, "Practice copy"
        else:
            title = f"Chapter {d.chapter_no}" + (f" — {d.chapter_title}" if d.chapter_title else "")
            subtitle = d.book
        self.wtitle.set_title(title)
        self.wtitle.set_subtitle(subtitle)
        self.set_title(f"{title} · {APP_NAME}")

    def set_doc(self, doc):
        self._save_pending()  # the chapter being replaced (e.g. by New Chapter)
        if self._disk_dialog is not None:  # a question about the chapter being replaced
            self._disk_dialog.force_close()
        self.doc = doc
        self.editor.load(doc)
        if self.speller.available:
            self.speller.ignore_while_open(guide.SPELL_IGNORE if self._is_guide(doc) else ())
            text = " ".join(n.text for n in doc.root.walk())
            self._apply_spelling(self._pick_lang(doc.lang, text))
            for v in self.editor.all_views():
                v.recheck_spelling()
        self.stack.set_visible_child_name("editor")
        self.findbar.schedule_refresh()  # new chapter, new text views
        for act in DOC_ACTIONS:
            self.lookup_action(act).set_enabled(True)
        self._update_title()
        self.state["last_file"] = str(doc.path)
        if not self._is_guide(doc):  # New Chapter keeps suggesting your own book
            self.state["last_book"] = doc.book
        save_state(self.state)
        self._reload_sidebar()
        self._backup(force=True)  # the chapter as it was when you opened it

    @staticmethod
    def notes_root_path():
        return notes_root()

    def _backup_folder(self):
        return backups.folder_for(self.doc.path, notes_root(), paths.backups_dir())

    def _backup(self, force=False):
        """Keep a copy of the chapter as it is on disk (never in the way of saving)."""
        if not self.doc or not self.doc.path or self._is_guide():
            return
        try:
            backups.backup(self.doc.path, self._backup_folder(), force=force)
        except OSError:
            pass

    def open_path(self, path):
        self._save_pending()  # before reading: it may be this very chapter
        try:
            self.set_doc(Document.load(path))
        except (OSError, ValueError, KeyError) as e:
            self.toast(f"Could not open {Path(path).name}: {e}")

    # -- chapter sidebar -------------------------------------------------------------------

    def _reload_sidebar(self):
        if self.split.get_show_sidebar():
            self.sidebar.reload(notes_root(), self.doc.path if self.doc else None)
        return False

    # -- renaming, reordering and trashing chapters and books ------------------------------------

    def _flush_save(self):
        """Write the open chapter now: file operations read chapters from disk. Nothing
        can wait for an answer here, so a version changed on disk goes to Earlier Versions."""
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        self.save(quiet=True, ask=False)

    def _save_pending(self):
        """Write the open chapter now if an autosave is waiting: before another chapter
        replaces it, or the autosave would write that one instead and these edits would be
        lost (CR4 in CODE_REVIEW.md). An open question about a change on disk counts too:
        an autosave asked it, so its edits aren't written yet."""
        if self._save_src or self._disk_dialog is not None:
            self._flush_save()

    def _after_move(self, moved, focus=None):
        """Point the open chapter at its new file and refresh the list."""
        try:
            backups.move(moved, notes_root(), paths.backups_dir())  # earlier versions follow
        except OSError:
            pass
        if self.doc and self.doc.path:
            new = next((n for o, n in moved.items() if library.same_file(o, self.doc.path)), None)
            if new is not None:
                fresh = Document.load(new)
                self.doc.path = Path(new)
                self.doc.book, self.doc.chapter_no, self.doc.chapter_title = \
                    fresh.book, fresh.chapter_no, fresh.chapter_title
                self.doc.remember_disk()  # written by the move, not by another program
                self.state["last_file"] = str(new)
                self.state["last_book"] = fresh.book
                save_state(self.state)
                self._update_title()
        self._reload_sidebar()
        if focus is not None:
            self.sidebar.focus_path(moved.get(Path(focus), focus))

    def _close_doc(self):
        self.findbar.set_search_mode(False)
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        self.doc = None
        self.stack.set_visible_child_name("empty")
        for act in DOC_ACTIONS:
            self.lookup_action(act).set_enabled(False)
        self.wtitle.set_title(APP_NAME)
        self.wtitle.set_subtitle("")
        self.set_title(APP_NAME)
        self.state.pop("last_file", None)
        save_state(self.state)

    def on_rename(self, *_):
        """F2: the focused sidebar row (chapter or book), else the open chapter."""
        focus = self.get_focus()
        if focus is not None and focus.is_ancestor(self.sidebar):
            row = self.sidebar.focused_row()
            if row is not None and row._path is None:
                return self.on_book_rename(str(row._folder))
            if row is not None:
                return self.on_chapter_props(str(row._path))
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
        except (OSError, ValueError, KeyError) as e:
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
        GLib.idle_add(lambda: (title.grab_focus(), False)[1])

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
        GLib.idle_add(lambda: (entry.grab_focus(), False)[1])

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

    def _text_min_width(self):
        return self.split.get_content().measure(Gtk.Orientation.HORIZONTAL, -1)[0]

    def set_sidebar_width(self, width, save=False):
        w = int(max(SIDEBAR_MIN, min(SIDEBAR_MAX, width)))
        self._sidebar_w = w
        self.split.set_min_sidebar_width(w)
        self.split.set_max_sidebar_width(w)
        self._collapse.set_condition(
            Adw.BreakpointCondition.parse(f"max-width: {w + self._text_min_width() + TEXT_ROOM}px"))
        self._update_handle()
        if save:
            self.state["sidebar_width"] = w
            save_state(self.state)

    def _update_handle(self):
        self.handle.set_visible(self.split.get_show_sidebar() and not self.split.get_collapsed())
        rtl = self.get_direction() == Gtk.TextDirection.RTL
        edge = max(0, self._sidebar_w - 3)  # 6 px wide, centred on the edge
        self.handle.set_halign(Gtk.Align.END if rtl else Gtk.Align.START)
        self.handle.set_margin_start(0 if rtl else edge)
        self.handle.set_margin_end(edge if rtl else 0)

    def _handle_drag_begin(self, gesture, x, y):
        ok, box = self.handle.compute_bounds(self._overlay)
        if not (self.handle.get_visible() and ok and box.origin.x - 2 <= x <= box.origin.x + box.size.width + 2):
            gesture.set_state(Gtk.EventSequenceState.DENIED)  # not on the handle
            return
        # Claim only once the pointer moves (in _handle_drag_update): claiming on press
        # would cancel the handle's own click gesture, so double-click couldn't reset.
        self._drag_from = self._sidebar_w

    def _handle_drag_update(self, gesture, dx, _dy):
        if self._drag_from is None:
            return
        if not self.handle.has_css_class("dragging"):
            if abs(dx) < 3:
                return
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.handle.add_css_class("dragging")
        if self.get_direction() == Gtk.TextDirection.RTL:
            dx = -dx
        # never collapse while dragging ("max-width: N" includes N, hence the extra pixel)
        room = self.get_width() - self._text_min_width() - TEXT_ROOM - 1
        self.set_sidebar_width(min(self._drag_from + dx, room))

    def _handle_drag_end(self, *_):
        dragged = self.handle.has_css_class("dragging")
        self._drag_from = None
        self.handle.remove_css_class("dragging")
        if dragged:
            self.set_sidebar_width(self._sidebar_w, save=True)

    def _on_sidebar_shown(self, split, _pspec):
        self._update_handle()
        on = split.get_show_sidebar()
        self.lookup_action("sidebar").set_state(GLib.Variant.new_boolean(on))
        if not split.get_collapsed():  # an overlay closing by itself isn't a preference
            self.state["sidebar"] = on
            save_state(self.state)
        if on:
            self._reload_sidebar()

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

    def _schedule_save(self):
        if self._save_src:
            GLib.source_remove(self._save_src)
        self._save_src = GLib.timeout_add(800, self._autosave)

    def _autosave(self):
        self._save_src = None
        self.save(quiet=True)
        return False

    def save(self, quiet=False, ask=True):
        """Write the open chapter. If another program changed its file since it was opened
        or last saved, ask first (Reload or Keep Mine) instead of overwriting that version;
        with ask=False, where no answer can wait, keep this one and put the other in Earlier
        Versions (CR10 in CODE_REVIEW.md, R16)."""
        if not self.doc:
            return
        changed = self.doc.changed_on_disk()
        if changed and ask:
            self._ask_about_disk_change()
            return
        if changed:
            self._keep_disk_version()
        else:
            self._backup()  # at most every few minutes: the version about to be overwritten
        try:
            self.doc.save()
            if not quiet:
                self.toast("Saved")
        except OSError as e:
            self.toast(f"Save failed: {e}")

    def _keep_disk_version(self):
        """Put the file another program changed in Earlier Versions before this version
        replaces it: always, even in the second the last copy was taken."""
        if self.doc.path and not self._is_guide():
            try:
                backups.keep(Path(self.doc.path).read_bytes(), self._backup_folder())
            except OSError:
                pass

    def _ask_about_disk_change(self):
        if self._disk_dialog is not None:
            return
        doc = self.doc
        label = doc.chapter_title or f"Chapter {doc.chapter_no}"
        dlg = Adw.AlertDialog(
            heading="Changed on Disk",
            body=f"Another program changed “{label}” since it was opened here, a sync tool perhaps. "
                 "Reload that version, or keep the one you have here? The other one stays in Earlier "
                 "Versions either way.")
        dlg.add_response("keep", "Keep Mine")
        dlg.add_response("reload", "Reload")
        dlg.set_response_appearance("reload", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("reload")
        dlg.set_close_response("later")  # Escape: nothing now; the next save asks again
        dlg.connect("response", lambda _d, response: self._on_disk_change(doc, response))
        dlg.connect("closed", self._disk_dialog_closed)  # however it closes, or no save would write again
        self._disk_dialog = dlg
        dlg.present(self)

    def _disk_dialog_closed(self, dlg):
        if self._disk_dialog is dlg:
            self._disk_dialog = None

    def _on_disk_change(self, doc, response):
        if doc is not self.doc:
            return
        if response == "keep":
            self.save(quiet=True, ask=False)
            self.toast("Saved yours: the other version is in Earlier Versions")
        elif response == "reload":
            self._reload_from_disk()

    def _reload_from_disk(self):
        """Replace the open chapter with its file, as one undoable step; the version it
        replaces goes to Earlier Versions too."""
        doc = self.doc
        try:
            fresh = Document.load(doc.path)
        except (OSError, ValueError) as e:
            self.toast(f"Could not reload {Path(doc.path).name}: {e}")
            return
        if not self._is_guide():
            try:
                backups.keep(doc.dumps().encode("utf-8"), self._backup_folder())
            except OSError:
                pass
        self.editor.replace_content(fresh.root)
        doc.lang, doc.format, doc.extra, doc.chapter_extra = fresh.lang, fresh.format, fresh.extra, fresh.chapter_extra
        doc.remember_disk()
        if self._save_src:  # nothing to write: the chapter is now what the file holds
            GLib.source_remove(self._save_src)
            self._save_src = None
        self.toast("Reloaded from disk: Ctrl+Z brings back your version")

    def _on_close(self, *_):
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        self.save(quiet=True, ask=False)
        return False

    # -- actions -----------------------------------------------------------------------

    def on_copy(self, *_):
        lines = layout(self.doc.root, self.rules)
        provider = Gdk.ContentProvider.new_union([
            Gdk.ContentProvider.new_for_bytes(mime, GLib.Bytes.new(data if isinstance(data, bytes)
                                                                   else data.encode("utf-8")))
            for mime, data in export_formats(lines, self.rules)])
        self.get_clipboard().set_content(provider)
        self.save(quiet=True)
        self.toast("Copied — paste into TopCoding with Ctrl+V")

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
        GLib.idle_add(lambda: ((title if book.get_text() else book).grab_focus(), False)[1])

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

    # -- zoom ----------------------------------------------------------------------------------

    def set_zoom(self, percent, save=True, announce=True):
        """Size of the chapter text, in % of normal (11 pt); the rest of the window keeps its size."""
        pct = int(max(ZOOM_MIN, min(ZOOM_MAX, round(percent / ZOOM_STEP) * ZOOM_STEP)))
        changed = pct != self._zoom
        self._zoom = pct
        size = TEXT_PT * pct / 100
        self._zoom_css.load_from_string(
            f".outline .prefix, .outline textview.rt, .outline textview.rt text {{ font-size: {size:.2f}pt; }}")
        self.zoom_label.set_label(f"{pct}%")
        self.lookup_action("zoom-in").set_enabled(pct < ZOOM_MAX)
        self.lookup_action("zoom-out").set_enabled(pct > ZOOM_MIN)
        if changed:
            self.editor.text_size_changed()
        if save:
            self.state["zoom"] = pct
            save_state(self.state)
        if announce:
            if self._zoom_toast is not None:
                self._zoom_toast.dismiss()
            self._zoom_toast = Adw.Toast(title=f"Text size {pct}%", timeout=1, use_markup=False)
            self.toasts.add_toast(self._zoom_toast)

    def scroll_zoom(self, ctrl, dy):
        """Ctrl + scroll wheel zooms (up: larger). Returns True when it used the scroll."""
        if not ctrl:
            return False
        self._scroll_zoom -= dy
        steps = int(self._scroll_zoom)
        if steps:
            self._scroll_zoom -= steps
            self.set_zoom(self._zoom + steps * ZOOM_STEP)
        return True

    def on_find(self, replace=False):
        """Ctrl+F / Ctrl+H (or Ctrl+R): open the find bar, starting from the selected text if any."""
        prefill = None
        view = self.editor.cur_view
        if view is not None and view.has_selection():
            s, e = view.selection_offsets()
            text = view.get_plain()[s:e]
            if 0 < len(text) <= 100:
                prefill = text
        self.findbar.open(replace=replace, prefill=prefill)

    def on_commands(self, *_):
        """Search Commands (Ctrl+Shift+P)."""
        # The search field takes the primary selection, which collapses the chapter's
        # selection; remember it so Bold, Italic and the like still apply to it.
        view = self.editor.cur_view
        sel = view.selection_offsets() if view is not None else None

        def restore():
            if view is not None and sel and view.get_root() is not None:
                view.grab_focus()
                view.select_range(*sel)
        dlg = command_search.CommandSearch(command_search.build(self), before_run=restore)
        self._command_search = dlg
        dlg.present(self)
        GLib.idle_add(lambda: (dlg.entry.grab_focus(), False)[1])

    def on_versions(self, *_):
        """Earlier Versions: pick a kept copy of this chapter, preview it, restore it."""
        if not self.doc or self._is_guide() or not self.doc.path:
            self.toast("Open a chapter of a book first")
            return
        self._flush_save()
        found = backups.list_backups(self._backup_folder())
        dlg = Adw.Dialog(title="Earlier Versions", content_width=860, content_height=600)
        tv = Adw.ToolbarView()
        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dlg.close())
        restore = Gtk.Button(label="Restore", sensitive=False, css_classes=["suggested-action"])
        header.pack_start(cancel)
        header.pack_end(restore)
        tv.add_top_bar(header)
        if not found:
            tv.set_content(Adw.StatusPage(
                icon_name="document-open-recent-symbolic", title="No Earlier Versions Yet",
                description="A copy is kept when you open a chapter, and every 10 minutes while you edit it."))
        else:
            lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["navigation-sidebar"])
            try:
                now = Path(self.doc.path).read_bytes()
            except OSError:
                now = None
            for b in found:
                try:
                    items = sum(1 for n in Document.load(b.path).root.walk() if n.kind != "root")
                    subtitle = f"{items} item{'s' if items != 1 else ''}"
                    if now is not None and b.path.read_bytes() == now:
                        subtitle += " · same as now"
                except (OSError, ValueError, KeyError):
                    subtitle = "can't be read"
                row = Adw.ActionRow(title=f"{b.when:%H:%M}", subtitle=subtitle, tooltip_text=_when(b.when))
                row._backup = b
                lb.append(row)

            def day_header(row, before):
                # a heading above the first copy of each day: Today, Yesterday, 2026-11-02
                day = row._backup.when.date()
                if before is not None and before._backup.when.date() == day:
                    row.set_header(None)
                    return
                label = Gtk.Label(label=_day(day), xalign=0, margin_start=12, margin_top=12, margin_bottom=4)
                label.add_css_class("heading")
                label.add_css_class("dim-label")
                row.set_header(label)
            lb.set_header_func(day_header)
            preview = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                   left_margin=16, right_margin=16, top_margin=12, bottom_margin=12)
            self._versions_preview = preview

            def selected(_lb, row):
                restore.set_sensitive(row is not None)
                if row is None:
                    return
                try:
                    text = to_plain(layout(Document.load(row._backup.path).root, self.rules))
                except (OSError, ValueError, KeyError) as e:
                    text = f"This copy can't be read: {e}"
                    restore.set_sensitive(False)
                preview.get_buffer().set_text(text)

            lb.connect("row-selected", selected)
            paned = Gtk.Paned(position=250, shrink_start_child=False, resize_start_child=False,
                              start_child=Gtk.ScrolledWindow(child=lb, hscrollbar_policy=Gtk.PolicyType.NEVER),
                              end_child=Gtk.ScrolledWindow(child=preview, hexpand=True))
            tv.set_content(paned)
            lb.select_row(lb.get_row_at_index(0))

            def do_restore(*_):
                row = lb.get_selected_row()
                dlg.close()
                if row is not None:
                    self.restore_version(row._backup.path)

            restore.connect("clicked", do_restore)
            lb.connect("row-activated", lambda *_: do_restore())
        dlg.set_child(tv)
        dlg.present(self)

    def restore_version(self, path):
        """Put an earlier version's content in the editor; Ctrl+Z takes it back."""
        try:
            earlier = Document.load(path)
        except (OSError, ValueError, KeyError) as e:
            self.toast(f"Could not read that version: {e}")
            return
        self._flush_save()
        self._backup(force=True)  # what you had a moment ago is kept too
        self.editor.replace_content(earlier.root)
        self.toast("Earlier version restored. Ctrl+Z takes it back.")

    def on_show_plain(self, *_):
        text = to_plain(layout(self.doc.root, self.rules))
        dlg = Adw.Dialog(title="Plain Text", content_width=900, content_height=650)
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        view = Gtk.TextView(editable=False, monospace=True, left_margin=16, right_margin=16,
                            top_margin=12, bottom_margin=12)
        view.get_buffer().set_text(text)
        sw = Gtk.ScrolledWindow(child=view, vexpand=True)
        tv.set_content(sw)
        dlg.set_child(tv)
        dlg.present(self)

    def on_edit_rules(self, *_):
        p = user_rules_path()
        if not p.exists():
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(RULES_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError as e:  # (CR27)
                self.toast(f"Could not create {p}: {e.strerror or e}")
                return
        Gtk.FileLauncher.new(Gio.File.new_for_path(str(p))).launch(self, None, None)
        self.toast("Edit, save, then use “Reload Formatting Rules”")

    def on_reload_rules(self, *_):
        self.rules = Rules.load()
        self.editor.set_rules(self.rules)
        self.toast(f"Rules error: {self.rules.error}" if self.rules.error else "Formatting rules reloaded")

    def on_open_folder(self, *_):
        root = notes_root()
        root.mkdir(parents=True, exist_ok=True)
        Gtk.FileLauncher.new(Gio.File.new_for_path(str(root))).launch(self, None, None)

    def on_about(self, *_):
        notes_version, notes = paths.latest_release(APP_ID)
        dlg = Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon=APP_ID,
            version=VERSION,
            comments="Outline editor for book chapter notes, formatted for pasting into TopCoding.",
            license_type=Gtk.License.GPL_3_0,
        )
        if notes:  # written once, in data/dev.simo.Notterizmus.metainfo.xml
            dlg.set_release_notes_version(notes_version or VERSION)
            dlg.set_release_notes(notes)
        dlg.present(self)

    def on_shortcuts(self, *_):
        trig = {v.get("label", k): (v.get("trigger", ""), v["symbol"]) for k, v in self.rules["markers"].items()}
        groups = [
            ("Outline", [
                ("New item (splits at the cursor)", "Return"),
                ("Next numbered item at this level", "<Ctrl>Return"),
                ("Add component menu", "<Alt>Insert"),
                ("Indent / outdent", "Tab <Shift>Tab"),
                ("Move item up / down", "<Alt>Up <Alt>Down"),
                ("Cycle item type", "<Ctrl><Shift>space"),
                ("Join with the item above", "BackSpace"),
            ]),
            ("Enter on an empty item", [
                ("Bullet under Ⅰ.1.a) becomes Ⅰ.1.b)", "Return"),
            ]),
            ("Selection", [
                ("Expand / shrink selection (word, item, section…)", "<Ctrl>w <Ctrl><Shift>w"),
                ("Select all items", "<Ctrl>a"),
                ("Extend item selection", "<Shift>Up <Shift>Down"),
            ]),
            ("Multiple cursors", [
                ("Add cursor above / below (tap Ctrl twice, hold, then arrow)", "<Ctrl>Up <Ctrl>Down"),
                ("Back to one cursor", "Escape"),
            ]),
            ("Text size", [("Larger / smaller text (also Ctrl + scroll wheel)", "<Ctrl>equal <Ctrl>minus"),
                           ("Normal text size", "<Ctrl>0")]),
            ("Find", [("Find in the chapter", "<Ctrl>f"), ("Find and replace", "<Ctrl>h <Ctrl>r"),
                      ("Next / previous match", "<Ctrl>g <Ctrl><Shift>g")]),
            ("Text", [("Spelling fixes and word completion", "<Ctrl>space"),
                      ("Bold", "<Ctrl>b"), ("Italic", "<Ctrl>i"),
                      ("Undo / redo", "<Ctrl>z <Ctrl><Shift>z"),
                      ("Paste (detects outline structure)", "<Ctrl>v"),
                      ("Paste as plain text", "<Ctrl><Shift>v")]),
            ("Tables", [("Insert table", "<Ctrl>t"), ("Next / previous cell", "Tab <Shift>Tab")]),
            ("Drawings", [("Insert drawing (Excalidraw)", "<Ctrl>d")]),
            ("File", [("New chapter", "<Ctrl>n"), ("Open chapter", "<Ctrl>o"), ("Save", "<Ctrl>s"),
                      ("Previous / next chapter of the book", "<Ctrl>Page_Up <Ctrl>Page_Down"),
                      ("Chapter properties: rename, number, book (on a book: rename it)", "F2"),
                      ("Copy for TopCoding", "<Ctrl><Shift>c")]),
            ("Chapter list", [("Show or hide", "F9"),
                              ("Move the chapter up / down", "<Alt>Up <Alt>Down"),
                              ("Move the chapter to Trash", "Delete"),
                              ("All chapter actions", "Menu")]),
            ("Help", [("Search commands (find any command and its key)", "<Ctrl><Shift>p"),
                      ("Getting Started (a practice chapter)", "F1"),
                      ("Keyboard shortcuts", "<Ctrl>question")]),
        ]
        dlg = Adw.ShortcutsDialog()
        for title, items in groups:
            sec = Adw.ShortcutsSection(title=title)
            for label, accel in items:
                sec.add(Adw.ShortcutsItem(title=label, accelerator=accel))
            dlg.add(sec)
        types = Adw.ShortcutsSection(title="Item type: type at the start of an item, then Space")
        types.add(Adw.ShortcutsItem(title=f"Numbered item — “{self.rules['heading']['trigger']}”", accelerator=""))
        for label, (t, sym) in trig.items():
            types.add(Adw.ShortcutsItem(title=f"{label} {sym} — “{t}”", accelerator=""))
        dlg.add(types)
        dlg.present(self)


_ZOOM_PROVIDER = None


def _zoom_provider(display):
    global _ZOOM_PROVIDER
    if _ZOOM_PROVIDER is None:
        _ZOOM_PROVIDER = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(display, _ZOOM_PROVIDER, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    return _ZOOM_PROVIDER


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


def _day(day):
    """'Today', 'Yesterday' or '2026-11-02'."""
    from datetime import date, timedelta
    if day == date.today():
        return "Today"
    if day == date.today() - timedelta(days=1):
        return "Yesterday"
    return f"{day:%Y-%m-%d}"


def _when(dt):
    """'Today 14:05', 'Yesterday 09:30' or '2026-11-02 18:40'."""
    return f"{_day(dt.date())} {dt:%H:%M}"
