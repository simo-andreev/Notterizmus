"""Row widgets, one per node kind. Register new kinds (e.g. "drawing") in ROW_TYPES."""
from __future__ import annotations

from gi.repository import Gdk, GLib, Gtk

from .richtext import RichText


def _prefix_markup(segs):
    out = []
    for s in segs:
        t = GLib.markup_escape_text(s.text)
        if s.bold:
            t = f"<b>{t}</b>"
        if s.role == "connector":
            t = f'<span font_family="monospace" alpha="55%">{t}</span>'
        out.append(t)
    return "".join(out)


def _mods(state):
    return (bool(state & Gdk.ModifierType.CONTROL_MASK),
            bool(state & Gdk.ModifierType.SHIFT_MASK),
            bool(state & Gdk.ModifierType.ALT_MASK))


def wire_view(editor, row, view):
    """Shared input handling for every RichText that belongs to a row."""
    keys = Gtk.EventControllerKey()
    keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    keys.connect("key-pressed", lambda _c, kv, _kc, st: editor.on_key(row, view, kv, st))
    keys.connect("key-released", lambda _c, kv, _kc, st: editor.on_key_released(kv))
    view.add_controller(keys)
    focus = Gtk.EventControllerFocus()
    focus.connect("enter", lambda *_: editor.set_current(row.node, view))
    view.add_controller(focus)
    click = Gtk.GestureClick(button=0)
    click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    click.connect("pressed", lambda g, _n, x, y: editor.on_click(row, view, g, x, y))
    view.add_controller(click)
    view.connect("paste-clipboard", lambda v: (v.stop_emission_by_name("paste-clipboard"),
                                               editor.paste(row, v)))
    view.connect("copy-clipboard", lambda v: editor.copy_text(v, cut=False) and v.stop_emission_by_name("copy-clipboard"))
    view.connect("cut-clipboard", lambda v: editor.copy_text(v, cut=True) and v.stop_emission_by_name("cut-clipboard"))
    editor.track_cursor(view)


class _PrefixRow(Gtk.Box):
    def __init__(self, editor, node):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class("row")
        self.editor = editor
        self.node = node
        self.prefix = Gtk.Label(xalign=0, valign=Gtk.Align.START)
        self.prefix.add_css_class("prefix")
        self.prefix.set_cursor_from_name("pointer")
        self.prefix.set_tooltip_text("Item menu")
        click = Gtk.GestureClick(button=0)
        click.connect("released", lambda *_: editor.show_item_menu(self))
        self.prefix.add_controller(click)
        self.append(self.prefix)

    def set_prefix(self, segs):
        self.prefix.set_markup(_prefix_markup(segs))

    def views(self):
        return []


class TextRow(_PrefixRow):
    """Heading or bullet: prefix (connectors + label/marker) followed by rich text."""

    def __init__(self, editor, node):
        super().__init__(editor, node)
        self.view = RichText()
        self.view.set_runs(node.runs)
        self.view.connect("content-changed", self._on_changed)
        wire_view(editor, self, self.view)
        self.append(self.view)
        self.connect("map", lambda *_: GLib.timeout_add(20, lambda: (self.view.queue_resize(), False)[1]))

    def _on_changed(self, _v):
        self.node.runs = self.view.get_runs()
        self.editor.on_text_changed(self)

    def reload(self):
        self.view.set_runs(self.node.runs)

    def focus(self, offset=0):
        self.view.grab_focus()
        self.view.set_cursor(offset)

    def cursor_offset(self):
        return self.view.cursor_offset()

    def views(self):
        return [self.view]


class TableRow(_PrefixRow):
    def __init__(self, editor, node):
        super().__init__(editor, node)
        self.cur = (0, 0)
        self.cells = {}
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        bar = Gtk.Box(spacing=2)
        bar.add_css_class("table-bar")
        for label, tip, cb in (("+ Row", "Add row below", self.add_row),
                               ("+ Column", "Add column right", self.add_col),
                               ("− Row", "Remove row", self.del_row),
                               ("− Column", "Remove column", self.del_col)):
            b = Gtk.Button(label=label, tooltip_text=tip)
            b.add_css_class("flat")
            b.connect("clicked", lambda _b, f=cb: f())
            bar.append(b)
        self.header_btn = Gtk.ToggleButton(label="Header row", active=bool(node.data.get("header")))
        self.header_btn.add_css_class("flat")
        self.header_btn.connect("toggled", self._toggle_header)
        bar.append(self.header_btn)
        rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Delete table")
        rm.add_css_class("flat")
        rm.connect("clicked", lambda _b: editor.delete_items([self.node]))
        bar.append(rm)
        self.grid = Gtk.Grid(halign=Gtk.Align.START)
        self.grid.add_css_class("ntz-table")
        box.append(bar)
        box.append(self.grid)
        self.append(box)
        # Text views inside a Grid finish their layout after the first measure;
        # re-queue so the grid picks up the real cell heights.
        self.connect("map", lambda *_: GLib.timeout_add(30, self._requeue))
        self.build()

    def _requeue(self):
        for rt in self.cells.values():
            rt.queue_resize()
        self.grid.queue_resize()
        return False

    @property
    def rows(self):
        return self.node.data.setdefault("rows", [[[]]])

    def views(self):
        return list(self.cells.values())

    def build(self, focus=None):
        while (c := self.grid.get_first_child()) is not None:
            self.grid.remove(c)
        header = self.node.data.get("header")
        self.cells = {}
        for r, row in enumerate(self.rows):
            for c, cell in enumerate(row):
                rt = RichText(left_margin=6, right_margin=6)
                rt.set_runs(cell)
                rt.set_size_request(150, -1)  # height set by editor.size_new_views
                rt.add_css_class("cell")
                if header and r == 0:
                    rt.add_css_class("header-cell")
                rt.connect("content-changed", self._cell_changed, r, c)
                keys = Gtk.EventControllerKey()
                keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
                keys.connect("key-pressed", self._cell_key, rt, r, c)
                rt.add_controller(keys)
                fc = Gtk.EventControllerFocus()
                fc.connect("enter", self._cell_focus, rt, r, c)
                rt.add_controller(fc)
                self.editor.track_cursor(rt)
                self.grid.attach(rt, c, r, 1, 1)
                self.cells[(r, c)] = rt
        self.editor.size_new_views(self.cells.values())
        GLib.timeout_add(30, self._requeue)
        if focus:
            GLib.idle_add(self.focus_cell, *focus)

    def focus_cell(self, r=0, c=0, offset=-1):
        rt = self.cells.get((r, c))
        if rt:
            rt.grab_focus()
            rt.set_cursor(offset)
        return False

    def focus(self, offset=0):
        self.focus_cell(0, 0, offset)

    def cursor_offset(self):
        return None

    def _cell_focus(self, _fc, rt, r, c):
        self.cur = (r, c)
        self.editor.set_current(self.node, rt)

    def _cell_changed(self, rt, r, c):
        self.rows[r][c] = rt.get_runs()
        self.editor.mark_changed(self.node)

    def _cell_key(self, _ctl, keyval, _kc, state, rt, r, c):
        name = Gdk.keyval_name(keyval)
        ctrl, shift, alt = _mods(state)
        nrows, ncols = len(self.rows), len(self.rows[0]) if self.rows else 0
        if self.editor.common_key(rt, name, ctrl, shift, alt):
            return True
        if ctrl and not shift and name == "space":
            self.editor.show_assist(rt)
            return True
        if ctrl and name in ("b", "B"):
            rt.toggle("bold")
            return True
        if ctrl and name in ("i", "I"):
            rt.toggle("italic")
            return True
        if name == "Tab" and not ctrl:
            i = r * ncols + c + 1
            if i >= nrows * ncols:
                self.add_row()
            else:
                self.focus_cell(i // ncols, i % ncols)
            return True
        if name == "ISO_Left_Tab":
            i = r * ncols + c - 1
            if i >= 0:
                self.focus_cell(i // ncols, i % ncols)
            return True
        if name in ("Return", "KP_Enter") and not shift:
            if r + 1 < nrows:
                self.focus_cell(r + 1, c)
            else:
                self.editor.focus_neighbor(self.node, +1, create=True)
            return True
        if name == "Up" and not shift and rt.on_first_line():
            if r > 0:
                self.focus_cell(r - 1, c)
            else:
                self.editor.focus_neighbor(self.node, -1)
            return True
        if name == "Down" and not shift and rt.on_last_line():
            if r + 1 < nrows:
                self.focus_cell(r + 1, c, 0)
            else:
                self.editor.focus_neighbor(self.node, +1)
            return True
        return False

    def _changed_struct(self, focus):
        self.build(focus=focus)
        self.editor.mark_changed(self.node, structural=True)

    def add_row(self):
        r, c = self.cur
        ncols = len(self.rows[0]) if self.rows else 1
        self.rows.insert(r + 1, [[] for _ in range(ncols)])
        self.cur = (r + 1, 0)
        self._changed_struct((r + 1, 0))

    def add_col(self):
        r, c = self.cur
        for row in self.rows:
            row.insert(c + 1, [])
        self.cur = (r, c + 1)
        self._changed_struct((r, c + 1))

    def del_row(self):
        if len(self.rows) <= 1:
            return
        r, c = self.cur
        del self.rows[r]
        self.cur = (min(r, len(self.rows) - 1), c)
        self._changed_struct(self.cur)

    def del_col(self):
        if not self.rows or len(self.rows[0]) <= 1:
            return
        r, c = self.cur
        for row in self.rows:
            del row[c]
        self.cur = (r, min(c, len(self.rows[0]) - 1))
        self._changed_struct(self.cur)

    def _toggle_header(self, btn):
        if bool(self.node.data.get("header")) == btn.get_active():
            return
        self.node.data["header"] = btn.get_active()
        self._changed_struct(None)


ROW_TYPES = {"heading": TextRow, "bullet": TextRow, "table": TableRow}
