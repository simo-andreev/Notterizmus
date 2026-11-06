from __future__ import annotations

import json
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .. import APP_ID, APP_NAME, VERSION, guide, library, paths
from ..export import to_html, to_plain
from ..layout import layout
from ..model import Document, chapter_filename
from ..rules import Rules, config_dir, user_rules_path
from ..spell import Speller, guess_language
from .outline import OutlineEditor
from .sidebar import ChapterSidebar

RULES_TEMPLATE = Path(__file__).resolve().parent.parent / "rules.example.toml"


def notes_root():
    return paths.notes_root(glib_documents=GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS))


def _state_path():
    return config_dir() / "state.json"


def load_state():
    try:
        return json.loads(_state_path().read_text())
    except (OSError, ValueError):
        return {}


def save_state(st):
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1))


class Window(Adw.ApplicationWindow):
    __gtype_name__ = "NtzWindow"

    def __init__(self, app):
        super().__init__(application=app, default_width=1100, default_height=800, title=APP_NAME)
        self.rules = Rules.load()
        self.state = load_state()
        self.doc = None
        self._save_src = None
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
        s1.append("Show Plain Text", "win.show-plain")
        s2 = Gio.Menu()
        s2.append("Edit Formatting Rules", "win.edit-rules")
        s2.append("Reload Formatting Rules", "win.reload-rules")
        s2.append("Open Notes Folder", "win.open-folder")
        s0 = Gio.Menu()
        s0.append("Chapter Properties…", "win.rename")
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
        s3.append("Getting Started", "win.guide")
        s3.append("Keyboard Shortcuts", "win.shortcuts")
        s3.append(f"About {APP_NAME}", "win.about")
        for s in (s0, s1, s2, s3):
            menu.append_section(None, s)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Menu"))
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
        self.editor.connect("changed", lambda *_: self._schedule_save())
        self.editor.connect("message", lambda _e, msg: self.toast(msg))
        self.editor.connect("toast", lambda _e, msg, button, cb: self.toast(msg, button, cb))

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
        self.split = Adw.OverlaySplitView(sidebar=self.sidebar, content=tv,
                                          min_sidebar_width=200, max_sidebar_width=300)
        # The header needs about 620 px and the sidebar 200-300 px next to it.
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 860sp"))
        bp.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(bp)
        self.set_size_request(640, 400)
        self.toasts.set_child(self.split)
        self.set_content(self.toasts)

        for name, cb in (("new", self.on_new), ("open", self.on_open), ("save", lambda *_: self.save()),
                         ("copy", self.on_copy), ("insert-table", lambda *_: self.editor.insert_table()),
                         ("show-plain", self.on_show_plain), ("edit-rules", self.on_edit_rules),
                         ("reload-rules", self.on_reload_rules), ("open-folder", self.on_open_folder),
                         ("guide", self.on_guide), ("shortcuts", self.on_shortcuts), ("about", self.on_about),
                         ("prev-chapter", lambda *_: self.on_chapter_step(-1)),
                         ("next-chapter", lambda *_: self.on_chapter_step(1)),
                         ("rename", self.on_rename)):
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
        for act in ("copy", "insert-table", "show-plain", "save"):
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

        self.connect("close-request", self._on_close)
        if self.rules.error:
            GLib.idle_add(lambda: (self.toast("Rules file error — using defaults"), False)[1])

        last = self.state.get("last_file")
        if last and Path(last).exists():
            self.open_path(last)

    # -- helpers ------------------------------------------------------------------

    def toast(self, msg, button=None, callback=None):
        t = Adw.Toast(title=msg, timeout=6 if button else 3)
        if button:
            t.set_button_label(button)
            t.connect("button-clicked", lambda *_: callback())
        self.toasts.add_toast(t)

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
        self.doc = doc
        self.editor.load(doc)
        if self.speller.available:
            text = " ".join(n.text for n in doc.root.walk())
            self._apply_spelling(self._pick_lang(doc.lang, text))
            if self._is_guide(doc) and self.speller.dict:
                for word in guide.SPELL_IGNORE:
                    self.speller.ignore(word)
                for v in self.editor.all_views():
                    v.recheck_spelling()
        self.stack.set_visible_child_name("editor")
        for act in ("copy", "insert-table", "show-plain", "save"):
            self.lookup_action(act).set_enabled(True)
        self._update_title()
        self.state["last_file"] = str(doc.path)
        if not self._is_guide(doc):  # New Chapter keeps suggesting your own book
            self.state["last_book"] = doc.book
        save_state(self.state)
        self._reload_sidebar()

    def open_path(self, path):
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
        """Write the open chapter now: file operations read chapters from disk."""
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        self.save(quiet=True)

    def _after_move(self, moved, focus=None):
        """Point the open chapter at its new file and refresh the list."""
        if self.doc and self.doc.path:
            new = next((n for o, n in moved.items() if library.same_file(o, self.doc.path)), None)
            if new is not None:
                fresh = Document.load(new)
                self.doc.path = Path(new)
                self.doc.book, self.doc.chapter_no, self.doc.chapter_title = \
                    fresh.book, fresh.chapter_no, fresh.chapter_title
                self.state["last_file"] = str(new)
                self.state["last_book"] = fresh.book
                save_state(self.state)
                self._update_title()
        self._reload_sidebar()
        if focus is not None:
            self.sidebar.focus_path(moved.get(Path(focus), focus))

    def _close_doc(self):
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        self.doc = None
        self.stack.set_visible_child_name("empty")
        for act in ("copy", "insert-table", "show-plain", "save"):
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
            return
        except OSError as e:
            self.toast(f"Could not change the chapter: {e}")
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
        try:
            moved = library.rename_book(old_folder, name)
        except FileExistsError:
            self.toast("Another book already has that name")
            return
        except OSError as e:
            self.toast(f"Could not rename the book: {e}")
            return
        if old_folder.name in self.sidebar.expanded:
            self.sidebar.expanded.discard(old_folder.name)
            self.sidebar.expanded.add(library.safe_name(name))
        self._after_move(moved)

    def _reorder_chapters(self, order, moving):
        self._flush_save()
        try:
            moved = library.reorder(order)
        except (FileExistsError, OSError) as e:
            self.toast(f"Could not reorder the chapters: {e}")
            self._reload_sidebar()
            return
        self._after_move(moved, focus=moving)

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
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)  # no trash access (e.g. inside a sandbox): write it back
        if reopen:
            self.open_path(path)
        self._reload_sidebar()

    def _on_sidebar_shown(self, split, _pspec):
        on = split.get_show_sidebar()
        self.lookup_action("sidebar").set_state(GLib.Variant.new_boolean(on))
        if not split.get_collapsed():  # an overlay closing by itself isn't a preference
            self.state["sidebar"] = on
            save_state(self.state)
        if on:
            self._reload_sidebar()

    def _open_from_sidebar(self, path):
        if not (self.doc and self.doc.path and Path(self.doc.path).resolve() == Path(path).resolve()):
            self.save(quiet=True)
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
        self.save(quiet=True)
        self.open_path(ch.path)

    def _schedule_save(self):
        if self._save_src:
            GLib.source_remove(self._save_src)
        self._save_src = GLib.timeout_add(800, self._autosave)

    def _autosave(self):
        self._save_src = None
        self.save(quiet=True)
        return False

    def save(self, quiet=False):
        if not self.doc:
            return
        try:
            self.doc.save()
            if not quiet:
                self.toast("Saved")
        except OSError as e:
            self.toast(f"Save failed: {e}")

    def _on_close(self, *_):
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        self.save(quiet=True)
        return False

    # -- actions -----------------------------------------------------------------------

    def on_copy(self, *_):
        lines = layout(self.doc.root, self.rules)
        html = to_html(lines, code_prefix=self.rules["export"]["code_prefix"])
        plain = to_plain(lines)
        provider = Gdk.ContentProvider.new_union([
            Gdk.ContentProvider.new_for_bytes("text/html", GLib.Bytes.new(html.encode("utf-8"))),
            Gdk.ContentProvider.new_for_bytes("text/plain;charset=utf-8", GLib.Bytes.new(plain.encode("utf-8"))),
            Gdk.ContentProvider.new_for_bytes("text/plain", GLib.Bytes.new(plain.encode("utf-8"))),
        ])
        self.get_clipboard().set_content(provider)
        self.save(quiet=True)
        self.toast("Copied — paste into TopCoding with Ctrl+V")

    def on_new(self, *_):
        dlg = Adw.AlertDialog(heading="New Chapter",
                              body="Each book + chapter is saved as its own file.")
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        book = Adw.EntryRow(title="Book")
        book.set_text(self.state.get("last_book", ""))
        num = Adw.SpinRow.new_with_range(1, 999, 1)
        num.set_title("Chapter number")
        if self.doc and self.doc.book == book.get_text():
            num.set_value(self.doc.chapter_no + 1)
        title = Adw.EntryRow(title="Chapter title (optional)")
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
            existing = sorted(folder.glob(f"{n:02d}*.notz")) if folder.exists() else []
            if existing:
                self.open_path(existing[0])
                self.toast("That chapter already exists — opened it")
                return
            doc = Document.new(b, n, t, folder / chapter_filename(n, t))
            doc.save()
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
                self.save(quiet=True)
                self.open_path(gf.get_path())

        fd.open(self, None, done)

    def on_guide(self, *_):
        """Open a fresh practice copy of the Getting Started chapter."""
        self.save(quiet=True)
        doc = guide.document(paths.guide_path(), self.rules)
        try:
            doc.save()
        except OSError as e:
            self.toast(f"Could not create the guide: {e}")
            return
        self.set_doc(doc)
        self.toast("A practice copy: change anything. F1 brings back a fresh one.")

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
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(RULES_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
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
            ("Text", [("Spelling fixes and word completion", "<Ctrl>space"),
                      ("Bold", "<Ctrl>b"), ("Italic", "<Ctrl>i"),
                      ("Undo / redo", "<Ctrl>z <Ctrl><Shift>z"),
                      ("Paste (detects outline structure)", "<Ctrl>v"),
                      ("Paste as plain text", "<Ctrl><Shift>v")]),
            ("Tables", [("Insert table", "<Ctrl>t"), ("Next / previous cell", "Tab <Shift>Tab")]),
            ("File", [("New chapter", "<Ctrl>n"), ("Open chapter", "<Ctrl>o"), ("Save", "<Ctrl>s"),
                      ("Previous / next chapter of the book", "<Ctrl>Page_Up <Ctrl>Page_Down"),
                      ("Chapter properties: rename, number, book (on a book: rename it)", "F2"),
                      ("Copy for TopCoding", "<Ctrl><Shift>c")]),
            ("Chapter list", [("Show or hide", "F9"),
                              ("Move the chapter up / down", "<Alt>Up <Alt>Down"),
                              ("Move the chapter to Trash", "Delete"),
                              ("All chapter actions", "Menu")]),
            ("Help", [("Getting Started (a practice chapter)", "F1"),
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
