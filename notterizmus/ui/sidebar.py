"""The chapter sidebar: books from the notes folder, each with its chapters."""
from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, GObject, Gtk, Pango

from .. import library


class ChapterSidebar(Adw.Bin):
    __gtype_name__ = "NtzChapterSidebar"
    __gsignals__ = {"open-chapter": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self):
        super().__init__()
        self.books = []
        self.current = None      # path of the open chapter
        self.expanded = set()    # book names shown open
        self._root = None

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
        sw = Gtk.ScrolledWindow(child=self.list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        tv.set_content(sw)
        self.set_child(tv)

    # -- contents -------------------------------------------------------------------------

    def reload(self, root=None, current=None):
        """Rescan the notes folder; current is the open chapter's path (or None)."""
        if root is not None:
            self._root = root
        self.current = Path(current) if current else None
        self.books = library.scan(self._root) if self._root else []
        book, _i = library.find(self.books, self.current)
        if book is not None:
            self.expanded.add(book.name)
        self._rebuild()

    def _rebuild(self):
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
        row._path = None
        return row

    def _chapter_row(self, ch):
        box = Gtk.Box(spacing=8, margin_start=20)
        num = Gtk.Label(label="" if ch.number is None else str(ch.number), width_chars=2, xalign=1)
        num.add_css_class("dim-label")
        num.add_css_class("numeric")
        box.append(num)
        box.append(Gtk.Label(label=ch.label, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
        row = Gtk.ListBoxRow(child=box, tooltip_text=ch.path.name)
        row._book = None
        row._path = ch.path
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
