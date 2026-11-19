"""Earlier versions (R4): copies kept on open and while editing, restored from a dialog."""
from datetime import datetime, timedelta
from pathlib import Path

from notterizmus import backups, paths
from notterizmus.export import to_plain
from notterizmus.guide import b, h
from notterizmus.layout import layout
from notterizmus.model import Document

from . import support as ui


class BackupsTest(ui.UITestCase):
    def tearDown(self):
        while (dlg := self.win.get_visible_dialog()) is not None:
            dlg.force_close()
            ui.wait_for(lambda: self.win.get_visible_dialog() is not dlg, "a dialog to close")

    def folder(self):
        return backups.folder_for(self.win.doc.path, self.win.notes_root_path(), paths.backups_dir())

    def texts(self):
        return [Document.load(c.path).root.children[0].text for c in backups.list_backups(self.folder())]

    def test_opening_a_chapter_keeps_a_copy(self):
        ui.open_chapter([h("As opened")], book="Backups open")
        self.assertEqual(self.texts(), ["As opened"])

    def test_getting_started_has_no_copies(self):
        self.win.lookup_action("guide").activate(None)
        ui.settle()
        root = paths.backups_dir()
        self.assertFalse(any("Getting Started" in str(p) for p in root.rglob("*")) if root.exists() else False)

    def test_saving_keeps_the_version_it_overwrites_at_most_every_interval(self):
        doc = ui.open_chapter([h("v1")], book="Backups interval")
        view = ui.row(doc.root.children[0]).view
        ui.type_text(view, " v2")
        self.win.save(quiet=True)
        self.assertEqual(self.texts(), ["v1"], "within the interval: no new copy")
        # the interval has passed: the copy was taken that long ago
        first, = backups.list_backups(self.folder())
        first.path.rename(first.path.with_name(
            backups._name(first.when - timedelta(seconds=backups.BACKUP_EVERY + 1))))
        ui.type_text(view, " v3")
        self.win.save(quiet=True)
        self.assertEqual(self.texts(), ["v1 v2", "v1"])

    def test_earlier_versions_shows_at_once_and_fills_in_each_copy(self):
        """Every copy was read and compared before the dialog showed: 0.9 s for 54 copies of
        a 4 MB chapter (CR32). The details come a moment later now."""
        doc = ui.open_chapter([h("now", b("a note"))], book="Backups details")
        self.win.on_versions()
        dlg = self.win.get_visible_dialog()
        lb = next(w for w in ui.walk(dlg) if isinstance(w, ui.Gtk.ListBox))
        row = lb.get_row_at_index(0)
        self.assertEqual(row.get_subtitle(), "…", "shown before its copy is read")
        ui.wait_for(lambda: row.get_subtitle() != "…", "the copy's details")
        self.assertEqual(row.get_subtitle(), "2 items · same as now")
        self.assertEqual(Path(row._backup.path).read_bytes(), Path(doc.path).read_bytes())

    def test_restoring_an_earlier_version_and_undoing_it(self):
        doc = ui.open_chapter([h("now")], book="Backups restore")
        folder = self.folder()
        for i, text in enumerate(["older", "old"]):
            earlier = Document.load(doc.path)
            earlier.root.children[0].runs = [ui_run(text)]
            tmp = folder / "tmp.notz"
            earlier.save(tmp)
            target = folder / f"{(datetime.now() - timedelta(hours=2 - i)).strftime('%Y-%m-%dT%H-%M-%S')}.notz"
            tmp.rename(target)
        self.win.lookup_action("versions").activate(None)
        ui.wait_for(lambda: self.win.get_visible_dialog() is not None, "Earlier Versions")
        dlg = self.win.get_visible_dialog()
        rows = [w for w in ui.walk(dlg) if isinstance(w, ui.Adw.ActionRow)]
        ui.wait_for(lambda: "…" not in [r.get_subtitle() for r in rows], "the copies' details")  # (CR32)
        self.assertEqual([r.get_subtitle() for r in rows], ["1 item · same as now", "1 item", "1 item"])
        self.assertRegex(rows[0].get_title(), r"^\d\d:\d\d$")
        self.assertEqual(rows[0].get_header().get_label(), "Today")
        listbox = rows[0].get_parent()
        listbox.select_row(rows[2])  # the oldest
        buf = self.win._versions_preview.get_buffer()
        self.assertEqual(buf.get_text(*buf.get_bounds(), True),
                         to_plain(layout(Document.load(rows[2]._backup.path).root, self.win.rules)))
        restore = next(w for w in ui.walk(dlg) if isinstance(w, ui.Gtk.Button) and w.get_label() == "Restore")
        restore.emit("clicked")
        ui.wait_for(lambda: self.win.get_visible_dialog() is None, "the dialog to close")
        ui.settle()
        self.assertEqual(self.win.doc.root.children[0].text, "older")
        self.assertEqual(self.win.doc.chapter_title, doc.chapter_title, "only the content changes")
        ui.press(ui.row(self.win.doc.root.children[0]).view, "z", ctrl=True)
        self.assertEqual(self.win.doc.root.children[0].text, "now")

    def test_copies_follow_a_renamed_chapter(self):
        doc = ui.open_chapter([h("kept")], title="Before", book="Backups rename")
        before = self.folder()
        self.assertTrue(before.is_dir())
        self.win.apply_chapter_props(doc.path, doc.path.parent, doc.chapter_no, "After")
        self.assertFalse(before.exists())
        self.assertEqual(self.texts(), ["kept"])
        self.assertTrue(self.folder().name.endswith("After"))


def ui_run(text):
    from notterizmus.model import Run
    return Run(text)


class VersionsByDayTest(ui.UITestCase):
    def tearDown(self):
        while (dlg := self.win.get_visible_dialog()) is not None:
            dlg.force_close()
            ui.wait_for(lambda: self.win.get_visible_dialog() is not dlg, "a dialog to close")

    def test_copies_are_grouped_by_day(self):
        doc = ui.open_chapter([h("days")], book="Backups days")
        folder = backups.folder_for(doc.path, self.win.notes_root_path(), paths.backups_dir())
        for days in (1, 10):
            when = datetime.now() - timedelta(days=days)
            (folder / f"{when:%Y-%m-%dT%H-%M-%S}.notz").write_bytes(doc.path.read_bytes())
        self.win.lookup_action("versions").activate(None)
        ui.wait_for(lambda: self.win.get_visible_dialog() is not None, "Earlier Versions")
        rows = [w for w in ui.walk(self.win.get_visible_dialog()) if isinstance(w, ui.Adw.ActionRow)]
        headers = [r.get_header().get_label() if r.get_header() else None for r in rows]
        ten_days = f"{(datetime.now() - timedelta(days=10)):%Y-%m-%d}"
        self.assertEqual(headers, ["Today", "Yesterday", ten_days])
