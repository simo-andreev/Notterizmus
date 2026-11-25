"""The window's saving (CR38 in CODE_REVIEW.md): autosave 800 ms after a change, saving
before anything reads the chapter from disk, Earlier Versions copies, and what to do when
another program changed the file (CR10, R16).

Uses the window's doc, editor, state, toast() and _is_guide(); keeps _save_src (the
waiting autosave) and _disk_dialog (the question about a change on disk)."""
from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, GLib

from .. import backups, paths
from ..model import Document
from .helpers import notes_root


class WindowSaving:
    def _backup_folder(self):
        return backups.folder_for(self.doc.path, notes_root(), paths.backups_dir())

    def _backup(self, force=False):
        """Keep a copy of the chapter as it is on disk (never in the way of saving)."""
        if not self.doc or not self.doc.path or self._is_guide():
            return
        try:
            backups.backup(self.doc.path, self._backup_folder(), force=force)
        except OSError:
            pass

    def _flush_save(self):
        """Write the open chapter now: file operations read chapters from disk. Nothing
        can wait for an answer here, so a version changed on disk goes to Earlier Versions."""
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        self.save(quiet=True, ask=False)

    def _save_pending(self):
        """Write the open chapter now if an autosave is waiting: before another chapter
        replaces it, or the autosave would write that one instead and these edits would be
        lost (CR4 in CODE_REVIEW.md). An open question about a change on disk counts too:
        an autosave asked it, so its edits aren't written yet."""
        if self._save_src or self._disk_dialog is not None:
            self._flush_save()

    def _schedule_save(self):
        if self._save_src:
            GLib.source_remove(self._save_src)
        self._save_src = GLib.timeout_add(800, self._autosave)

    def _autosave(self):
        self._save_src = None
        self.save(quiet=True)
        return False

    def save(self, quiet=False, ask=True):
        """Write the open chapter. If another program changed its file since it was opened
        or last saved, ask first (Reload or Keep Mine) instead of overwriting that version;
        with ask=False, where no answer can wait, keep this one and put the other in Earlier
        Versions (CR10 in CODE_REVIEW.md, R16)."""
        if not self.doc:
            return
        changed = self.doc.changed_on_disk()
        if changed and ask:
            self._ask_about_disk_change()
            return
        if changed:
            self._keep_disk_version()
        else:
            self._backup()  # at most every few minutes: the version about to be overwritten
        try:
            self.doc.save()
            if not quiet:
                self.toast("Saved")
        except OSError as e:
            self.toast(f"Save failed: {e}")

    def _keep_disk_version(self):
        """Put the file another program changed in Earlier Versions before this version
        replaces it: always, even in the second the last copy was taken."""
        if self.doc.path and not self._is_guide():
            try:
                backups.keep(Path(self.doc.path).read_bytes(), self._backup_folder())
            except OSError:
                pass

    def _ask_about_disk_change(self):
        if self._disk_dialog is not None:
            return
        doc = self.doc
        label = doc.chapter_title or f"Chapter {doc.chapter_no}"
        dlg = Adw.AlertDialog(
            heading="Changed on Disk",
            body=f"Another program changed “{label}” since it was opened here, a sync tool perhaps. "
                 "Reload that version, or keep the one you have here? The other one stays in Earlier "
                 "Versions either way.")
        dlg.add_response("keep", "Keep Mine")
        dlg.add_response("reload", "Reload")
        dlg.set_response_appearance("reload", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("reload")
        dlg.set_close_response("later")  # Escape: nothing now; the next save asks again
        dlg.connect("response", lambda _d, response: self._on_disk_change(doc, response))
        dlg.connect("closed", self._disk_dialog_closed)  # however it closes, or no save would write again
        self._disk_dialog = dlg
        dlg.present(self)

    def _disk_dialog_closed(self, dlg):
        if self._disk_dialog is dlg:
            self._disk_dialog = None

    def _on_disk_change(self, doc, response):
        if doc is not self.doc:
            return
        if response == "keep":
            self.save(quiet=True, ask=False)
            self.toast("Saved yours: the other version is in Earlier Versions")
        elif response == "reload":
            self._reload_from_disk()

    def _reload_from_disk(self):
        """Replace the open chapter with its file, as one undoable step; the version it
        replaces goes to Earlier Versions too."""
        doc = self.doc
        try:
            fresh = Document.load(doc.path)
        except (OSError, ValueError) as e:
            self.toast(f"Could not reload {Path(doc.path).name}: {e}")
            return
        if not self._is_guide():
            try:
                backups.keep(doc.dumps().encode("utf-8"), self._backup_folder())
            except OSError:
                pass
        self.editor.replace_content(fresh.root)
        doc.lang, doc.format, doc.extra, doc.chapter_extra = fresh.lang, fresh.format, fresh.extra, fresh.chapter_extra
        doc.remember_disk()
        if self._save_src:  # nothing to write: the chapter is now what the file holds
            GLib.source_remove(self._save_src)
            self._save_src = None
        self.toast("Reloaded from disk: Ctrl+Z brings back your version")

    def _on_close(self, *_):
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        self.save(quiet=True, ask=False)
        if self._assessments is not None:  # the app quits as one: its drafts are saved as it closes
            self._assessments.close()
        return False
