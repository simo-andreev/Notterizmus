from __future__ import annotations

import json
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .. import APP_ID, APP_NAME, VERSION
from ..export import to_html, to_plain
from ..layout import layout
from ..model import Document, chapter_filename
from ..rules import Rules, config_dir, user_rules_path
from ..spell import Speller, guess_language
from .outline import OutlineEditor

RULES_TEMPLATE = Path(__file__).resolve().parent.parent / "rules.example.toml"


def notes_root():
    d = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS) or str(Path.home() / "Documents")
    return Path(d) / "Notterizmus"


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
        s3.append("Keyboard Shortcuts", "win.shortcuts")
        s3.append(f"About {APP_NAME}", "win.about")
        for s in (s1, s2, s3):
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

        empty = Adw.StatusPage(icon_name="accessories-text-editor-symbolic", title="No Chapter Open",
                               description="Create a chapter for a book, or open an existing one.")
        bb = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        nb = Gtk.Button(label="New Chapter", action_name="win.new", css_classes=["pill", "suggested-action"])
        ob = Gtk.Button(label="Open…", action_name="win.open", css_classes=["pill"])
        bb.append(nb)
        bb.append(ob)
        empty.set_child(bb)

        self.stack = Gtk.Stack()
        self.stack.add_named(empty, "empty")
        self.stack.add_named(self.editor, "editor")
        tv.set_content(self.stack)
        self.toasts.set_child(tv)
        self.set_content(self.toasts)

        for name, cb in (("new", self.on_new), ("open", self.on_open), ("save", lambda *_: self.save()),
                         ("copy", self.on_copy), ("insert-table", lambda *_: self.editor.insert_table()),
                         ("show-plain", self.on_show_plain), ("edit-rules", self.on_edit_rules),
                         ("reload-rules", self.on_reload_rules), ("open-folder", self.on_open_folder),
                         ("shortcuts", self.on_shortcuts), ("about", self.on_about)):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", cb)
            self.add_action(a)
        for act in ("copy", "insert-table", "show-plain", "save"):
            self.lookup_action(act).set_enabled(False)

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

    def _update_title(self):
        d = self.doc
        title = f"Chapter {d.chapter_no}" + (f" — {d.chapter_title}" if d.chapter_title else "")
        self.wtitle.set_title(title)
        self.wtitle.set_subtitle(d.book)
        self.set_title(f"{title} · {APP_NAME}")

    def set_doc(self, doc):
        self.doc = doc
        self.editor.load(doc)
        if self.speller.available:
            text = " ".join(n.text for n in doc.root.walk())
            self._apply_spelling(self._pick_lang(doc.lang, text))
        self.stack.set_visible_child_name("editor")
        for act in ("copy", "insert-table", "show-plain", "save"):
            self.lookup_action(act).set_enabled(True)
        self._update_title()
        self.state["last_file"] = str(doc.path)
        self.state["last_book"] = doc.book
        save_state(self.state)

    def open_path(self, path):
        try:
            self.set_doc(Document.load(path))
        except (OSError, ValueError, KeyError) as e:
            self.toast(f"Could not open {Path(path).name}: {e}")

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
            folder = notes_root() / "".join("_" if c in "/\\\0" else c for c in b)
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
        start = Path(self.doc.path).parent if self.doc and self.doc.path else root
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
        dlg = Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon=APP_ID,
            version=VERSION,
            comments="Outline editor for book chapter notes, formatted for pasting into TopCoding.",
            release_notes_version="1.0.0",
            release_notes=(
                "<p>First release.</p><ul>"
                "<li>Outline editor with automatic numbering (Ⅰ, Ⅰ.1, Ⅰ.1.a) and tree connectors</li>"
                "<li>Bold, italic and tables; Copy for TopCoding</li>"
                "<li>Structure-aware paste, undo/redo, selection scopes, multiple cursors</li>"
                "<li>Spell checking with per-chapter language</li></ul>"),
        )
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
                ("Cycle item type", "<Ctrl>space"),
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
            ("Text", [("Bold", "<Ctrl>b"), ("Italic", "<Ctrl>i"),
                      ("Undo / redo", "<Ctrl>z <Ctrl><Shift>z"),
                      ("Paste (detects outline structure)", "<Ctrl>v"),
                      ("Paste as plain text", "<Ctrl><Shift>v")]),
            ("Tables", [("Insert table", "<Ctrl>t"), ("Next / previous cell", "Tab <Shift>Tab")]),
            ("File", [("New chapter", "<Ctrl>n"), ("Open chapter", "<Ctrl>o"), ("Save", "<Ctrl>s"),
                      ("Copy for TopCoding", "<Ctrl><Shift>c")]),
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
