"""The chapter sidebar: books from the notes folder, each with its chapters."""
from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Graphene, Gtk, Pango

from .. import library



# A chapter row's drag handlers find the row through their controller when a drag starts.
# Holding it (or its chapter) made a cycle through GTK, where Python's garbage collector can't
# see it, and every rebuild of the list left the chapter rows behind (CR18 in CODE_REVIEW.md).

def _drag_prepare(source, _x, _y):
    return Gdk.ContentProvider.new_for_value(str(source.get_widget()._path))


def _drag_begin(source, _drag):
    source.set_icon(Gtk.WidgetPaintable.new(source.get_widget()), 20, 10)


class ChapterSidebar(Adw.Bin):
    __gtype_name__ = "NtzChapterSidebar"
    __gsignals__ = {"open-chapter": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self):
        super().__init__()
        self.books = []
        self.current = None      # path of the open chapter
        self.expanded = set()    # book names shown open
        self._root = None
        self.popup = None        # set by the window: popup(menu_model, widget) shows a menu
        self.on_reorder = None   # set by the window: on_reorder(chapters in their new order)

        tv = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Chapters"))
        tv.add_top_bar(header)

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("navigation-sidebar")
        empty = Gtk.Label(label="No chapters yet.\nNew Chapter (Ctrl+N) adds one.", justify=Gtk.Justification.CENTER,
                          wrap=True, margin_top=24, margin_start=12, margin_end=12)
        empty.add_css_class("dim-label")
        self.list.set_placeholder(empty)
        self.list.connect("row-activated", self._activated)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key)
        self.list.add_controller(keys)
        menu_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        menu_click.connect("pressed", self._right_click)
        self.list.add_controller(menu_click)
        drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        drop.connect("motion", self._drop_motion)
        drop.connect("leave", lambda *_: self._mark_drop(None, False))
        drop.connect("drop", self._drop)
        self.list.add_controller(drop)
        self._drop_row = None
        sw = Gtk.ScrolledWindow(child=self.list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        tv.set_content(sw)
        self.set_child(tv)

    # -- contents -------------------------------------------------------------------------

    def reload(self, root=None, current=None):
        """Rescan the notes folder; current is the open chapter's path (or None)."""
        if root is not None:
            self._root = root
        current = Path(current) if current else None
        books = library.scan(self._root) if self._root else []
        book, _i = library.find(books, current)
        unchanged = self._shape(books) == self._shape(self.books) and current == self.current \
            and (book is None or book.name in self.expanded)
        self.current, self.books = current, books
        if book is not None:
            self.expanded.add(book.name)
        if not unchanged:  # rebuilding on every window activation would drop keyboard focus
            self._rebuild()

    @staticmethod
    def _shape(books):
        return [(b.name, [c.path for c in b.chapters]) for b in books]

    def _rebuild(self):
        had = self.focused_row()
        had_key = (had._book, str(had._path)) if had is not None else None
        while (row := self.list.get_row_at_index(0)) is not None:
            self.list.remove(row)
        selected = None
        cur_book, cur_i = library.find(self.books, self.current)
        for book in self.books:
            is_open = book.name in self.expanded
            self.list.append(self._book_row(book, is_open))
            if not is_open:
                continue
            for i, ch in enumerate(book.chapters):
                row = self._chapter_row(ch)
                self.list.append(row)
                if book is cur_book and i == cur_i:
                    selected = row
        if selected is not None:
            self.list.select_row(selected)
        else:
            self.list.unselect_all()
        if had_key is not None:
            again = next((r for r in self.rows() if (r._book, str(r._path)) == had_key), None)
            if again is not None:
                again.grab_focus()

    def _book_row(self, book, is_open):
        box = Gtk.Box(spacing=6)
        box.append(Gtk.Image(icon_name="pan-down-symbolic" if is_open else "pan-end-symbolic"))
        name = Gtk.Label(label=book.name, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        name.add_css_class("heading")
        box.append(name)
        count = Gtk.Label(label=str(len(book.chapters)))
        count.add_css_class("dim-label")
        count.add_css_class("numeric")
        box.append(count)
        row = Gtk.ListBoxRow(child=box, selectable=False, tooltip_text=book.name)
        row._book = book.name
        row._folder = book.path
        row._path = None
        return row

    def _chapter_row(self, ch):
        box = Gtk.Box(spacing=8, margin_start=20)
        num = Gtk.Label(label="" if ch.number is None else str(ch.number), width_chars=2, xalign=1)
        num.add_css_class("dim-label")
        num.add_css_class("numeric")
        box.append(num)
        box.append(Gtk.Label(label=ch.label, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
        row = Gtk.ListBoxRow(child=box, tooltip_text=f"{ch.path.name}\nDrag to reorder · right-click for more")
        row._book = None
        row._folder = ch.path.parent
        row._path = ch.path
        drag = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        drag.connect("prepare", _drag_prepare)
        drag.connect("drag-begin", _drag_begin)
        row.add_controller(drag)
        return row

    # -- input ------------------------------------------------------------------------------

    def _activated(self, _lb, row):
        if row._book is not None:
            name = row._book
            self.expanded.symmetric_difference_update({name})
            self._rebuild()
            book_row = next((r for r in self.rows() if r._book == name), None)
            if book_row is not None:
                book_row.grab_focus()  # keep keyboard focus on the book that was toggled
            return
        self.emit("open-chapter", str(row._path))

    def focus_path(self, path):
        """Put keyboard focus on the chapter row for path (after the list was rebuilt)."""
        row = next((r for r in self.rows() if r._path and library.same_file(r._path, path)), None)
        if row is not None:
            row.grab_focus()

    def focused_row(self):
        row = self.list.get_focus_child()
        return row if isinstance(row, Gtk.ListBoxRow) else None

    # -- menus and keys -----------------------------------------------------------------------

    def menu_for(self, row):
        m = Gio.Menu()
        if row._path is None:
            item = Gio.MenuItem.new("Rename Book…", None)
            item.set_action_and_target_value("win.book-rename", GLib.Variant.new_string(str(row._folder)))
            m.append_item(item)
            return m
        target = GLib.Variant.new_string(str(row._path))
        s1, s2, s3 = Gio.Menu(), Gio.Menu(), Gio.Menu()
        for menu, label, action in ((s1, "Chapter Properties…", "win.chapter-props"),
                                    (s2, "Move Up", "win.chapter-up"), (s2, "Move Down", "win.chapter-down"),
                                    (s3, "Move to Trash", "win.chapter-trash")):
            item = Gio.MenuItem.new(label, None)
            item.set_action_and_target_value(action, target)
            menu.append_item(item)
        for s in (s1, s2, s3):
            m.append_section(None, s)
        return m

    def show_menu(self, row):
        if self.popup is not None and row is not None:
            self.popup(self.menu_for(row), row)

    def _right_click(self, gesture, _n, _x, y):
        row = self.list.get_row_at_y(int(y))
        if row is not None:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            row.grab_focus()
            self.show_menu(row)

    def _key(self, _ctl, keyval, _code, state):
        name = Gdk.keyval_name(keyval)
        alt = bool(state & Gdk.ModifierType.ALT_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        row = self.focused_row()
        if row is None:
            return False
        if name == "Menu" or (shift and name == "F10"):
            self.show_menu(row)
            return True
        if row._path is None:
            return False
        target = GLib.Variant.new_string(str(row._path))
        if alt and name in ("Up", "Down"):
            self.activate_action("win.chapter-up" if name == "Up" else "win.chapter-down", target)
            return True
        if name == "Delete" and not alt:
            self.activate_action("win.chapter-trash", target)
            return True
        return False

    # -- drag to reorder ------------------------------------------------------------------------

    def _drop_place(self, y):
        """(row, after) for a drop at y: before or after a chapter row."""
        row = self.list.get_row_at_y(int(y))
        if row is None or row._path is None:
            return None, False
        ok, top = row.compute_point(self.list, Graphene.Point().init(0, 0))
        after = ok and y > top.y + row.get_height() / 2
        return row, after

    def _mark_drop(self, row, after):
        if self._drop_row is not None:
            self._drop_row.remove_css_class("drop-before")
            self._drop_row.remove_css_class("drop-after")
        self._drop_row = row
        if row is not None:
            row.add_css_class("drop-after" if after else "drop-before")

    def _drop_motion(self, _target, _x, y):
        row, after = self._drop_place(y)
        self._mark_drop(row, after)
        return Gdk.DragAction.MOVE if row is not None else 0

    def _drop(self, _target, value, _x, y):
        row, after = self._drop_place(y)
        self._mark_drop(None, False)
        return row is not None and self.drop_chapter(value, row._path, after)

    def drop_chapter(self, src, target, after=False):
        """Move chapter src next to chapter target in the same book (reorders it)."""
        book, i = library.find(self.books, src)
        tbook, _j = library.find(self.books, target)
        if book is None or tbook is not book or library.same_file(src, target):
            return False  # only within one book; moving to another book is in Chapter Properties
        moving = book.chapters[i]
        order = [c for c in book.chapters if c is not moving]
        j = next(k for k, c in enumerate(order) if library.same_file(c.path, target))
        order.insert(j + 1 if after else j, moving)
        if self.on_reorder is not None:
            self.on_reorder(order, moving.path)
        return True

    def rows(self):
        i = 0
        while (r := self.list.get_row_at_index(i)) is not None:
            yield r
            i += 1

    def chapter_rows(self):
        """[(label, path, selected)] of the chapter rows shown (used by the tests)."""
        return [(list(_labels(r))[-1].get_text(), r._path, r.is_selected())
                for r in self.rows() if r._path is not None]


def _labels(widget):
    c = widget.get_first_child()
    while c is not None:
        if isinstance(c, Gtk.Label):
            yield c
        yield from _labels(c)
        c = c.get_next_sibling()
