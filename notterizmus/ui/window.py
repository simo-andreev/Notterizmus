from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .. import APP_ID, APP_NAME, assessments, guide, library, paths
from ..layout import layout
from ..model import Document
from ..rules import Rules
from ..spell import Speller, guess_language
from .findbar import FindBar
from .assessments_window import AssessmentsWindow
from .helpers import WORKER, assessments_root, load_state, notes_root, run_once, save_state
from .outline import OutlineEditor
from .outline_clipboard import export_formats
from .sidebar import ChapterSidebar
from .window_chapters import WindowChapters
from .window_dialogs import WindowDialogs
from .window_saving import WindowSaving
from .window_sizing import SIDEBAR_DEFAULT, WindowSizing
from .window_zoom import ZOOM_STEP, WindowZoom, _zoom_provider

DOC_ACTIONS = ("copy", "insert-table", "insert-drawing", "show-plain", "save", "find", "replace", "find-next", "find-prev")


class Window(WindowSaving, WindowChapters, WindowDialogs, WindowZoom, WindowSizing, Adw.ApplicationWindow):
    """The main window: the header bar, the chapter list beside the editor, the find bar,
    and the open chapter (doc). Its parts are mixins, one theme each (CR38 in
    CODE_REVIEW.md), as the editor's are: window_saving (autosave, changes on disk),
    window_chapters (new, open, rename, reorder, trash), window_dialogs, window_zoom and
    window_sizing (the chapter list's width). They share doc, editor, findbar, sidebar,
    split, state, rules and toast(); the state each keeps is in its module's docstring."""
    __gtype_name__ = "NtzWindow"

    def __init__(self, app):
        super().__init__(application=app, default_width=1100, default_height=800, title=APP_NAME)
        self.rules = Rules.load()
        self.state = load_state()
        self.doc = None
        self._save_src = None
        self._disk_dialog = None  # asking what to do about a chapter changed on disk (CR10)
        self._assessments = None  # the Assessments window, while it is open
        self._linked = {}  # {chapter file, resolved: the folder of its newest assessment}
        self.speller = Speller()
        self.languages = self.speller.languages()

        self.toasts = Adw.ToastOverlay()
        tv = Adw.ToolbarView()
        tv.add_top_bar(self._build_header())
        self._build_editor(tv)
        tv.set_content(self._build_stack())
        self._build_sidebar(tv)
        self._add_actions()
        self._add_sidebar_action()
        self._add_spelling_actions()

        self.set_zoom(self.state.get("zoom", 100), save=False, announce=False)
        self.connect("close-request", self._on_close)
        if self.rules.error:
            GLib.idle_add(run_once, self.toast, "Rules file error — using defaults")

        last = self.state.get("last_file")
        if last and Path(last).exists():
            self.open_path(last)
        self._offer_stranded()
        self.refresh_linked()

    # -- building the window ----------------------------------------------------------

    def _build_header(self):
        """The header bar: chapter buttons, the main menu with its zoom row, Copy for
        TopCoding and the spelling language."""
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
        sa = Gio.Menu()
        sa.append("Assessments…", "win.assessments")
        sa.append("Import Assessment Report…", "win.import-assessment")
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
        for s in (sz, s0, sa, s1, s2, s3):
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
        return header

    def _build_editor(self, tv):
        """The editor and its find bar, and Ctrl + scroll wheel zoom."""
        self.editor = OutlineEditor(self.rules)
        self.editor.spell_menu = self.spell_menu
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

    def _build_stack(self):
        """The editor, or a page to start from while no chapter is open."""
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
        return self.stack

    def _build_sidebar(self, tv):
        """The chapter list beside tv (the toolbar view), with its resize handle."""
        # Chapter list on the left; it becomes an overlay when the window is narrow.
        self.sidebar = ChapterSidebar()
        self.sidebar.connect("open-chapter", lambda _s, path: self._open_from_sidebar(path))
        self.sidebar.on_reorder = self._reorder_chapters
        self.sidebar.popup = self.editor.popup_menu
        self.sidebar.has_assessment = self.has_assessment
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

    def _add_actions(self):
        for name, cb in (("new", self.on_new), ("open", self.on_open), ("save", lambda *_: self.save()),
                         ("copy", self.on_copy), ("insert-table", lambda *_: self.editor.insert_table()),
                         ("insert-drawing", lambda *_: self.editor.insert_drawing()),
                         ("show-plain", self.on_show_plain), ("edit-rules", self.on_edit_rules),
                         ("reload-rules", self.on_reload_rules), ("open-folder", self.on_open_folder),
                         ("guide", self.on_guide), ("shortcuts", self.on_shortcuts), ("about", self.on_about),
                         ("prev-chapter", lambda *_: self.on_chapter_step(-1)),
                         ("next-chapter", lambda *_: self.on_chapter_step(1)),
                         ("rename", self.on_rename), ("versions", self.on_versions),
                         ("assessments", self.on_assessments),
                         ("import-assessment", lambda *_: self.assessments_window().choose_file()),
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
                         ("chapter-trash", self.on_chapter_trash),
                         ("chapter-practice", self.on_chapter_practice),
                         ("chapter-import", self.on_chapter_import)):
            a = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            a.connect("activate", lambda _a, p, f=cb: f(p.get_string()))
            self.add_action(a)
        for act in DOC_ACTIONS:
            self.lookup_action(act).set_enabled(False)

    def _add_sidebar_action(self):
        """F9: show or hide the chapter list, remembered between runs."""
        show = bool(self.state.get("sidebar", True))
        a = Gio.SimpleAction.new_stateful("sidebar", None, GLib.Variant.new_boolean(show))
        a.connect("activate", lambda act, _p: self.split.set_show_sidebar(not act.get_state().get_boolean()))
        self.add_action(a)
        self.split.set_show_sidebar(show)
        self.split.connect("notify::show-sidebar", self._on_sidebar_shown)
        self.connect("notify::is-active", lambda *_: self.is_active() and self._reload_sidebar())
        self._reload_sidebar()

    def _add_spelling_actions(self):
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

    # -- the open chapter ------------------------------------------------------------

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

    def open_path(self, path):
        self._save_pending()  # before reading: it may be this very chapter
        try:
            self.set_doc(Document.load(path))
        except (OSError, ValueError) as e:
            self.toast(f"Could not open {Path(path).name}: {e}")

    def _reload_sidebar(self):
        if self.split.get_show_sidebar():
            self.sidebar.reload(notes_root(), self.doc.path if self.doc else None)
        return False

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

    # -- assessments ---------------------------------------------------------------------

    def assessments_window(self):
        """The Assessments window, opened if it isn't."""
        if self._assessments is None:
            self._assessments = AssessmentsWindow(self.get_application(), on_changed=self.refresh_linked,
                                                  on_closed=self._assessments_closed)
        self._assessments.present()
        return self._assessments

    def _assessments_closed(self, win):
        if self._assessments is win:
            self._assessments = None

    def on_assessments(self, *_):
        """Assessments…: the open chapter's newest assessment, if it has one; else the list."""
        folder = self._linked.get(_key(self.doc.path)) if self.doc and self.doc.path else None
        win = self.assessments_window()
        if folder is not None:
            win.open_folder(folder)

    def on_chapter_practice(self, path):
        folder = self._linked.get(_key(path))
        if folder is not None:
            self.assessments_window().open_folder(folder)

    def on_chapter_import(self, path):
        self.assessments_window().choose_file(library.Chapter(*library.parse_name(Path(path).stem), Path(path)))

    def has_assessment(self, path):
        """Whether the chapter at path has an assessment (for its menu in the chapter list)."""
        return _key(path) in self._linked

    def refresh_linked(self):
        """Find again which chapters have assessments (in the background)."""
        WORKER.run(lambda root=assessments_root(), notes=notes_root(): _linked_chapters(root, notes),
                   done=self._set_linked, failed=lambda _e: None)  # (no menu items: nothing else needs it)

    def _set_linked(self, linked):
        self._linked = linked
        self.sidebar.update_assessments()
        if self._assessments is not None and self._assessments.page is None:
            self._assessments.refresh()

    # -- copy and find -----------------------------------------------------------------

    def on_copy(self, *_):
        lines = layout(self.doc.root, self.rules)
        provider = Gdk.ContentProvider.new_union([
            Gdk.ContentProvider.new_for_bytes(mime, GLib.Bytes.new(data if isinstance(data, bytes)
                                                                   else data.encode("utf-8")))
            for mime, data in export_formats(lines, self.rules)])
        self.get_clipboard().set_content(provider)
        self.save(quiet=True)
        self.toast("Copied — paste into TopCoding with Ctrl+V")

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


def _key(path):
    """A chapter's file as Window._linked knows it."""
    return str(Path(path).resolve())


def _linked_chapters(root, notes):
    """{chapter file, resolved: the folder of its most recently completed assessment}
    (for helpers.WORKER: no GTK)."""
    found, _broken = assessments.list_all(root)
    linked = {}
    for a, ch in assessments.resolve_links(found, library.scan(notes), notes):
        if ch is not None:
            linked.setdefault(_key(ch.path), a.folder)  # (found is newest first)
    return linked
