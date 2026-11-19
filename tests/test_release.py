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
        """The newest release's section is this version. Above it, an "## Unreleased" section
        may collect what is done but not released yet; scripts/release.sh refuses to build
        while it is there."""
        heading = next(l for l in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
                       if l.startswith("## ") and l != "## Unreleased")
        self.assertTrue(heading.startswith(f"## {VERSION} "), heading)

    def test_the_readme_and_the_feature_list_name_this_version(self):
        major_minor = ".".join(VERSION.split(".")[:2])
        for name, title in (("README.md", f"# Notterizmus {major_minor}"),
                            ("FEATURES.md", f"# Notterizmus {major_minor} — Features")):
            first = next(l for l in (ROOT / name).read_text(encoding="utf-8").splitlines() if l.startswith("# "))
            self.assertEqual(first, title, name)

    def test_the_package_recommends_dictionaries_for_both_languages(self):
        """Bulgarian is one of the app's two languages (CR30)."""
        control = (ROOT / "debian" / "control").read_text(encoding="utf-8")
        recommends = control.split("Recommends:", 1)[1].split("\nDescription:", 1)[0]
        self.assertIn("hunspell-en-us", recommends)
        self.assertIn("hunspell-bg", recommends)

    def test_man_page(self):
        th = (ROOT / "debian" / "notterizmus.1").read_text(encoding="utf-8").splitlines()[0]
        self.assertIn(f'"notterizmus {VERSION}"', th)


if __name__ == "__main__":
    unittest.main()
