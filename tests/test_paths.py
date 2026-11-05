import os
import tempfile
import unittest
from pathlib import Path

from notterizmus.paths import documents_dir, notes_root


class PathsTest(unittest.TestCase):
    def test_native_uses_glib(self):
        self.assertEqual(documents_dir({}, "/home/u/Документи"), Path("/home/u/Документи"))

    def test_snap_reads_real_home_user_dirs(self):
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(Path(home) / ".config")
            (Path(home) / ".config" / "user-dirs.dirs").write_text(
                '# comment\nXDG_DESKTOP_DIR="$HOME/Работен плот"\nXDG_DOCUMENTS_DIR="$HOME/Документи"\n',
                encoding="utf-8")
            env = {"SNAP_REAL_HOME": home, "HOME": home + "/snap/notterizmus/1"}
            # GLib's answer inside a snap points into the snap's private HOME; it must be ignored
            got = notes_root(env, home + "/snap/notterizmus/1")
            self.assertEqual(got, Path(home) / "Документи" / "Notterizmus")

    def test_snap_without_user_dirs(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(documents_dir({"SNAP_REAL_HOME": home}), Path(home) / "Documents")


if __name__ == "__main__":
    unittest.main()
