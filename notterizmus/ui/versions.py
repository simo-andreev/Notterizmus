"""Earlier Versions (R4): pick a kept copy of the open chapter, preview it, restore it.
Out of window.py's on_versions (CR49 in CODE_REVIEW.md)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from gi.repository import Adw, GLib, Gtk

from ..export import to_plain
from ..layout import layout
from ..model import Document


class VersionRow(Adw.ActionRow):
    """A kept copy in Earlier Versions (backup: a backups.Backup)."""

    def __init__(self, backup, **props):
        super().__init__(**props)
        self.backup = backup


class VersionsDialog(Adw.Dialog):
    """The kept copies (backups, newest first) of the chapter at chapter_path, under a
    heading per day, with a preview of the one selected as plain text. Restore, or
    activating a row, closes it and calls on_restore(the copy's path)."""

    def __init__(self, backups, chapter_path, rules, on_restore):
        super().__init__(title="Earlier Versions", content_width=860, content_height=600)
        self.rules, self.on_restore = rules, on_restore
        tv = Adw.ToolbarView()
        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        self.restore = Gtk.Button(label="Restore", sensitive=False, css_classes=["suggested-action"])
        header.pack_start(cancel)
        header.pack_end(self.restore)
        tv.add_top_bar(header)
        if not backups:
            tv.set_content(Adw.StatusPage(
                icon_name="document-open-recent-symbolic", title="No Earlier Versions Yet",
                description="A copy is kept when you open a chapter, and every 10 minutes while you edit it."))
        else:
            self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["navigation-sidebar"])
            rows = []
            for b in backups:
                row = VersionRow(b, title=f"{b.when:%H:%M}", subtitle="…", tooltip_text=_when(b.when))
                self.list.append(row)
                rows.append(row)
            self._fill_in(chapter_path, rows)
            self.list.set_header_func(_day_header)
            self.preview = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                        left_margin=16, right_margin=16, top_margin=12, bottom_margin=12)
            self.list.connect("row-selected", self._selected)
            paned = Gtk.Paned(position=250, shrink_start_child=False, resize_start_child=False,
                              start_child=Gtk.ScrolledWindow(child=self.list, hscrollbar_policy=Gtk.PolicyType.NEVER),
                              end_child=Gtk.ScrolledWindow(child=self.preview, hexpand=True))
            tv.set_content(paned)
            self.list.select_row(self.list.get_row_at_index(0))
            self.restore.connect("clicked", lambda *_: self._restore())
            self.list.connect("row-activated", lambda *_: self._restore())
        self.set_child(tv)

    def _selected(self, _lb, row):
        self.restore.set_sensitive(row is not None)
        if row is None:
            return
        try:
            text = to_plain(layout(Document.load(row.backup.path).root, self.rules))
        except (OSError, ValueError) as e:
            text = f"This copy can't be read: {e}"
            self.restore.set_sensitive(False)
        self.preview.get_buffer().set_text(text)

    def _restore(self):
        row = self.list.get_selected_row()
        self.close()
        if row is not None:
            self.on_restore(row.backup.path)

    def _fill_in(self, chapter_path, rows):
        """Each copy's item count, and whether it is the chapter as it is now, a row at a time
        once the dialog shows: read before it, 54 copies of a 4 MB chapter kept it from
        showing for 0.9 s (CR32 in CODE_REVIEW.md)."""
        try:
            now = Path(chapter_path).read_bytes()
        except OSError:
            now = None
        pending = iter(rows)
        open_ = [True]
        self.connect("closed", lambda *_: open_.__setitem__(0, False))

        def next_row():
            row = next(pending, None) if open_[0] else None
            if row is None:
                return GLib.SOURCE_REMOVE
            row.set_subtitle(_copy_summary(row.backup.path, now))
            return GLib.SOURCE_CONTINUE

        GLib.idle_add(next_row)


def _day_header(row, before):
    """A heading above the first copy of each day: Today, Yesterday, 2026-11-02."""
    day = row.backup.when.date()
    if before is not None and before.backup.when.date() == day:
        row.set_header(None)
        return
    label = Gtk.Label(label=_day(day), xalign=0, margin_start=12, margin_top=12, margin_bottom=4)
    label.add_css_class("heading")
    label.add_css_class("dim-label")
    row.set_header(label)


def _day(day):
    """'Today', 'Yesterday' or '2026-11-02'."""
    if day == date.today():
        return "Today"
    if day == date.today() - timedelta(days=1):
        return "Yesterday"
    return f"{day:%Y-%m-%d}"


def _copy_summary(path, now):
    """'12 items', '12 items · same as now' (now: the chapter file's bytes) or "can't be read"."""
    try:
        data = Path(path).read_bytes()
        items = sum(1 for n in Document.from_json(json.loads(data)).root.walk() if n.kind != "root")
    except (OSError, ValueError, RecursionError):
        return "can't be read"
    return f"{items} item{'s' if items != 1 else ''}" + (" · same as now" if data == now else "")


def _when(dt):
    """'Today 14:05', 'Yesterday 09:30' or '2026-11-02 18:40'."""
    return f"{_day(dt.date())} {dt:%H:%M}"
