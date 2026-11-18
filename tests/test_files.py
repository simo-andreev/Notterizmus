"""Saving a chapter: in one step, on the disk, with the file's permissions kept (CR25 in
CODE_REVIEW.md)."""
from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from notterizmus.model import Document


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "Book" / "01 T.notz"
        self.doc = Document.new("Book", 1, "T", self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def mode(self):
        return stat.S_IMODE(self.path.stat().st_mode)

    def leftovers(self):
        return sorted(f.name for f in self.path.parent.iterdir() if f.name != self.path.name)

    def test_a_chapter_keeps_its_permissions_when_it_is_saved(self):
        """Every save made a chapter 0600 (mkstemp's mode), which sync tools and shared
        folders notice."""
        self.doc.save()
        for mode in (0o644, 0o640, 0o600):
            os.chmod(self.path, mode)
            self.doc.save()
            self.assertEqual(oct(self.mode()), oct(mode))

    def test_a_new_chapter_gets_the_usual_permissions_for_the_umask(self):
        old = os.umask(0o022)
        try:
            self.doc.save()
            self.assertEqual(oct(self.mode()), oct(0o644))
            self.path.unlink()
            os.umask(0o077)
            self.doc.save()
            self.assertEqual(oct(self.mode()), oct(0o600))
        finally:
            os.umask(old)

    def test_the_content_reaches_the_disk_before_it_replaces_the_file(self):
        """Without fsync, a power cut soon after a save can leave an empty chapter file."""
        events, fsync, replace = [], os.fsync, os.replace

        def synced(fd):
            events.append("folder" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
            fsync(fd)

        def replaced(src, dst):
            events.append("replace")
            replace(src, dst)

        with mock.patch("os.fsync", synced), mock.patch("os.replace", replaced):
            self.doc.save()
        self.assertEqual(events, ["file", "replace", "folder"])

    def test_a_write_that_fails_leaves_the_file_as_it_was(self):
        from notterizmus.files import atomic_write
        self.doc.save()
        before = self.path.read_bytes()
        with self.assertRaises(OSError), atomic_write(self.path) as f:
            f.write("half of a chap")
            raise OSError(28, "No space left on device")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.leftovers(), [], "no temporary file stays behind")

    def test_binary_content_is_written_as_it_is(self):
        from notterizmus.files import atomic_write
        data = bytes(range(256))
        with atomic_write(self.path, binary=True) as f:
            f.write(data)
        self.assertEqual(self.path.read_bytes(), data)
        self.assertEqual(self.leftovers(), [])


class DiskChangeTest(unittest.TestCase):
    """A chapter notices when another program changed its file since it was read or
    written (a sync tool, a second machine), so autosave doesn't overwrite that version
    unasked (CR10 in CODE_REVIEW.md, R16)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "Book" / "01 T.notz"
        Document.new("Book", 1, "T", self.path).save()

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_chapter_is_unchanged_on_disk_after_it_is_read_or_written(self):
        doc = Document.load(self.path)
        self.assertFalse(doc.changed_on_disk())
        doc.save()
        self.assertFalse(doc.changed_on_disk())

    def test_another_program_replacing_or_rewriting_the_file_is_noticed(self):
        doc = Document.load(self.path)
        other = Document.load(self.path)
        other.chapter_title = "Theirs"
        other.save()  # replaced, as sync tools do
        self.assertTrue(doc.changed_on_disk())
        doc.save()
        self.assertFalse(doc.changed_on_disk())
        with open(self.path, "a", encoding="utf-8") as f:  # changed in place
            f.write(" ")
        self.assertTrue(doc.changed_on_disk())

    def test_a_file_that_is_gone_or_never_written_counts_as_unchanged(self):
        doc = Document.load(self.path)
        self.path.unlink()
        self.assertFalse(doc.changed_on_disk(), "saving brings it back, as before")
        self.assertFalse(Document.new("Book", 2, "New", self.path.with_name("02 New.notz")).changed_on_disk())

    def test_its_text_is_what_a_save_writes(self):
        doc = Document.load(self.path)
        self.assertEqual(doc.dumps(), self.path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
