"""The Assessments window (R35): a TopCoding report imported from its .txt file, practiced
from a blank editor with the original answers behind Reveal, saved as a draft as you type,
finished into earlier attempts, and imported again (Skip, or Replace with the graded one)."""
import json
import shutil
import tempfile
from pathlib import Path

from notterizmus.assessment_txt import Points
from notterizmus.library import Chapter
from notterizmus.model import Document

from . import support as ui
from .test_freeing import Watch

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GRADED = FIXTURES / "assessment_design_a_rate_limiter.txt"
UNGRADED = FIXTURES / "assessment_design_a_rate_limiter_ungraded.txt"
BOOK = "Assessment book"


def helpers():
    """The app's UI helpers, imported when a test runs: this module is also imported
    without PyGObject (tests/test_without_gtk.py)."""
    from notterizmus.ui import helpers as h
    return h


def assessments_root():
    return helpers().assessments_root()


def notes_root():
    return helpers().notes_root()


def idle():
    """Wait for the files' background work and what it hands back to the window."""
    ui.wait_for(lambda: helpers().WORKER.pending == 0, "the background file work")
    ui.frames(2)


def labels(widget):
    return [w.get_label() for w in ui.walk(widget) if isinstance(w, ui.Gtk.Label) and w.get_label()]


def paned_settled(paned):
    """The paned has room for both sides again: its position is no longer squeezed."""
    return paned.props.max_position > paned.props.min_position


class AssessmentsTest(ui.UITestCase):
    def setUp(self):
        super().setUp()
        idle()
        shutil.rmtree(assessments_root(), ignore_errors=True)  # each test starts with none imported
        chapter = notes_root() / BOOK / "03 Design a Rate Limiter.notz"
        if not chapter.exists():
            Document.new(BOOK, 3, "Design a Rate Limiter", chapter).save()
        self.chapter = chapter
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.aw = self.win.assessments_window()
        ui._watch_input(self.aw)  # real keys go to this window now
        idle()

    def tearDown(self):
        aw = self.aw
        if aw is not None and not aw.released:
            while (dlg := aw.get_visible_dialog()) is not None:
                dlg.force_close()
                ui.wait_for(lambda: aw.get_visible_dialog() is not dlg, "a dialog to close")
            aw.close()
        ui.wait_for(lambda: self.win._assessments is None, "the Assessments window to close")
        idle()

    # -- helpers ----------------------------------------------------------------------

    def dialog(self):
        ui.wait_for(lambda: self.aw.get_visible_dialog() is not None, "a dialog")
        return self.aw.get_visible_dialog()

    def respond(self, response):
        dlg = self.dialog()
        dlg.emit("response", response)
        dlg.force_close()
        ui.wait_for(lambda: self.aw.get_visible_dialog() is None, "the dialog to close")
        idle()

    def import_file(self, path):
        self.aw.import_file(ui.Gio.File.new_for_path(str(path)))
        idle()
        return self.dialog()

    def page(self):
        ui.wait_for(lambda: self.aw.page is not None and self.aw.page.attempt is not None, "the practice page")
        idle()
        page = self.aw.page
        ui.wait_for(lambda: ui.point_in(page, self.aw.nav) == (0, 0), "the practice page to slide in")
        return page

    def imported(self, path=GRADED):
        self.import_file(path)
        self.respond("apply")
        return self.page()

    def folders(self):
        root = assessments_root()
        return sorted(p.name for p in root.iterdir() if not p.name.startswith(".")) if root.exists() else []

    def draft(self, page):
        return json.loads((page.a.folder / "draft.json").read_text(encoding="utf-8"))

    def saved(self, page):
        ui.wait_for(lambda: page.saved.get_label() == "Saved", "the draft to be saved")
        idle()

    def text(self, page):
        buf = page.view.get_buffer()
        return buf.get_text(*buf.get_bounds(), False)

    def toasts(self):
        return [w.get_label() for w in ui.walk(self.aw.toasts) if isinstance(w, ui.Gtk.Label) and w.get_label()]

    def real_clicks_here(self):
        """Make real clicks go to the Assessments window: they go to the biggest window
        (broadway_input), and the main window is bigger."""
        self.aw.set_default_size(self.win.get_width() + 40, self.win.get_height() + 20)
        ui.pointer_to(self.aw)

    # -- tests ------------------------------------------------------------------------

    def test_with_nothing_imported_the_window_says_how_to_start(self):
        self.assertEqual(self.aw.list_stack.get_visible_child_name(), "empty")
        self.assertIn("No Assessments Yet", labels(self.aw.list_stack.get_visible_child()))
        self.assertTrue(self.aw.lookup_action("import").get_enabled())
        self.assertFalse(self.aw.lookup_action("next-question").get_enabled())

    def test_an_imported_report_opens_blank_with_its_chapter_and_its_details_hidden(self):
        dlg = self.import_file(GRADED)
        self.assertEqual(dlg.get_heading(), "Import “Design a Rate Limiter”")
        self.assertIn("19 questions, completed 2026-11-23 19:05, scored 7.10 / 19 (37.4%).", dlg.get_body())
        combo = next(w for w in ui.walk(dlg) if isinstance(w, ui.Adw.ComboRow))
        self.assertEqual(combo.get_selected_item().get_string(), f"{BOOK} · 03 Design a Rate Limiter")
        self.respond("apply")
        page = self.page()
        self.assertEqual(self.folders(), ["design_a_rate_limiter_2026-11-23T19-05-51"])
        self.assertEqual((page.a.folder / "report.txt").read_bytes(), GRADED.read_bytes())
        self.assertEqual(len(page.rows), 19)
        self.assertEqual((page.heading.get_label(), self.text(page)), ("Question 1 of 19", ""))
        self.assertEqual(page.prompt.get_label(), "What is the purpose of a rate limiter in a distributed system?")
        self.assertFalse(page.revealer.get_reveal_child())
        self.assertEqual(page.title.get_subtitle(), f"{BOOK} · Chapter 3")
        self.assertEqual(page.final_score.get_label(), "Original score 7.10 / 19 (37.4%)")
        self.assertNotIn("Original score", page.facts.get_label())
        self.assertFalse(page.grading.get_visible())
        self.assertEqual(page.progress_label.get_label(), "Practice attempt 1 · 0 of 19 drafted · 0 revealed")
        ui.wait_for(lambda: self.win.has_assessment(self.chapter), "the chapter to know its assessment")

    def test_reveal_shows_the_original_answer_its_score_the_sample_and_the_feedback(self):
        page = self.page_for_question(1)
        page.reveal_btn.set_active(True)
        shown = labels(page.details)
        q = page.questions[1]
        for text in (q.answer, "Score 1 / 1", q.sample, q.feedback):
            self.assertIn(text, shown)
        self.assertTrue(page.revealer.get_reveal_child())
        self.assertTrue(page.rows[1].revealed.get_visible())
        self.saved(page)
        self.assertEqual(self.draft(page)["answers"]["1"], {"text": "", "revealed": True})
        page.show_question(8)  # no answer, a score of 0: no feedback
        self.assertFalse(page.revealer.get_reveal_child(), "each question starts hidden")
        page.reveal_btn.set_active(True)
        shown = labels(page.details)
        self.assertIn("No answer provided", shown)
        self.assertIn("No feedback (score 0).", shown)
        page.show_question(1)
        self.assertTrue(page.revealer.get_reveal_child(), "a question comes back as it was left")

    def page_for_question(self, number):
        page = self.imported()
        page.show_question(number)
        return page

    def test_load_my_original_answer_asks_before_replacing_text_and_can_be_undone(self):
        page = self.page_for_question(2)
        original = page.questions[2].answer
        page.load_btn.emit("clicked")
        self.assertIsNone(self.aw.get_visible_dialog(), "an empty editor: nothing to ask")
        self.assertEqual(self.text(page), original)
        page.view.get_buffer().undo()
        self.assertEqual(self.text(page), "")
        page.view.get_buffer().set_text("my own try")
        page.load_btn.emit("clicked")
        self.assertEqual(self.dialog().get_heading(), "Replace Your Answer?")
        self.respond("cancel")
        self.assertEqual(self.text(page), "my own try")
        page.load_btn.emit("clicked")
        self.respond("replace")
        self.assertEqual(self.text(page), original)
        page.view.get_buffer().undo()
        self.assertEqual(self.text(page), "my own try")
        page.show_question(8)
        self.assertFalse(page.load_btn.get_sensitive(), "no answer was given on TopCoding")

    def test_typing_is_saved_as_a_draft_and_counted(self):
        page = self.imported()
        page.view.grab_focus()
        ui.wait_for(page.view.has_focus, "the answer's editor")
        ui.real_type("Token bucket")
        self.assertEqual(self.text(page), "Token bucket")
        self.assertEqual(page.counts.get_label(), "2 words · 12 characters")
        self.saved(page)
        self.assertEqual(self.draft(page)["answers"]["1"]["text"], "Token bucket")
        self.assertTrue(page.rows[1].drafted.get_visible())
        self.assertEqual(page.progress_label.get_label(), "Practice attempt 1 · 1 of 19 drafted · 0 revealed")

    # -- spelling (R35a) -----------------------------------------------------------------

    def chapter_in(self, lang, text=None):
        """The assessment's chapter, its spelling language set to lang (None: not chosen)
        and, if given, with this text; put back as it was when the test ends."""
        from notterizmus.guide import h
        before = self.chapter.read_bytes()
        self.addCleanup(self.chapter.write_bytes, before)
        doc = Document.load(self.chapter)
        doc.lang = lang
        if text is not None:
            doc.root.children = [h(text)]
        doc.save()

    def underlined(self, view):
        """The words underlined as misspelled in the answer's editor."""
        buf = view.get_buffer()
        text = buf.get_text(*buf.get_bounds(), False)
        it, words = buf.get_start_iter(), []
        while it.starts_tag(buf.tag_spell) or it.forward_to_tag_toggle(buf.tag_spell):
            end = it.copy()
            end.forward_to_tag_toggle(buf.tag_spell)
            words.append(text[it.get_offset():end.get_offset()])
            it = end
        return words

    def needs(self, lang):
        if lang not in self.aw.languages:
            self.skipTest(f"no {lang} dictionary")

    def test_the_answer_is_spell_checked_in_the_chapters_language_with_suggestions_on_right_click(self):
        self.needs("en_US")
        self.chapter_in("en_US", "Мащабиране")  # the chapter's choice wins over its text's alphabet
        page = self.imported()
        self.assertEqual(self.aw.speller.lang, "en_US")
        view, buf = page.view, page.view.get_buffer()
        buf.set_text("a token buckett refills")
        ui.wait_for(lambda: self.underlined(view) == ["buckett"], "the misspelled word to be underlined")

        # A real right-click on it: the notes' suggestions, Add to Dictionary and Ignore
        self.real_clicks_here()
        rect = view.get_iter_location(buf.get_iter_at_offset(10))  # inside "buckett"
        x, y = view.buffer_to_window_coords(ui.Gtk.TextWindowType.WIDGET, rect.x + 2, rect.y + rect.height // 2)
        ui.real_click(view, x, y, button=3)

        def menu():
            return next((w for w in ui.walk(view) if isinstance(w, ui.Gtk.PopoverMenu) and w.get_visible()), None)
        ui.wait_for(lambda: menu() is not None, "the right-click menu")
        shown = labels(menu())
        self.assertIn("bucket", shown)
        self.assertIn("Add “buckett” to Dictionary", shown)
        self.assertIn("Ignore", shown)
        self.assertEqual(shown[-1], "Ignore", "below GTK's own items")
        menu().popdown()
        ui.wait_for(lambda: menu() is None, "the menu to close")

        view.activate_action("answer.spell-replace", ui.GLib.Variant.new_string("bucket"))
        self.assertEqual(self.text(page), "a token bucket refills")
        ui.wait_for(lambda: self.underlined(view) == [], "the underline to go")
        buf.undo()  # one step
        self.assertEqual(self.text(page), "a token buckett refills")
        self.saved(page)
        self.assertEqual(self.draft(page)["answers"]["1"]["text"], "a token buckett refills")

        # Ignore, then the main window's Check Spelling turns it off and on
        ui.wait_for(lambda: self.underlined(view) == ["buckett"], "the underline back")
        ui.real_click(view, x, y, button=3)
        ui.wait_for(lambda: menu() is not None, "the right-click menu")
        menu().popdown()
        view.activate_action("answer.spell-ignore", ui.GLib.Variant.new_string("buckett"))
        self.assertEqual(self.underlined(view), [])
        buf.set_text("a sliding windo")
        ui.wait_for(lambda: self.underlined(view) == ["windo"], "the new misspelled word underlined")
        spell = self.win.lookup_action("spell")
        self.addCleanup(lambda: spell.get_state().get_boolean() or spell.activate(None))
        spell.activate(None)
        self.assertEqual(self.underlined(view), [], "off: the underlines go at once")
        page.show_question(2)
        buf2 = view.get_buffer()
        buf2.set_text("anothr answer")
        ui.frames(2)
        self.assertEqual(self.underlined(view), [], "and none come while it's off")
        spell.activate(None)
        self.assertEqual(self.underlined(view), ["anothr"], "on again")

    def test_a_chapter_without_a_chosen_language_is_checked_by_its_text(self):
        self.needs("en_US")
        self.needs("bg_BG")
        self.chapter_in(None, "Ограничаване на заявките")
        page = self.imported()
        self.assertEqual(self.aw.speller.lang, "bg_BG", "mostly Cyrillic: Bulgarian")
        page.view.get_buffer().set_text("ограничаване на заявкиите with a buckett")
        ui.wait_for(lambda: self.underlined(page.view) == ["заявкиите", "buckett"],
                    "misspelled words in both alphabets underlined")
        # A language chosen for the chapter in the main window (win.spell-lang): the answers follow
        self.aw.language_chosen(self.chapter.parent / ".." / BOOK / self.chapter.name, "en_US")
        self.assertEqual(self.aw.speller.lang, "en_US")
        self.aw.language_chosen(self.chapter.with_name("other.notz"), "bg_BG")
        self.assertEqual(self.aw.speller.lang, "en_US", "another chapter's choice isn't this one's")

    def test_ctrl_page_down_and_up_go_between_questions_and_f9_hides_the_list(self):
        page = self.imported()
        # Just opened, on the first question: no Previous. (The buttons follow their actions,
        # which are enabled once the draft has been read, after the first question is shown.)
        self.assertEqual((page.prev_btn.get_sensitive(), page.next_btn.get_sensitive()), (False, True))
        page.view.grab_focus()
        ui.wait_for(page.view.has_focus, "the answer's editor")
        ui.real_key("Page_Down", ctrl=True)
        self.assertEqual((page.current, page.heading.get_label()), (2, "Question 2 of 19"))
        self.assertTrue(page.view.has_focus())
        self.assertIs(page.list.get_selected_row(), page.rows[2])
        self.assertTrue(page.prev_btn.get_sensitive())
        ui.real_key("Page_Up", ctrl=True)
        self.assertEqual(page.current, 1)
        ui.real_key("Page_Up", ctrl=True)  # nothing before the first
        self.assertEqual(page.current, 1)
        page.show_question(page.numbers[-1])
        self.assertEqual((page.prev_btn.get_sensitive(), page.next_btn.get_sensitive()), (True, False))
        page.show_question(page.numbers[0])
        ui.real_key("F9")
        self.assertFalse(page.list_pane.get_visible())
        ui.real_key("F9")
        self.assertTrue(page.list_pane.get_visible())

    def test_the_question_list_is_resized_by_dragging_its_edge_within_both_minimums(self):
        """Its width was fixed: the list was the sidebar of an Adw.OverlaySplitView."""
        from notterizmus.ui.assessment_page import LIST_MIN, LIST_WIDTH
        page = self.imported()
        self.real_clicks_here()
        paned, y = page.paned, page.paned.get_height() / 2
        self.assertEqual(paned.get_position(), LIST_WIDTH)

        def drag_edge_to(x):
            ui.real_drag((paned, paned.get_position() + 0.5, y), (paned, x, y))
            ui.past_double_click()

        drag_edge_to(LIST_WIDTH + 80)
        self.assertAlmostEqual(paned.get_position(), LIST_WIDTH + 80, delta=1)
        ui.wait_for(lambda: abs(page.list_pane.get_width() - paned.get_position()) <= 1, "the list to follow")
        drag_edge_to(20)
        self.assertEqual(paned.get_position(), LIST_MIN)
        drag_edge_to(paned.get_width() - 20)
        widest = paned.props.max_position
        self.assertEqual(paned.get_position(), widest)
        ui.frames(2)
        least = page.question_pane.measure(ui.Gtk.Orientation.HORIZONTAL, -1)[0]
        self.assertEqual(page.question_pane.get_width(), least, "the question keeps its minimum width")
        ui.real_key("F9")
        ui.real_key("F9")
        ui.frames(2)
        self.assertEqual(paned.get_position(), widest, "it comes back as wide as it was dragged")

    def test_f9_takes_the_focus_to_the_side_it_shows(self):
        """GTK moved the focus out of the side F9 hid to the paned, whose arrow keys moved
        the hidden handle: in a narrow window, they chose no question."""
        from notterizmus.ui.assessment_page import LIST_WIDTH
        page = self.imported()
        page.rows[1].grab_focus()
        ui.wait_for(page.rows[1].has_focus, "the question list")
        ui.real_key("F9")  # the list goes from under the focus
        self.assertFalse(page.list_pane.get_visible())
        self.assertTrue(page.view.has_focus(), "the answer")
        ui.real_key("F9")
        self.assertTrue(page.view.has_focus(), "the list beside it leaves the focus in the answer")
        self.aw.set_default_size(640, 700)
        ui.wait_for(lambda: page.bin.get_current_breakpoint() is page.narrow, "the narrow layout")
        page.view.grab_focus()  # (the change of layout took it to the header bar)
        ui.wait_for(page.view.has_focus, "the answer")
        ui.real_key("F9")  # the list in the question's place
        self.assertEqual((page.list_pane.get_visible(), page.question_pane.get_visible()), (True, False))
        self.assertTrue(page.rows[1].has_focus(), "the question chosen in the list")
        ui.real_key("Down")
        self.assertEqual(page.current, 2, "the arrow keys choose a question")
        ui.real_key("F9")  # the question in the list's place again
        self.assertEqual((page.list_pane.get_visible(), page.question_pane.get_visible()), (False, True))
        self.assertTrue(page.view.has_focus(), "the answer again")
        self.assertEqual(page.paned.get_position(), LIST_WIDTH, "the hidden handle stayed where it was")

    def test_the_list_and_the_question_fit_side_by_side_or_take_turns_at_any_text_size(self):
        """The narrow layout began at 720sp alone: with smaller text that was narrower than
        the list (whose minimum doesn't shrink) and the question need, and a window a little
        wider cut the question off."""
        settings = ui.Gtk.Settings.get_default()
        self.addCleanup(settings.set_property, "gtk-xft-dpi", settings.props.gtk_xft_dpi)
        page = self.imported()
        content = page.bin.get_child()
        for scale, width in ((0.9, 660), (0.9, 730), (1.25, 890), (1.25, 910)):
            settings.set_property("gtk-xft-dpi", round(96 * 1024 * scale))
            self.aw.set_default_size(width, 700)
            ui.wait_for(lambda: self.aw.get_width() == width, f"the window to be {width} px wide")
            narrow = width <= 720 * max(scale, 1)  # 720 px, or 720sp with larger text
            ui.wait_for(lambda: (page.bin.get_current_breakpoint() is page.narrow) == narrow,
                        f"the {'narrow' if narrow else 'wide'} layout at {width} px with {scale:g}× text")
            ui.frames(2)
            self.assertGreaterEqual(page.bin.get_width(), content.measure(ui.Gtk.Orientation.HORIZONTAL, -1)[0],
                                    f"room for what is shown at {width} px with {scale:g}× text")

    def test_a_narrow_window_shows_the_list_or_the_question_and_widening_brings_both_back(self):
        from notterizmus.ui.assessment_page import LIST_WIDTH
        page = self.imported()

        def shown():
            return page.list_pane.get_visible(), page.question_pane.get_visible()

        self.aw.set_default_size(640, 700)
        ui.wait_for(lambda: page.bin.get_current_breakpoint() is page.narrow, "the narrow layout")
        self.assertEqual(shown(), (False, True))
        self.aw.lookup_action("sidebar").activate(None)  # F9
        self.assertEqual(shown(), (True, False))
        page.rows[3].activate()  # a question chosen in the list takes its place
        self.assertEqual((page.current, shown()), (3, (False, True)))
        for width in (735, 800, 1040):  # widened slowly, as by dragging its edge
            self.aw.set_default_size(width, 780)
            ui.wait_for(lambda: self.aw.get_width() == width, f"the window to be {width} px wide")
        ui.wait_for(lambda: page.bin.get_current_breakpoint() is None, "the wide layout")
        self.assertEqual(shown(), (True, True))
        ui.wait_for(lambda: paned_settled(page.paned), "the list to be laid out")
        self.assertEqual(page.paned.get_position(), LIST_WIDTH, "its width comes back with it")

    def test_revealed_scores_show_in_topcodings_colors_until_the_toggle_turns_them_off(self):
        page = self.imported()
        for n in (1, 2, 8):  # 1 / 1, 0.75 / 1, and 0 / 1 where no answer was given
            page.show_question(n)
            page.reveal_btn.set_active(True)
        colors = ("result-good", "result-partial", "result-poor")

        def scores():
            return [(page.rows[n].score.get_label(), [c for c in colors if page.rows[n].score.has_css_class(c)])
                    for n in (1, 2, 8)]

        def answer_block():  # "Your Original Answer", here for question 8
            block = page.details.get_first_child()
            return labels(block)[:3], [c for c in colors if block.has_css_class(c)]

        def final_score():  # 37.4 %: red, below 65 %
            return page.final_score.get_label(), [c for c in colors if page.final_score.has_css_class(c)]

        self.assertEqual(final_score(), ("Original score 7.10 / 19 (37.4%)", ["result-poor"]))
        self.assertEqual(scores(), [("1", ["result-good"]), ("0.75", ["result-partial"]), ("0", ["result-poor"])])
        self.assertFalse(page.rows[3].score.get_visible(), "not revealed: no score")
        page.rows[3].set_state(False, True, Points("2", "5"))  # (TopCoding's are out of 1)
        self.assertEqual(page.rows[3].score.get_label(), "2 / 5", "a score out of more says so")
        self.assertEqual(answer_block(), (["Your Original Answer", "Score 0 / 1", "No answer provided"],
                                          ["result-poor"]))
        toggle = next(w for w in ui.walk(page) if isinstance(w, ui.Gtk.ToggleButton)
                      and w.get_action_name() == "win.highlights")
        self.assertTrue(toggle.get_active(), "on when the window opens")
        self.real_clicks_here()
        ui.real_drag((toggle, toggle.get_width() / 2, toggle.get_height() / 2))
        self.assertFalse(toggle.get_active())
        self.assertEqual(scores(), [("1", []), ("0.75", []), ("0", [])], "the scores stay, without colors")
        self.assertEqual(final_score(), ("Original score 7.10 / 19 (37.4%)", []))
        self.assertEqual(answer_block(), (["Your Original Answer", "Score 0 / 1", "No answer provided"], []))
        page.show_question(1)
        self.assertEqual(answer_block()[1], [], "nor on a question shown after")
        self.aw.lookup_action("highlights").activate(None)
        self.assertEqual(answer_block()[1], ["result-good"])
        self.assertEqual(scores()[0], ("1", ["result-good"]))
        self.assertEqual(final_score()[1], ["result-poor"])
        self.aw.lookup_action("highlights").activate(None)
        self.aw.close()  # off is not kept
        ui.wait_for(lambda: self.win._assessments is None, "the window to close")
        self.aw = self.win.assessments_window()
        self.assertTrue(self.aw.highlights)

    def test_finishing_an_attempt_keeps_it_and_starts_a_blank_one(self):
        page = self.imported()
        page.view.get_buffer().set_text("first try")
        self.saved(page)
        self.aw.lookup_action("finish").activate(None)
        self.assertEqual(self.dialog().get_heading(), "Finish This Attempt?")
        self.respond("finish")
        ui.wait_for(lambda: self.text(page) == "" and page.get_sensitive(), "a blank attempt")
        (done,) = (page.a.folder / "attempts").iterdir()
        self.assertEqual(json.loads(done.read_text(encoding="utf-8"))["answers"]["1"]["text"], "first try")
        self.assertFalse((page.a.folder / "draft.json").exists())
        self.assertEqual(page.progress_label.get_label(), "Practice attempt 2 · 0 of 19 drafted · 0 revealed")
        self.assertFalse(page.rows[1].drafted.get_visible())
        self.assertFalse(self.aw.lookup_action("finish").get_enabled(), "nothing to finish yet")

    def test_the_list_shows_your_last_attempt_and_the_original_score_stays_hidden_until_reveal(self):
        """R35b: what you did with each question last time, never its original score or the
        sample answer until you reveal it in this attempt."""
        page = self.imported()

        def row_labels(n):
            return labels(page.rows[n])[1:]  # after its number

        def hidden(n):
            q = page.questions[n]
            return not page.rows[n].score.get_visible() and q.sample not in row_labels(n) \
                and q.score.got not in row_labels(n) and "original score" not in page.rows[n].get_tooltip_text()

        self.assertFalse(any(r.last.get_visible() for r in page.rows.values()), "no attempt finished yet")
        page.view.get_buffer().set_text("Token bucket refills at a fixed rate")
        page.show_question(2)
        page.reveal_btn.set_active(True)
        self.assertFalse(hidden(2), "revealed in this attempt: its score shows")
        self.saved(page)
        self.aw.lookup_action("finish").activate(None)
        self.respond("finish")
        ui.wait_for(lambda: self.text(page) == "" and page.get_sensitive(), "a blank attempt")

        self.assertEqual(page.rows[1].last.get_label(), "Last time: 7 words")
        self.assertEqual(page.rows[2].last.get_label(), "Last time: left blank · revealed")
        self.assertEqual(page.rows[3].last.get_label(), "Last time: left blank")
        self.assertIn("last time: 7 words", page.rows[1].get_tooltip_text())
        for n in (1, 2, 3):
            self.assertTrue(hidden(n), f"question {n}: the new attempt hides it again")
        self.assertFalse(page.revealer.get_reveal_child())

        page.show_question(1)
        page.reveal_btn.set_active(True)
        ui.wait_for(lambda: not hidden(1), "Reveal shows question 1's score")
        self.assertEqual(page.rows[1].score.get_label(), page.questions[1].score.got)
        self.assertTrue(hidden(2))

        # Opened again, the last attempt is read from its file
        folder = page.a.folder
        self.aw.nav.pop_to_tag("list")
        ui.wait_for(lambda: self.aw.nav.find_page("practice") is None, "the page to be gone")
        idle()
        self.aw.open_folder(folder)
        page = self.page()
        ui.wait_for(lambda: page.rows[1].last.get_label() == "Last time: 7 words", "the last attempt read again")
        self.assertEqual(page.rows[2].last.get_label(), "Last time: left blank · revealed")
        self.assertFalse(hidden(1), "revealed in this attempt, which was saved")
        self.assertTrue(hidden(2))

    def test_the_trash_button_moves_an_assessment_to_the_trash_and_undo_brings_it_back(self):
        """R35c: a row's trash button moves the assessment's folder, its draft too, to the
        Trash; Undo on the toast puts it back."""
        from notterizmus.ui import assessments_window as module
        trash = Path(self.tmp.name) / "Trash"
        trash.mkdir()
        saved = module.trash_path, module.restore_from_trash
        self.addCleanup(lambda: setattr(module, "trash_path", saved[0]) or setattr(module, "restore_from_trash", saved[1]))

        def to_trash(path):  # a stand-in Trash: the real one would show test files in Files
            shutil.move(str(path), trash / Path(path).name)

        def restore(path):
            src = trash / Path(path).name
            return src.exists() and bool(shutil.move(str(src), path))
        module.trash_path, module.restore_from_trash = to_trash, restore

        page = self.imported()
        page.view.get_buffer().set_text("Token bucket")
        self.saved(page)
        folder = page.a.folder
        self.aw.nav.pop_to_tag("list")
        ui.wait_for(lambda: self.aw.page is None and self.aw.nav.find_page("practice") is None, "the list")
        idle()
        ui.wait_for(lambda: self.win.has_assessment(self.chapter), "the chapter to know its assessment")

        def rows():
            return [w for w in ui.walk(self.aw.prefs) if isinstance(w, ui.Adw.ActionRow)]
        row = next(r for r in rows() if r.get_title() == "Design a Rate Limiter")
        button = next(w for w in ui.walk(row) if isinstance(w, ui.Gtk.Button)
                      and w.get_action_name() == "win.remove")
        self.assertEqual((button.get_tooltip_text(), button.get_action_target_value().get_string()),
                         ("Move to Trash", str(folder)))
        self.real_clicks_here()
        ui.real_click(button, button.get_width() / 2, button.get_height() / 2)
        ui.wait_for(lambda: not folder.exists(), "the folder to go to the Trash")
        idle()
        self.assertTrue((trash / folder.name / "draft.json").exists(), "the draft goes with it")
        ui.wait_for(lambda: self.aw.list_stack.get_visible_child_name() == "empty", "the list without it")
        self.assertFalse(self.win.has_assessment(self.chapter))
        self.assertIn("“Design a Rate Limiter” moved to Trash", self.toasts())

        undo = next(w for w in ui.walk(self.aw.toasts) if isinstance(w, ui.Gtk.Button) and w.get_label() == "Undo")
        ui.wait_for(lambda: undo.get_mapped() and ui.point_in(undo, self.aw)[1] + undo.get_height()
                    <= self.aw.get_height(), "the toast inside the window")
        for _ in range(60):  # and done sliding: where it was a frame before
            at = ui.point_in(undo, self.aw)
            ui.frames(1)
            if ui.point_in(undo, self.aw) == at:
                break
        ui.real_click(undo, undo.get_width() / 2, undo.get_height() / 2)
        ui.wait_for(lambda: folder.exists(), "the folder back from the Trash")
        idle()
        ui.wait_for(lambda: any(r.get_title() == "Design a Rate Limiter" for r in rows()), "the row back")
        self.assertTrue(self.win.has_assessment(self.chapter))
        self.aw.open_folder(folder)
        self.assertEqual(self.text(self.page()), "Token bucket", "the draft back with it")

    def test_earlier_attempts_shows_each_answer_and_compares_it_with_the_sample(self):
        page = self.imported()
        page.view.get_buffer().set_text("first try")
        self.saved(page)
        page._finish()
        ui.wait_for(lambda: self.text(page) == "", "a blank attempt")
        self.aw.lookup_action("attempts").activate(None)
        from notterizmus.ui.attempts import AttemptsDialog
        dlg = self.dialog()
        self.assertIsInstance(dlg, AttemptsDialog)
        idle()
        row = dlg.list.get_row_at_index(0)
        ui.wait_for(lambda: row.get_subtitle() != "…", "the attempt to be read")
        self.assertEqual(row.get_subtitle(), "2 words")
        self.assertEqual(dlg.answer.get_label(), "first try")
        self.assertFalse(dlg.sample_panel.get_visible())
        dlg.compare.set_active(True)
        self.assertTrue(dlg.sample_panel.get_visible())
        self.assertEqual(dlg.sample.get_label(), page.questions[1].sample)

    def test_the_same_report_again_is_skipped_or_replaced_and_replacing_keeps_the_draft(self):
        page = self.imported(UNGRADED)
        self.assertTrue(page.grading.get_visible())
        self.assertIn("Not graded in this file", page.grading.get_label())
        page.view.get_buffer().set_text("kept")
        dlg = self.import_file(GRADED)
        self.assertEqual(dlg.get_heading(), "Report Already Imported")
        self.assertIn("This file has its scores and feedback: Replace adds them.", dlg.get_body())
        self.respond("skip")
        self.assertEqual(len(self.folders()), 1)
        self.assertFalse(page.a.report.graded)
        self.import_file(GRADED)
        self.respond("replace")
        idle()
        self.assertIs(self.aw.page, page)
        self.assertTrue(page.a.report.graded)
        self.assertFalse(page.grading.get_visible())
        self.assertEqual(self.text(page), "kept")
        self.assertEqual(len(self.folders()), 1)
        folder = assessments_root() / self.folders()[0]
        self.assertEqual((folder / "report.txt").read_bytes(), GRADED.read_bytes())
        self.assertEqual(json.loads((folder / "draft.json").read_text(encoding="utf-8"))["answers"]["1"]["text"], "kept")

    def test_an_ungraded_report_says_so_where_the_scores_would_be(self):
        page = self.imported(UNGRADED)
        page.reveal_btn.set_active(True)
        shown = labels(page.details)
        self.assertIn("Not graded in this file", shown)
        self.assertIn("Not graded in this file: import the report again once TopCoding has graded it.", shown)
        self.assertFalse(page.rows[1].score.get_visible(), "no score in the list, so no color")
        self.assertFalse(page.final_score.get_visible(), "nor an original score")

    def test_a_file_that_is_not_a_whole_report_is_refused_with_where_and_why(self):
        lines = GRADED.read_text(encoding="utf-8").split("\n")
        k = next(i for i, line in enumerate(lines) if line == "Question 3")
        bad = Path(self.tmp.name) / "broken.txt"
        bad.write_text("\n".join(lines[:k + 4] + lines[k + 5:]), encoding="utf-8")  # without "Your answer:"
        dlg = self.import_file(bad)
        self.assertEqual(dlg.get_heading(), "Couldn't Import the Report")
        self.assertRegex(dlg.get_body(), r"^broken\.txt: Line \d+, question 3: there's no “Your answer:” line")
        self.assertTrue(dlg.get_body().endswith("Nothing was imported."))
        self.respond("ok")
        self.assertEqual(self.folders(), [])

    def test_a_report_dropped_on_the_window_is_imported(self):
        from gi.repository import GObject
        ctrls = self.aw.toasts.observe_controllers()
        target = next(c for c in (ctrls.get_item(i) for i in range(ctrls.get_n_items()))
                      if isinstance(c, ui.Gtk.DropTarget))
        files = ui.Gdk.FileList.new_from_list([ui.Gio.File.new_for_path(str(p)) for p in (GRADED, UNGRADED)])
        self.assertTrue(target.emit("drop", GObject.Value(ui.Gdk.FileList, files), 10.0, 10.0))
        idle()
        self.assertIn("One report at a time: importing the first", self.toasts())
        dlg = self.dialog()
        self.assertEqual(dlg.get_heading(), "Import “Design a Rate Limiter”")
        self.assertIn("scored 7.10 / 19 (37.4%)", dlg.get_body())  # the first file: the graded one
        self.respond("apply")
        self.assertEqual(self.folders(), ["design_a_rate_limiter_2026-11-23T19-05-51"])

    def test_the_chapter_list_offers_the_chapters_assessment(self):
        self.imported()
        ui.wait_for(lambda: self.win.has_assessment(self.chapter), "the chapter to know its assessment")
        from notterizmus.ui.sidebar import ChapterRow
        menu = self.win.sidebar.menu_for(ChapterRow(Chapter(3, "Design a Rate Limiter", self.chapter)))
        items = [menu.get_item_link(i, "section").get_item_attribute_value(j, "label").get_string()
                 for i in range(menu.get_n_items())
                 for j in range(menu.get_item_link(i, "section").get_n_items())]
        self.assertIn("Practice Assessment", items)
        self.assertIn("Import Assessment Report…", items)

    def chapter_button(self, path):
        """The button at the end of a chapter's row in the chapter list, its book unfolded."""
        from notterizmus.ui.sidebar import ChapterRow
        sidebar = self.win.sidebar
        self.win._reload_sidebar()
        sidebar.expanded.add(BOOK)
        sidebar._rebuild()
        ui.frames(2)
        row = next(r for r in sidebar.rows() if isinstance(r, ChapterRow) and r.path == path)
        ok, bounds = row.compute_bounds(sidebar.list)
        row.get_ancestor(ui.Gtk.ScrolledWindow).get_vadjustment().set_value(bounds.get_y())  # where a click finds it
        ui.frames(2)
        return row.assessment_button

    def close_for_real_clicks(self):
        """Close the Assessments window: real clicks go to the biggest window, which it is."""
        self.aw.close()
        ui.wait_for(lambda: self.win._assessments is None, "the Assessments window to close")
        ui.pointer_to(self.win)

    def test_a_chapter_without_an_assessment_imports_one_for_itself_from_its_button(self):
        """The import goes with the chapter whose button it came from, without asking,
        though the report's title matches another chapter; then the report opens."""
        from unittest import mock
        from notterizmus.ui.assessments_window import AssessmentsWindow
        other = notes_root() / BOOK / "04 Leaky Buckets.notz"
        Document.new(BOOK, 4, "Leaky Buckets", other).save()
        self.addCleanup(other.unlink, missing_ok=True)
        self.close_for_real_clicks()
        button = self.chapter_button(other)
        self.assertEqual((button.get_action_name(), button.get_action_target_value().get_string()),
                         ("win.chapter-import", str(other)))
        self.assertEqual(button.get_tooltip_text(), "Import an assessment report for this chapter…")
        self.assertTrue(button.has_css_class("dim-label"))
        opened = self.win.doc.path if self.win.doc else None
        chosen = []

        def choose_file(aw, chapter=None):  # the file dialog, answered with the graded report
            chosen.append(chapter)
            aw.import_file(ui.Gio.File.new_for_path(str(GRADED)), chapter)

        with mock.patch.object(AssessmentsWindow, "choose_file", choose_file):
            ui.real_drag((button, button.get_width() / 2, button.get_height() / 2))
            ui.wait_for(lambda: self.win._assessments is not None, "the Assessments window")
            self.aw = self.win._assessments
            ui._watch_input(self.aw)
            page = self.page()
        self.assertEqual([ch.path for ch in chosen], [other])
        self.assertIsNone(self.aw.get_visible_dialog(), "no question which chapter")
        self.assertEqual(page.title.get_subtitle(), f"{BOOK} · Chapter 4")
        link = json.loads((page.a.folder / "report.json").read_text(encoding="utf-8"))["chapter"]
        self.assertEqual((link["file"], link["number"], link["title"]), (f"{BOOK}/04 Leaky Buckets.notz", 4, "Leaky Buckets"))
        self.assertEqual(self.win.doc.path if self.win.doc else None, opened, "the click didn't open the chapter")
        ui.wait_for(lambda: self.win.has_assessment(other), "the chapter to know its assessment")
        self.assertFalse(self.win.has_assessment(self.chapter))
        button = self.chapter_button(other)
        self.assertEqual((button.get_action_name(), button.get_tooltip_text()),
                         ("win.chapter-practice", "Practice this chapter's assessment"))
        self.assertFalse(button.has_css_class("dim-label"))

    def test_a_chapter_with_an_assessment_opens_it_from_its_button(self):
        self.imported()  # goes with chapter 3, whose title it has
        ui.wait_for(lambda: self.win.has_assessment(self.chapter), "the chapter to know its assessment")
        self.close_for_real_clicks()
        button = self.chapter_button(self.chapter)
        self.assertEqual((button.get_action_name(), button.get_action_target_value().get_string()),
                         ("win.chapter-practice", str(self.chapter)))
        ui.real_drag((button, button.get_width() / 2, button.get_height() / 2))
        ui.wait_for(lambda: self.win._assessments is not None, "the Assessments window")
        self.aw = self.win._assessments
        ui._watch_input(self.aw)
        page = self.page()
        self.assertEqual((page.a.report.title, page.title.get_subtitle()), ("Design a Rate Limiter", f"{BOOK} · Chapter 3"))
        self.assertEqual(self.folders(), ["design_a_rate_limiter_2026-11-23T19-05-51"], "nothing imported again")

    def test_an_assessment_follows_its_chapter_when_it_is_renamed(self):
        page = self.imported()
        folder = page.a.folder
        self.win.apply_chapter_props(self.chapter, self.chapter.parent, 3, "Rate Limiting")
        idle()
        renamed = self.chapter.with_name("03 Rate Limiting.notz")
        self.addCleanup(lambda: renamed.exists() and renamed.rename(self.chapter))
        link = json.loads((folder / "report.json").read_text(encoding="utf-8"))["chapter"]
        self.assertEqual(link["file"], f"{BOOK}/03 Rate Limiting.notz")
        self.assertTrue(self.win.has_assessment(renamed))

    def test_closing_the_window_saves_the_draft_and_lets_go_of_it(self):
        page = self.imported()
        folder = page.a.folder
        page.view.get_buffer().set_text("typed just before closing")
        w = Watch()
        w.add("the Assessments window", self.aw)
        w.add("its practice page", page)
        w.add("the answer's text view", page.view)
        page = None
        self.aw.close()
        ui.wait_for(lambda: self.win._assessments is None, "the window to close")
        draft = json.loads((folder / "draft.json").read_text(encoding="utf-8"))
        self.assertEqual(draft["answers"]["1"]["text"], "typed just before closing")
        self.aw = None
        w.wait(self)
