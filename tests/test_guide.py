import re
import tempfile
import unittest
from pathlib import Path

from notterizmus import guide
from notterizmus.model import Document, can_contain
from notterizmus.paths import guide_path
from notterizmus.rules import Rules

ROOT = Path(__file__).resolve().parents[1]
KEYISH = re.compile(r"Ctrl|Alt|Shift|Enter|Tab|Backspace|Delete|Esc|F\d+|[↑↓]")


class GuideTest(unittest.TestCase):
    def test_tree_follows_the_outline_rules(self):
        root = guide.build()
        self.assertTrue(root.children)
        for top in root.children:
            self.assertEqual(top.kind, "heading", "top-level items are always numbered")
        for n in root.walk():
            for c in n.children:
                self.assertTrue(can_contain(n, c), f"{c} can't sit under {n}")

    def test_round_trips_through_a_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "guide.notz"
            doc = guide.document(path)
            doc.save()
            again = Document.load(path)
        self.assertEqual(again.to_json(), doc.to_json())
        self.assertEqual(again.chapter_title, guide.TITLE)

    def test_every_key_is_documented_in_the_readme(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        keys = [k for k in guide.keys(guide.build()) if KEYISH.search(k)]
        self.assertGreater(len(keys), 20)
        missing = sorted({k for k in keys if k not in readme})
        self.assertEqual(missing, [], "keys taught by the guide but missing from README.md")

    def test_uses_the_typing_triggers_from_the_rules(self):
        r = Rules()
        r.data["heading"]["trigger"] = "^"
        r.data["markers"]["minus"]["trigger"] = "~"
        keys = guide.keys(guide.build(r))
        self.assertIn("^", keys)
        self.assertIn("~", keys)
        self.assertNotIn("#", keys)

    def test_only_the_exercise_word_is_flagged(self):
        from notterizmus.spell import WORD_RE, Speller, should_check
        sp = Speller()
        if not sp.available or "en_US" not in sp.languages():
            self.skipTest("no en_US dictionary")
        sp.set_language("en_US")
        root = guide.build()
        texts = [n.text for n in root.walk()] + [
            "".join(r.text for r in cell) for n in root.walk() for row in n.data.get("rows", []) for cell in row]
        flagged = {m.group() for t in texts for m in WORD_RE.finditer(t)
                   if should_check(m.group()) and not sp.check(m.group())}
        self.assertEqual(flagged - set(guide.SPELL_IGNORE), {"misspeled"})

    def test_practice_copy_lives_outside_the_notes(self):
        self.assertEqual(guide_path({"XDG_DATA_HOME": "/x/share"}),
                         Path("/x/share/notterizmus/Getting Started.notz"))
        self.assertEqual(guide_path({"HOME": "/home/u"}),
                         Path("/home/u/.local/share/notterizmus/Getting Started.notz"))


if __name__ == "__main__":
    unittest.main()
