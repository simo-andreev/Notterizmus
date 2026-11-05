"""Every place that records the version must agree (run during the package build)."""
import re
import unittest
from pathlib import Path

from notterizmus import APP_ID, VERSION
from notterizmus.paths import latest_release

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTest(unittest.TestCase):
    def test_metainfo_newest_release(self):
        version, notes = latest_release(APP_ID)
        self.assertEqual(version, VERSION)
        self.assertIn("<p>", notes)

    def test_debian_changelog(self):
        first = (ROOT / "debian" / "changelog").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(re.match(r"\S+ \(([^)]+)\)", first).group(1).split("~")[0], VERSION)

    def test_changelog_md(self):
        heading = next(l for l in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
                       if l.startswith("## "))
        self.assertTrue(heading.startswith(f"## {VERSION} "), heading)

    def test_man_page(self):
        th = (ROOT / "debian" / "notterizmus.1").read_text(encoding="utf-8").splitlines()[0]
        self.assertIn(f'"notterizmus {VERSION}"', th)


if __name__ == "__main__":
    unittest.main()
