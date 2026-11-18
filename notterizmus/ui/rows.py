"""Row widgets, one per node kind. Register new kinds in ROW_TYPES."""
from __future__ import annotations

import weakref

from gi.repository import Gdk, GLib, GObject, Gtk

from .. import drawing
from . import drawing_web
from .richtext import RichText


PREVIEW_MAX = (760, 600)


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


def shortcut_keyval(keyval, keycode, state):
    """The keyval a Ctrl/Alt shortcut means. On a non-Latin layout (Bulgarian) Ctrl+A
    arrives as Ctrl+Cyrillic_a; like GTK's own shortcuts, fall back to the Latin letter
    on the same key of the first layout, so the editor's shortcuts work there too
    (otherwise GtkTextView's would run instead: Ctrl+A selected one item's text)."""
    if not state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
        return keyval
    ch = chr(Gdk.keyval_to_unicode(keyval) or 0)
    if not ch.isalpha() or ch.isascii():
        return keyval
    display = Gdk.Display.get_default()
    ok, keys, keyvals = display.map_keycode(keycode) if display and keycode else (False, [], [])
    if not ok:
        return keyval
    level = 1 if state & Gdk.ModifierType.SHIFT_MASK else 0
    latin = [(k.group, k.level != level, kv) for k, kv in zip(keys, keyvals)
             if 0 < Gdk.keyval_to_unicode(kv) < 0x80 and chr(Gdk.keyval_to_unicode(kv)).isalpha()]
    return min(latin)[2] if latin else keyval


def row_of(widget):
    """The row a widget is in, or None.

    Handlers on a row's widgets look their row up this way when the event comes; they must
    not hold it, nor the widget they are on. Such a handler belongs to a widget the row
    owns, so holding the row makes a cycle through GTK, where Python's garbage collector
    can't see it, and the row would never be freed (R29c): every row of every chapter
    opened, with its text and a drawing's picture. Holding the editor is fine."""
    return widget.get_ancestor(_PrefixRow)


def _in_row(f):
    """A signal handler that calls f(row, widget, source, *args): `widget` is the one the
    signal came from (the controller's widget for a controller) and `row` the row it is
    in, both found when the signal comes (see row_of). Outside a row it does nothing."""
    def handler(source, *args):
        widget = source.get_widget() if isinstance(source, Gtk.EventController) else source
        row = row_of(widget) if widget is not None else None
        return False if row is None else f(row, widget, source, *args)
    return handler


def wire_view(editor, view):
    """Shared input handling for every RichText that belongs to a row."""
    keys = Gtk.EventControllerKey()
    keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    keys.connect("key-pressed", _in_row(lambda row, v, _c, kv, kc, st:
                                        editor.on_key(row, v, shortcut_keyval(kv, kc, st), st)))
    keys.connect("key-released", lambda _c, kv, _kc, st: editor.on_key_released(kv))
    view.add_controller(keys)
    focus = Gtk.EventControllerFocus()
    focus.connect("enter", _in_row(lambda row, v, _c: editor.set_current(row.node, v)))
    view.add_controller(focus)
    click = Gtk.GestureClick(button=0)
    click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    click.connect("pressed", _in_row(lambda row, v, g, _n, x, y: editor.on_click(row, v, g, x, y)))
    view.add_controller(click)
    view.connect("paste-clipboard", _in_row(lambda row, v, _v: (v.stop_emission_by_name("paste-clipboard"),
                                                                editor.paste(row, v))))
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
        click.connect("released", _in_row(lambda row, *_: editor.show_item_menu(row)))
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
        self.view.connect("content-changed", _in_row(lambda row, v, _v: row._on_changed(v)))
        wire_view(editor, self.view)
        self.append(self.view)
        self._markup = None
        self.connect("map", lambda r: GLib.timeout_add(20, lambda: (r.view.queue_resize(), False)[1]))

    def set_prefix(self, segs):
        """The text takes the row's width beside the prefix, so a wider prefix (Tab adds a
        level) narrows it: tell the view, so that frame already has the re-wrapped height."""
        markup = _prefix_markup(segs)
        if markup == self._markup:
            return
        self._markup = markup
        laid_out = self.view.get_width() > 1
        before = self.prefix.measure(Gtk.Orientation.HORIZONTAL, -1)[1] if laid_out else 0
        self.prefix.set_markup(markup)
        if laid_out:
            self.view.expect_width_change(before - self.prefix.measure(Gtk.Orientation.HORIZONTAL, -1)[1])

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
        for label, tip, name in (("+ Row", "Add row below", "add_row"),
                                 ("+ Column", "Add column right", "add_col"),
                                 ("− Row", "Remove row", "del_row"),
                                 ("− Column", "Remove column", "del_col")):
            b = Gtk.Button(label=label, tooltip_text=tip)
            b.add_css_class("flat")
            b.connect("clicked", _in_row(lambda row, *_, name=name: getattr(row, name)()))
            bar.append(b)
        self.header_btn = Gtk.ToggleButton(label="Header row", active=bool(node.data.get("header")))
        self.header_btn.add_css_class("flat")
        self.header_btn.connect("toggled", _in_row(lambda row, btn, _b: row._toggle_header(btn)))
        bar.append(self.header_btn)
        rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Delete table")
        rm.add_css_class("flat")
        rm.connect("clicked", _in_row(lambda row, *_: editor.delete_items([row.node])))
        bar.append(rm)
        self.grid = Gtk.Grid(halign=Gtk.Align.START)
        self.grid.add_css_class("ntz-table")
        box.append(bar)
        box.append(self.grid)
        self.append(box)
        # Text views inside a Grid finish their layout after the first measure;
        # re-queue so the grid picks up the real cell heights.
        self.connect("map", lambda r: GLib.timeout_add(30, r._requeue))
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
                rt.connect("content-changed", _in_row(lambda row, v, _v, r=r, c=c: row._cell_changed(v, r, c)))
                keys = Gtk.EventControllerKey()
                keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
                keys.connect("key-pressed", _in_row(lambda row, v, k, kv, kc, st, r=r, c=c:
                                                    row._cell_key(k, kv, kc, st, v, r, c)))
                rt.add_controller(keys)
                fc = Gtk.EventControllerFocus()
                fc.connect("enter", _in_row(lambda row, v, fc, r=r, c=c: row._cell_focus(fc, v, r, c)))
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

    def _cell_key(self, _ctl, keyval, keycode, state, rt, r, c):
        name = Gdk.keyval_name(shortcut_keyval(keyval, keycode, state))
        ctrl, shift, alt = _mods(state)
        nrows, ncols = len(self.rows), len(self.rows[0]) if self.rows else 0
        if self.editor.common_key(rt, name, ctrl, shift, alt):
            return True
        if name == "Escape" and self.editor.on_escape is not None and self.editor.on_escape():
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


class _Preview(GObject.Object, Gdk.Paintable):
    """A drawing's PNG at the size of the drawing (the PNG has more pixels than that, so
    it stays sharp on dense screens), or smaller for a drawing larger than PREVIEW_MAX."""

    def __init__(self, texture):
        super().__init__()
        self.texture = texture
        w, h = texture.get_width() / drawing.PREVIEW_SCALE, texture.get_height() / drawing.PREVIEW_SCALE
        fit = min(1.0, PREVIEW_MAX[0] / max(w, 1), PREVIEW_MAX[1] / max(h, 1))
        self.width, self.height = max(1, round(w * fit)), max(1, round(h * fit))

    def do_snapshot(self, snapshot, width, height):
        self.texture.snapshot(snapshot, width, height)

    def do_get_intrinsic_width(self):
        return self.width

    def do_get_intrinsic_height(self):
        return self.height

    def do_get_intrinsic_aspect_ratio(self):
        return self.texture.get_width() / max(1, self.texture.get_height())

    def do_get_flags(self):
        return Gdk.PaintableFlags.SIZE | Gdk.PaintableFlags.CONTENTS


class DrawingRow(_PrefixRow):
    """An Excalidraw drawing: its picture, with buttons to edit and delete it. The picture
    comes from the preview cache (drawing.py), or is made again when it isn't there."""

    def __init__(self, editor, node):
        super().__init__(editor, node)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        bar = Gtk.Box(spacing=2)
        bar.add_css_class("table-bar")
        edit = Gtk.Button(label="Edit Drawing", tooltip_text="Open the drawing in Excalidraw (or double-click it)")
        # (a single click on the picture selects it)
        edit.add_css_class("flat")
        edit.connect("clicked", _in_row(lambda row, *_: editor.edit_drawing(row.node)))
        bar.append(edit)
        copy = Gtk.Button(label="Copy", tooltip_text="Copy only this drawing, to paste it into TopCoding or here")
        copy.add_css_class("flat")
        copy.connect("clicked", _in_row(lambda row, *_: editor.copy_drawing(row.node)))
        bar.append(copy)
        rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Delete drawing")
        rm.add_css_class("flat")
        rm.connect("clicked", _in_row(lambda row, *_: editor.delete_items([row.node])))
        bar.append(rm)
        self.picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.SCALE_DOWN,
                                   halign=Gtk.Align.START, visible=False)
        self.picture.add_css_class("ntz-drawing")
        self.picture.set_cursor_from_name("pointer")
        click = Gtk.GestureClick(button=1)
        click.connect("pressed", _in_row(lambda row, _p, g, n, x, y: row._clicked(g, n, x, y)))
        self.picture.add_controller(click)
        self.note = Gtk.Label(xalign=0, wrap=True)
        self.note.add_css_class("dim-label")
        box.append(bar)
        box.append(self.picture)
        box.append(self.note)
        self.append(box)
        self._key = None
        self.reload()

    def _clicked(self, _gesture, n_press, _x, _y):
        """A click selects the drawing (then Ctrl+C, Ctrl+X and Delete act on it alone); a
        double-click opens it."""
        if n_press == 2:
            self.editor.edit_drawing(self.node)
        else:
            self.editor.set_selection([self.node])

    def reload(self):
        key = drawing.preview_key(self.node.data)
        if key == self._key:
            return
        self._key = key
        if drawing.is_empty(self.node.data):
            self._say("An empty drawing.")
        elif not self._show():
            self._say("Making the picture of this drawing…")
            me = weakref.ref(self)  # a row gone meanwhile needs no picture
            drawing_web.render(self.node.data, lambda _png, key=key: (r := me()) is not None and r._rendered(key))

    def _show(self):
        try:
            texture = Gdk.Texture.new_from_filename(str(drawing.preview_path(self.node.data)))
        except GLib.Error:
            return False
        preview = _Preview(texture)
        self.picture.set_paintable(preview)
        # Its full height is its minimum too. A picture that may shrink is the first thing
        # the outline squeezes when it is a little short of room (text rows never give
        # way), and in a long chapter it was squeezed to nothing.
        self.picture.set_size_request(-1, preview.height + 2)  # + the frame's border (style.css)
        self.picture.set_visible(True)
        self.note.set_visible(False)
        return True

    def _say(self, text):
        self.picture.set_visible(False)
        self.picture.set_paintable(None)
        self.picture.set_size_request(-1, -1)
        self.note.set_text(text)
        self.note.set_visible(True)

    def _rendered(self, key):
        if key != self._key or self._show():  # edited again meanwhile: that picture is on its way
            return
        n = sum(1 for e in self.node.data.get("elements", []) if not e.get("isDeleted"))
        why = "" if drawing_web.available() else f" {drawing_web.MISSING}."
        self._say(f"A drawing with {n} element{'s' if n != 1 else ''}; its picture can't be shown.{why}")

    def focus(self, offset=0):
        pass

    def cursor_offset(self):
        return None


class UnknownRow(_PrefixRow):
    """A block type this version doesn't know, written by a newer Notterizmus. Its data is
    saved back unchanged; here it's a read-only note, left out of Copy for TopCoding."""

    def __init__(self, editor, node):
        super().__init__(editor, node)
        box = Gtk.Box(spacing=8, hexpand=True)
        box.add_css_class("ntz-unknown")
        box.append(Gtk.Image(icon_name="dialog-information-symbolic", valign=Gtk.Align.START))
        self.label = Gtk.Label(xalign=0, wrap=True, hexpand=True)
        self.label.add_css_class("dim-label")
        box.append(self.label)
        rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Delete this block",
                        valign=Gtk.Align.START)
        rm.add_css_class("flat")
        rm.connect("clicked", _in_row(lambda row, *_: editor.delete_items([row.node])))
        box.append(rm)
        self.append(box)
        self.reload()

    def reload(self):
        self.label.set_text(f"A “{self.node.kind}” block made with a newer version of Notterizmus. "
                            "It's kept in the file unchanged, but it can't be shown or edited here, "
                            "and Copy for TopCoding leaves it out.")

    def focus(self, offset=0):
        pass

    def cursor_offset(self):
        return None


ROW_TYPES = {"heading": TextRow, "bullet": TextRow, "table": TableRow, "drawing": DrawingRow}


def row_type(kind):
    return ROW_TYPES.get(kind, UnknownRow)
