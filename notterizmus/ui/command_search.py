"""Search Commands (Ctrl+Shift+P): find any command by name and run it; its key is shown.

Editor behaviours that only exist as keys (Tab, Alt+↑, Ctrl+Space, …) run by replaying
that key on the item the cursor was in, so the search does exactly what the key does.
Digits go into the search here, so this popup has no number hotkeys.
"""
from __future__ import annotations

from gi.repository import Adw, Gdk, GLib, Gtk, Pango

from ..commands import Command, search
from ..spell import Speller
from .rows import TextRow

_MASKS = {"<Control>": Gdk.ModifierType.CONTROL_MASK, "<Shift>": Gdk.ModifierType.SHIFT_MASK,
          "<Alt>": Gdk.ModifierType.ALT_MASK}


def build(win):
    """Every command available right now, in the order shown when nothing is typed."""
    app = win.get_application()
    ed = win.editor
    cmds = []
    # The editor keeps its last chapter after one is closed, so ask the window.
    has_doc = win.doc is not None
    in_book = has_doc and not win._is_guide()

    def accel(action):
        found = app.get_accels_for_action(action) if app else []
        return found[0] if found else ""

    def act(title, action, target=None, section="", keywords="", shown=None):
        group, name = action.split(".", 1)
        a = (win if group == "win" else ed.actions).lookup_action(name)
        if a is None or not a.get_enabled():
            return
        widget = win if group == "win" else ed
        cmds.append(Command(title, lambda: widget.activate_action(action, target),
                            accel(action) if shown is None else shown, keywords, section, len(cmds)))

    # editor behaviours that are keys: replay the key on the item the cursor is in
    row = ed.rows.get(ed.current.id) if has_doc and ed.current is not None else None
    view = ed.cur_view if isinstance(row, TextRow) and ed.cur_view is row.view else \
        (row.view if isinstance(row, TextRow) else None)

    def key(title, accel_str, section="", keywords=""):
        if view is None:
            return
        name, state = accel_str, Gdk.ModifierType(0)
        for prefix, mask in _MASKS.items():
            if prefix in name:
                name, state = name.replace(prefix, ""), state | mask
        if state & Gdk.ModifierType.SHIFT_MASK and len(name) == 1:
            name = name.upper()  # as GTK reports it: Shift+w arrives as "W"
        elif state & Gdk.ModifierType.SHIFT_MASK and name == "Tab":
            name = "ISO_Left_Tab"  # and Shift+Tab as ISO_Left_Tab
        keyval = Gdk.keyval_from_name(name)

        def run():
            view.grab_focus()
            ed.on_key(row, view, keyval, state)
        cmds.append(Command(title, run, accel_str, keywords, section, len(cmds)))

    act("New Chapter", "win.new", section="Chapter", keywords="create book")
    act("Open Chapter…", "win.open", section="Chapter", keywords="file")
    if in_book:
        act("Previous Chapter", "win.prev-chapter", section="Chapter", keywords="back book")
        act("Next Chapter", "win.next-chapter", section="Chapter", keywords="forward book")
        act("Chapter Properties…", "win.rename", section="Chapter", keywords="rename number title move book")
        act("Earlier Versions…", "win.versions", section="Chapter", keywords="backup restore history undo")
    act("Copy for TopCoding", "win.copy", section="Chapter", keywords="export html paste clipboard")
    act("Show Plain Text", "win.show-plain", section="Chapter", keywords="export preview")
    act("Save", "win.save", section="Chapter")
    act("Show or Hide the Chapter List", "win.sidebar", section="List", keywords="sidebar books panel")
    if has_doc:
        act("Undo", "ed.undo", section="Text", shown="<Control>z")
        act("Redo", "ed.redo", section="Text", shown="<Control><Shift>z")
        act("Bold", "ed.bold", section="Text", shown="<Control>b", keywords="format strong")
        act("Italic", "ed.italic", section="Text", shown="<Control>i", keywords="format emphasis")
        key("Spelling Fixes and Word Completion", "<Control>space", section="Text",
            keywords="complete suggest autocomplete")
        act("Paste as Plain Text", "ed.paste-plain", section="Text", shown="<Control><Shift>v")
        key("Add Menu", "<Alt>Insert", section="Add", keywords="insert new item")
        act("Next Numbered Item", "ed.add", GLib.Variant.new_string("next"), section="Add",
            shown="<Control>Return", keywords="heading sibling")
        act("Sub-item", "ed.add", GLib.Variant.new_string("child"), section="Add", shown="",
            keywords="child nested numbered")
        act("Parent-level Item", "ed.add", GLib.Variant.new_string("parent"), section="Add", shown="",
            keywords="up level numbered")
        for name, m in win.rules["markers"].items():
            label = m.get("label", name)
            act(f"Add {label} {m['symbol']}", "ed.add", GLib.Variant.new_string(f"bullet:{name}"),
                section="Add", shown="", keywords="bullet")
        act("Insert Table", "win.insert-table", section="Add")
        for kind, marker, label, _trig in ed.kind_options():
            target = "heading" if kind == "heading" else f"bullet:{marker}"
            act(f"Make It {' '.join(label.split())}", "ed.set-kind", GLib.Variant.new_string(target),
                section="Item", shown="", keywords="type change convert")
        key("Cycle Item Type", "<Control><Shift>space", section="Item", keywords="change kind")
        key("Indent Item", "Tab", section="Item", keywords="sub level deeper")
        key("Outdent Item", "<Shift>Tab", section="Item", keywords="level up shallower")
        key("Move Item Up", "<Alt>Up", section="Item", keywords="reorder")
        key("Move Item Down", "<Alt>Down", section="Item", keywords="reorder")
        act("Delete Item", "ed.delete-item", section="Item", shown="", keywords="remove")
        act("Expand Selection", "ed.select-scope", section="Selection", shown="<Control>w")
        key("Shrink Selection", "<Control><Shift>w", section="Selection")
        act("Select All Items", "ed.select-all", section="Selection", shown="<Control>a")
    act("Check Spelling", "win.spell", section="Spelling", keywords="spell checker on off")
    for tag in getattr(win, "languages", []):
        act(f"Spelling Language: {Speller.language_name(tag)}", "win.spell-lang", GLib.Variant.new_string(tag),
            section="Spelling", keywords="dictionary")
    act("Edit Formatting Rules", "win.edit-rules", section="Settings", keywords="numbering connectors bullets")
    act("Reload Formatting Rules", "win.reload-rules", section="Settings")
    act("Open Notes Folder", "win.open-folder", section="Settings", keywords="files documents")
    act("Getting Started", "win.guide", section="Help", keywords="tutorial learn practice")
    act("Keyboard Shortcuts", "win.shortcuts", section="Help", keywords="keys help")
    act("About Notterizmus", "win.about", section="Help", keywords="version")
    return cmds


class CommandSearch(Adw.Dialog):
    __gtype_name__ = "NtzCommandSearch"

    def __init__(self, commands):
        super().__init__(title="Search Commands", content_width=560, content_height=470)
        self.commands = commands
        self.chosen = None
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.entry = Gtk.SearchEntry(placeholder_text="Type a command, e.g. “rename” or “table”",
                                     margin_top=12, margin_bottom=6, margin_start=12, margin_end=12)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE, css_classes=["navigation-sidebar"])
        self.list.set_placeholder(Gtk.Label(label="No matching command", margin_top=24, css_classes=["dim-label"]))
        self.scroller = Gtk.ScrolledWindow(child=self.list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        box.append(self.entry)
        box.append(self.scroller)
        self.set_child(box)
        self.entry.connect("search-changed", lambda *_: self.refill())
        self.entry.connect("activate", lambda *_: self.choose(self.list.get_selected_row()))
        self.entry.connect("stop-search", lambda *_: self.close())
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key)
        self.entry.add_controller(keys)
        self.list.connect("row-activated", lambda _l, row: self.choose(row))
        self.connect("closed", self._closed)
        self.refill()

    def refill(self):
        while (row := self.list.get_row_at_index(0)) is not None:
            self.list.remove(row)
        for cmd in search(self.entry.get_text(), self.commands):
            box = Gtk.Box(spacing=12)
            box.append(Gtk.Label(label=cmd.title, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
            if cmd.section:
                section = Gtk.Label(label=cmd.section)
                section.add_css_class("dim-label")
                section.add_css_class("caption")
                box.append(section)
            if cmd.accel:
                box.append(Adw.ShortcutLabel(accelerator=cmd.accel))
            row = Gtk.ListBoxRow(child=box)
            row._cmd = cmd
            self.list.append(row)
        first = self.list.get_row_at_index(0)
        if first is not None:
            self.list.select_row(first)
            self.scroller.get_vadjustment().set_value(0)

    def rows(self):
        i = 0
        while (row := self.list.get_row_at_index(i)) is not None:
            yield row
            i += 1

    def _key(self, _ctl, keyval, _code, _state):
        name = Gdk.keyval_name(keyval)
        step = {"Up": -1, "Down": 1, "Page_Up": -8, "Page_Down": 8}.get(name)
        if step is None:
            return False
        rows = list(self.rows())
        if not rows:
            return True
        cur = self.list.get_selected_row()
        i = rows.index(cur) if cur in rows else 0
        target = rows[max(0, min(len(rows) - 1, i + step))]
        self.list.select_row(target)
        ok, box = target.compute_bounds(self.list)
        if ok:
            self.scroller.get_vadjustment().clamp_page(box.origin.y, box.origin.y + box.size.height)
        return True

    def choose(self, row):
        if row is None:
            return
        self.chosen = row._cmd
        self.close()

    def _closed(self, *_):
        # Run after the dialog is gone, once it has handed focus back to the editor.
        if self.chosen is not None and self.chosen.run is not None:
            GLib.idle_add(lambda: (self.chosen.run(), False)[1])
