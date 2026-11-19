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


class MoreDocumentsTest(unittest.TestCase):
    def test_without_glib_or_a_snap_documents_is_in_the_home_folder(self):
        self.assertEqual(documents_dir({}), Path.home() / "Documents")
        self.assertEqual(notes_root({}, "/home/u/Docs"), Path("/home/u/Docs/Notterizmus"))

    def test_user_dirs_entry_is_matched_by_its_whole_name(self):
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(Path(home) / ".config")
            (Path(home) / ".config" / "user-dirs.dirs").write_text(
                'XDG_DOCUMENTS_DIR_OLD="$HOME/Old"\nXDG_DOCUMENTS_DIR="/abs/Docs"\n', encoding="utf-8")
            self.assertEqual(documents_dir({"SNAP_REAL_HOME": home}), Path("/abs/Docs"))


class DataFoldersTest(unittest.TestCase):
    def test_data_folder_follows_xdg_data_home_then_home(self):
        from notterizmus.paths import backups_dir, data_dir, guide_path
        self.assertEqual(data_dir({"XDG_DATA_HOME": "/d", "HOME": "/h"}), Path("/d/notterizmus"))
        self.assertEqual(data_dir({"XDG_DATA_HOME": "", "HOME": "/h"}), Path("/h/.local/share/notterizmus"))
        self.assertEqual(data_dir({}), Path.home() / ".local" / "share" / "notterizmus")
        self.assertEqual(backups_dir({"HOME": "/h"}), Path("/h/.local/share/notterizmus/backups"))
        self.assertEqual(guide_path({"XDG_DATA_HOME": "/d"}).parent, data_dir({"XDG_DATA_HOME": "/d"}))


class MetainfoTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.share = Path(tmp.name) / "share"
        (self.share / "metainfo").mkdir(parents=True)
        self.env = {"XDG_DATA_DIRS": f":{tmp.name}/missing:{self.share}"}

    def write(self, app_id, releases):
        (self.share / "metainfo" / f"{app_id}.metainfo.xml").write_text(
            f"<component><releases>{releases}</releases></component>", encoding="utf-8")

    def test_the_checkouts_own_metainfo_is_used_first(self):
        from notterizmus import APP_ID
        from notterizmus.paths import metainfo_path
        self.write(APP_ID, '<release version="0.0.1"/>')
        here = metainfo_path(APP_ID, self.env)
        self.assertEqual(here, Path(__file__).resolve().parents[1] / "data" / f"{APP_ID}.metainfo.xml")

    def test_an_installed_metainfo_is_found_through_the_data_dirs(self):
        from notterizmus.paths import latest_release, metainfo_path
        self.write("x.y", '<release version="9.9"><description><p>One</p><ul><li>a &amp; b</li></ul></description>'
                          '</release><release version="1.0"/>')
        self.assertEqual(metainfo_path("x.y", self.env), self.share / "metainfo" / "x.y.metainfo.xml")
        self.assertEqual(latest_release("x.y", self.env), ("9.9", "<p>One</p><ul><li>a &amp; b</li></ul>"))

    def test_a_metainfo_file_that_is_not_xml_gives_nothing(self):
        """About raised on it (CR27)."""
        from notterizmus.paths import latest_release
        (self.share / "metainfo" / "bad.metainfo.xml").write_text("<component><releases>", encoding="utf-8")
        self.assertEqual(latest_release("bad", self.env), (None, ""))

    def test_a_release_without_notes_and_a_file_without_releases(self):
        from notterizmus.paths import latest_release
        self.write("n", '<release version="2.0"/>')
        self.write("e", "")
        self.assertEqual(latest_release("n", self.env), ("2.0", ""))
        self.assertEqual(latest_release("e", self.env), (None, ""))
        self.assertEqual(latest_release("not.installed", self.env), (None, ""))


if __name__ == "__main__":
    unittest.main()
