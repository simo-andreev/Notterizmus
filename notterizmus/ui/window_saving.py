"""The window's saving (CR38 in CODE_REVIEW.md): autosave 800 ms after a change, saving
before anything reads the chapter from disk, Earlier Versions copies, and what to do when
another program changed the file (CR10, R16), and closing when the chapter can't be
saved (RV1 in PLAN.md).

Uses the window's doc, editor, state, toast(), _is_guide() and _update_title(); keeps
_save_src (the waiting autosave), save_banner, _save_error, _save_failures and _retry_src
(a save that failed: the banner and the retries, RV2), _disk_dialog (the question about a
change on disk), and _unsaved_dialog, _ask_unsaved_again, _copy_chooser, _aside
and _closing (closing when the chapter can't be saved)."""
from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk

from .. import backups, paths
from ..files import atomic_write
from ..model import Document
from .helpers import notes_root


RETRY_MAX = 60  # seconds between retries of a failed save, at most (RV2)


def _why(error):
    """An OSError in words, without the file it names: that is a hidden temporary file."""
    return error.strerror or str(error)


class WindowSaving:
    def _build_save_banner(self):
        """A banner that stays while the chapter isn't saved (RV2 in PLAN.md)."""
        self.save_banner = Adw.Banner(button_label="Retry", use_markup=False)
        self.save_banner.connect("button-clicked", lambda *_: self._retry_save())
        return self.save_banner

    def _chapter_label(self, doc=None):
        doc = doc or self.doc
        return doc.chapter_title or f"Chapter {doc.chapter_no}"

    def _saved_state(self, error):
        """After a save: error is its OSError, or None when it worked. A failure shows the
        banner, marks the title and retries after 2, 4, 8 … seconds, at most RETRY_MAX."""
        was = self._save_error
        self._save_error = error
        if error is None:
            self._save_failures = 0
            if self._retry_src:
                GLib.source_remove(self._retry_src)
                self._retry_src = None
            self.save_banner.set_revealed(False)
        else:
            self._save_failures += 1
            self.save_banner.set_title(f"“{self._chapter_label()}” isn't saved: {_why(error)}. "
                                       "Your edits are kept while the app is open.")
            self.save_banner.set_revealed(True)
            if self._retry_src:
                GLib.source_remove(self._retry_src)
            self._retry_src = GLib.timeout_add_seconds(min(RETRY_MAX, 2 ** self._save_failures),
                                                       self._retry_save)
        if (was is None) != (error is None) and self.doc is not None:
            self._update_title()

    def _retry_save(self):
        if self._retry_src:
            GLib.source_remove(self._retry_src)
            self._retry_src = None
        if self.doc is not None and self._save_error is not None:
            self.save(quiet=True)
        return False

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
        can wait for an answer here, so a version changed on disk goes to Earlier Versions.
        Returns whether the chapter is on disk."""
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        return self.save(quiet=True, ask=False)

    def _save_pending(self):
        """Write the open chapter now if an autosave is waiting: before another chapter
        replaces it, or the autosave would write that one instead and these edits would be
        lost (CR4 in CODE_REVIEW.md). An open question about a change on disk counts too:
        an autosave asked it, so its edits aren't written yet, and so does a save that
        failed (RV34). Returns whether the chapter is on disk."""
        if self._save_src or self._disk_dialog is not None or self._save_error is not None:
            return self._flush_save()
        return True

    def _put_aside_before_leaving(self):
        """The open chapter couldn't be saved and is about to be replaced: write it to the
        unsaved folder and say where (RV34 in PLAN.md)."""
        if self.doc is None:
            return
        label = self._chapter_label()
        try:
            self.toast(f"“{label}” couldn't be saved: your edits are in {self._write_aside()}")
        except OSError as e:
            self.toast(f"“{label}” couldn't be saved, nor kept elsewhere: {_why(e)}")

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
        Versions (CR10 in CODE_REVIEW.md, R16). Returns whether the chapter is now on disk."""
        if not self.doc:
            return True
        changed = self.doc.changed_on_disk()
        if changed and ask:
            self._ask_about_disk_change()
            return False
        if changed:
            self._keep_disk_version()
        else:
            self._backup()  # at most every few minutes: the version about to be overwritten
        try:
            self.doc.save()
        except OSError as e:
            self._saved_state(e)
            if not quiet:  # the banner says it for autosaves
                self.toast(f"Save failed: {_why(e)}")
            return False
        self._saved_state(None)
        if not quiet:
            self.toast("Saved")
        return True

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
        """Save before the window closes. If that fails, the window stays open: the edits
        are written to the unsaved folder and you're asked what to do (RV1 in PLAN.md)."""
        if self._closing:
            self._close_assessments()
            return False
        if self._unsaved_dialog is not None or self._copy_chooser is not None:
            return True  # already asked
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        if not self.save(quiet=True, ask=False):
            self._ask_unsaved()
            return True
        self._close_assessments()
        return False

    def _close_assessments(self):
        if self._assessments is not None:  # the app quits as one: its drafts are saved as it closes
            self._assessments.close()

    def _close_now(self):
        """Close the window without trying to save again."""
        self._closing = True
        if self._retry_src:
            GLib.source_remove(self._retry_src)
            self._retry_src = None
        self.close()

    def _write_aside(self):
        """Write the open chapter to the unsaved folder, once for the same text. Returns
        where, or raises OSError."""
        text = self.doc.dumps()
        if self._aside is None or self._aside[0] != text:
            self._aside = (text, backups.keep_unsaved(text, self.doc.path, paths.unsaved_dir()))
        return self._aside[1]

    def _ask_unsaved(self):
        doc = self.doc
        label = self._chapter_label()
        error = self._save_error
        reason = _why(error) if error else "the file couldn't be written"
        try:
            where = f"Your edits were written to {self._write_aside()} instead."
        except OSError as e:
            where = f"They couldn't be written anywhere else either: {_why(e)}."
        dlg = Adw.AlertDialog(
            heading="Not Saved",
            body=f"“{label}” couldn't be saved in {Path(doc.path).parent}: {reason}. {where} "
                 "Retry once the folder can be written to, save a copy somewhere else, or quit "
                 "without saving.")
        dlg.add_response("cancel", "Keep Open")
        dlg.add_response("discard", "Quit Without Saving")
        dlg.add_response("copy", "Save a Copy…")
        dlg.add_response("retry", "Retry")
        dlg.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_response_appearance("retry", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("retry")
        dlg.set_close_response("cancel")
        dlg.connect("response", self._on_unsaved_answer)
        dlg.connect("closed", self._unsaved_dialog_closed)
        self._ask_unsaved_again = False
        self._unsaved_dialog = dlg
        dlg.present(self)

    def _on_unsaved_answer(self, dlg, response):
        if response == "retry":
            if self.save(quiet=True, ask=False):
                self._close_now()
            else:
                self._ask_unsaved_again = True  # once this one has closed
        elif response == "copy":
            self._choose_copy()
        elif response == "discard":
            self._close_now()

    def _unsaved_dialog_closed(self, dlg):
        if self._unsaved_dialog is dlg:
            self._unsaved_dialog = None
            if self._ask_unsaved_again:
                self._ask_unsaved()

    def _choose_copy(self):
        fd = Gtk.FileDialog(title="Save a Copy", initial_name=Path(self.doc.path).name)
        fd.set_initial_folder(Gio.File.new_for_path(GLib.get_home_dir()))
        self._copy_chooser = fd

        def done(dialog, res):
            self._copy_chooser = None
            try:
                gf = dialog.save_finish(res)
            except GLib.Error:
                gf = None
            if gf is None or gf.get_path() is None:
                self._ask_unsaved()  # cancelled: the question again
            else:
                self._save_copy_to(gf.get_path())

        fd.save(self, None, done)

    def _save_copy_to(self, path):
        """Write the open chapter to path, leaving it open where it belongs, and close."""
        try:
            with atomic_write(path) as f:
                f.write(self.doc.dumps())
        except OSError as e:
            self.toast(f"The copy couldn't be saved: {_why(e)}")
            self._ask_unsaved()
            return
        self._close_now()
