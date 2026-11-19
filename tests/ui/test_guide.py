"""Getting Started (F1): a fresh practice copy outside the notes folder."""
import json

from notterizmus import guide, paths
from notterizmus.rules import config_dir

from . import support as ui


class GuideTest(ui.UITestCase):
    def open_guide(self):
        self.win.lookup_action("guide").activate(None)
        ui.settle()

    def test_f1_opens_it(self):
        self.assertEqual(self.app.get_accels_for_action("win.guide"), ["F1"])
        self.assertEqual(self.app.get_accels_for_action("win.about"), [])

    def test_opens_as_a_practice_copy_without_changing_the_suggested_book(self):
        ui.open_chapter([ui_h("Mine")], title="Mine")
        self.open_guide()
        path = paths.guide_path()
        self.assertTrue(path.exists())
        self.assertFalse(str(path).startswith(str(ui.scratch() / "Documents")), "kept out of the notes")
        self.assertEqual((self.win.wtitle.get_title(), self.win.wtitle.get_subtitle()),
                         (guide.TITLE, "Practice copy"))
        state = json.loads((config_dir() / "state.json").read_text())
        self.assertEqual(state["last_book"], "Book")
        self.assertEqual(state["last_file"], str(path))

    def test_starts_fresh_each_time(self):
        self.open_guide()
        first = self.win.doc.root.children[0]
        ui.type_text(ui.row(first).view, " PRACTICE")
        ui.wait_for(lambda: "PRACTICE" in paths.guide_path().read_text(encoding="utf-8"), "the autosave")
        self.open_guide()
        self.assertNotIn("PRACTICE", paths.guide_path().read_text(encoding="utf-8"))
        self.assertNotIn("PRACTICE", self.win.doc.root.children[0].text)

    def test_only_the_exercise_word_is_underlined(self):
        if not self.win.speller.dict or not (self.win.speller.lang or "").startswith("en"):
            self.open_guide()
        if not self.win.speller.dict or not (self.win.speller.lang or "").startswith("en"):
            self.skipTest("no English dictionary installed")
        self.open_guide()

        def marked():
            words = set()
            for v in self.ed.all_views():
                buf = v.get_buffer()
                it = buf.get_start_iter()
                while it.forward_to_tag_toggle(v.tag_spell):
                    if it.starts_tag(v.tag_spell):
                        end = it.copy()
                        end.forward_to_tag_toggle(v.tag_spell)
                        words.add(buf.get_text(it, end, True))
            return words

        ui.pump(0.6)  # spelling is checked a moment after the text is set
        ui.pump_until(lambda: marked() == {"misspeled"})
        self.assertEqual(marked(), {"misspeled"})


class GuideWordsTest(ui.UITestCase):
    def test_the_guides_own_words_are_flagged_again_in_other_chapters(self):
        """Opening Getting Started put its words (Ctrl, TopCoding, …) on Enchant's list
        for the whole run, so they went unflagged in every chapter opened after it (CR21)."""
        if not self.win.speller.available or "en_US" not in self.win.languages:
            self.skipTest("no en_US dictionary")
        self.win.lookup_action("guide").activate(None)
        ui.settle()
        doc = ui.open_chapter([guide.h("Intro", guide.b("TopCoding Ctrl"))])
        view = ui.row(doc.root.children[0].children[0]).view

        def marked():
            buf = view.get_buffer()
            words, it = set(), buf.get_start_iter()
            while True:
                if it.starts_tag(view.tag_spell):
                    end = it.copy()
                    end.forward_to_tag_toggle(view.tag_spell)
                    words.add(buf.get_text(it, end, True))
                    it = end
                if not it.forward_to_tag_toggle(view.tag_spell):
                    return words

        ui.wait_for(lambda: marked() == {"TopCoding", "Ctrl"}, "both words underlined")


def ui_h(text):
    return guide.h(text)
