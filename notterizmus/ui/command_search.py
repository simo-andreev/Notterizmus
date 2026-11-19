"""Search Commands (Ctrl+Shift+P): find any command by name and run it; its key is shown.

Editor behaviours that only exist as keys (Tab, Alt+↑, Ctrl+Space, …) run by replaying
that key on the item the cursor was in, so the search does exactly what the key does.
Digits go into the search here, so this popup has no number hotkeys.
"""
from __future__ import annotations

from gi.repository import Adw, Gdk, GLib, Gtk, Pango

from ..commands import COMMANDS, Command, search
from ..spell import Speller
from .rows import TextRow

def build(win):
    """Every command of COMMANDS available right now, in its order."""
    ed = win.editor
    cmds = []
    # The editor keeps its last chapter after one is closed, so ask the window.
    has_doc = win.doc is not None
    in_book = has_doc and not win._is_guide()

    # editor behaviours that are keys: replay the key on the item the cursor is in
    row = ed.rows.get(ed.current.id) if has_doc and ed.current is not None else None
    view = ed.cur_view if isinstance(row, TextRow) and ed.cur_view is row.view else \
        (row.view if isinstance(row, TextRow) else None)

    def act(spec, title, target=None):
        group, name = spec.action.split(".", 1)
        a = (win if group == "win" else ed.actions).lookup_action(name)
        if a is None or not a.get_enabled():
            return
        widget = win if group == "win" else ed
        variant = None if target is None else GLib.Variant.new_string(target)
        cmds.append(Command(title, lambda: widget.activate_action(spec.action, variant),
                            _accel(spec.key), spec.keywords, spec.section, len(cmds)))

    def key(spec):
        if view is None:
            return
        _ok, keyval, state = Gtk.accelerator_parse(spec.key)
        if state & Gdk.ModifierType.SHIFT_MASK:
            # as GTK reports them: Shift+w arrives as "W", Shift+Tab as ISO_Left_Tab
            keyval = Gdk.KEY_ISO_Left_Tab if keyval == Gdk.KEY_Tab else Gdk.keyval_to_upper(keyval)

        def run():
            view.grab_focus()
            ed.on_key(row, view, keyval, state)
        cmds.append(Command(spec.title, run, _accel(spec.key), spec.keywords, spec.section, len(cmds)))

    for spec in COMMANDS:
        if not spec.listed or (spec.needs == "doc" and not has_doc) or (spec.needs == "book" and not in_book):
            continue
        if not spec.action:
            key(spec)
        elif spec.each == "marker":
            for name, m in win.rules["markers"].items():
                act(spec, spec.title.format(label=f"{m.get('label', name)} {m['symbol']}"), f"bullet:{name}")
        elif spec.each == "kind":
            for kind, marker, label, _trig in ed.kind_options():
                act(spec, spec.title.format(label=" ".join(label.split())),
                    "heading" if kind == "heading" else f"bullet:{marker}")
        elif spec.each == "language":
            for tag in getattr(win, "languages", []):
                act(spec, spec.title.format(label=Speller.language_name(tag)), tag)
        else:
            act(spec, spec.title, spec.target)
    return cmds


def _accel(key):
    """The key as GTK names it ("<Ctrl>z" is "<Control>z"), or ""."""
    if not key:
        return ""
    _ok, keyval, mods = Gtk.accelerator_parse(key)
    return Gtk.accelerator_name(keyval, mods)


class CommandRow(Gtk.ListBoxRow):
    def __init__(self, cmd, **props):
        super().__init__(**props)
        self.cmd = cmd


class CommandSearch(Adw.Dialog):
    __gtype_name__ = "NtzCommandSearch"

    def __init__(self, commands, before_run=None):
        super().__init__(title="Search Commands", content_width=560, content_height=470)
        self.commands = commands
        self.chosen = None
        self.before_run = before_run  # e.g. put the text selection back first
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # no search delay: Enter right after typing must act on what was typed
        self.entry = Gtk.SearchEntry(placeholder_text="Type a command, e.g. “rename” or “table”",
                                     search_delay=0,
                                     margin_top=12, margin_bottom=6, margin_start=12, margin_end=12)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE, css_classes=["navigation-sidebar"])
        self.list.set_placeholder(Gtk.Label(label="No matching command", margin_top=24, css_classes=["dim-label"]))
        self.scroller = Gtk.ScrolledWindow(child=self.list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        box.append(self.entry)
        box.append(self.scroller)
        self.set_child(box)
        self.entry.connect("search-changed", lambda *_: self.refill())
        self.entry.connect("activate", lambda *_: self._activate())
        self.entry.connect("stop-search", lambda *_: self.close())
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key)
        self.entry.add_controller(keys)
        self.list.connect("row-activated", lambda _l, row: self.choose(row))
        self.connect("closed", self._closed)
        self.refill()

    def _activate(self):
        if self.entry.get_text() != self._filled_for:  # Enter beat the list: catch up first
            self.refill()
        self.choose(self.list.get_selected_row())

    def refill(self):
        self._filled_for = self.entry.get_text()
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
            row = CommandRow(cmd, child=box)
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
        self.chosen = row.cmd
        self.close()

    def _closed(self, *_):
        # Run after the dialog is gone, once it has handed focus back to the editor.
        if self.chosen is not None and self.chosen.run is not None:
            def run():
                if self.before_run is not None:
                    self.before_run()
                self.chosen.run()
                return False
            GLib.idle_add(run)
