"""Practicing one assessment (assessments_window.py): its questions in a list beside the
one being answered, an editor for each answer that starts blank, and behind Reveal what
TopCoding showed: your original answer with its score, the sample answer and the
feedback.

The answer editor (AnswerView) checks spelling as the notes do, in the language of the
chapter the assessment goes with (its own choice, else its text's alphabet), with the
same right-click suggestions; the main window's Check Spelling turns it off and on.

The answers are a practice attempt (assessments.Attempt). It is saved as the assessment's
draft 800 ms after a change, and when the page or the window goes: the text is copied
here, on the main loop, and written by helpers.WORKER, one write at a time, the newest
text winning. Finish Attempt keeps it among the attempts and starts a blank one; Earlier
Attempts (attempts.py) shows them.

The window's actions drive the page: win.prev-question and win.next-question (Ctrl+PgUp,
Ctrl+PgDn), win.sidebar (F9: the question list), win.finish, win.attach, win.attempts and
win.highlights (the original scores in TopCoding's colors: assessments.result_category and
final_category)."""
from __future__ import annotations

from datetime import datetime

from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from .. import assessments as store
from ..assessments import Answer, Attempt
from ..model import Document
from ..spell import pick_language
from .attempts import AttemptsDialog
from .helpers import WORKER, set_class, weak_handler
from .richtext import Spelling, add_spell_tag, mark_misspelled, spelling_section, word_at

SAVE_DELAY = 800  # ms after the last change, as for chapters
SPELL_DELAY = 400  # ms after the last change, as in the notes (richtext.RichText.schedule_spell)
LIST_WIDTH = 260  # px: the question list's width when a page opens (it isn't kept)
LIST_MIN = 200    # px: neither the list nor the question can be dragged narrower than its minimum


class DraftFile:
    """One assessment's draft.json, used only on WORKER's thread: it knows the file as it
    last read or wrote it, so a change another computer made is told from its own
    (assessments.write_draft), however the page's writes queue up."""

    def __init__(self, assessment):
        self.assessment, self.disk = assessment, None

    def read(self):
        attempt = store.read_draft(self.assessment)
        self.disk = attempt.disk
        return attempt

    def write(self, attempt):
        attempt.disk = self.disk
        kept = store.write_draft(self.assessment, attempt)
        self.disk = attempt.disk
        return kept, attempt.set_aside

    def finish(self, attempt):
        attempt.disk = self.disk
        done, kept = store.finish(self.assessment, attempt)
        self.disk = None
        return done, kept


class DraftBuffer(Gtk.TextBuffer):
    """The answer to question `number` in this attempt. Each question has its own, so each
    keeps its own undo history."""

    def __init__(self, number, text):
        super().__init__(enable_undo=True)
        self.number = number
        self.tag_spell = add_spell_tag(self)
        self.set_text(text)  # (not undoable: it was there when the page opened)


class AnswerView(Gtk.TextView):
    """The answer editor, showing one question's DraftBuffer at a time. Its words are
    checked with `spelling` (richtext.Spelling) as the notes' are, and a right-click on an
    underlined one (or the Menu key, Shift+F10 at the cursor) offers the same suggestions,
    Add to Dictionary and Ignore (richtext.spelling_section), as actions answer.*. A
    replacement is one step Ctrl+Z undoes."""
    __gtype_name__ = "NtzAnswerView"

    def __init__(self, spelling, **props):
        super().__init__(**props)
        self.spelling = spelling
        self._spell_src = None
        self._watched = None  # (buffer, handler id): the buffer shown, checked again as it changes
        self._word = None     # (start, end): the misspelled word the menu was opened on
        group = Gio.SimpleActionGroup()
        for name, method in (("spell-replace", self._replace), ("spell-add", self._add),
                             ("spell-ignore", self._ignore)):
            action = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            action.connect("activate", weak_handler(method))
            group.add_action(action)
        noop = Gio.SimpleAction.new("noop", None)
        noop.set_enabled(False)  # "No Suggestions"
        group.add_action(noop)
        self.insert_action_group("answer", group)
        # Before GTK's own handler shows the menu, as in the notes (rows.py)
        click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", weak_handler(self._pressed))
        self.add_controller(click)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", weak_handler(self._key_pressed))
        self.add_controller(keys)
        self.connect("notify::buffer", weak_handler(self._buffer_set))

    def _buffer_set(self, *_):
        if self._watched is not None:
            buf, handler = self._watched
            buf.disconnect(handler)
        buf = self.get_buffer()
        self._watched = (buf, buf.connect("changed", weak_handler(self.schedule_spell)))
        self.recheck_spelling()  # a question comes with its underlines

    def schedule_spell(self, *_):
        if self._spell_src:
            GLib.source_remove(self._spell_src)
        self._spell_src = GLib.timeout_add(SPELL_DELAY, weak_handler(self._spell_now))

    def _spell_now(self):
        self._spell_src = None
        self.recheck_spelling()
        return GLib.SOURCE_REMOVE

    def recheck_spelling(self):
        buf = self.get_buffer()
        if isinstance(buf, DraftBuffer):
            mark_misspelled(buf, buf.tag_spell, self.spelling)

    def stop(self):
        """The page is going: no check is due after it."""
        if self._spell_src:
            GLib.source_remove(self._spell_src)
            self._spell_src = None
        if self._watched is not None:
            buf, handler = self._watched
            buf.disconnect(handler)
            self._watched = None

    # -- the menu ---------------------------------------------------------------------

    def _pressed(self, _gesture, _n, x, y):
        bx, by = self.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        ok, it = self.get_iter_at_location(bx, by)
        self.prepare_menu(it if ok else None)

    def _key_pressed(self, _ctl, keyval, _code, state):
        if keyval == Gdk.KEY_Menu or (keyval == Gdk.KEY_F10 and state & Gdk.ModifierType.SHIFT_MASK):
            buf = self.get_buffer()
            self.prepare_menu(buf.get_iter_at_mark(buf.get_insert()))
        return False

    def prepare_menu(self, it):
        """Fill the right-click menu (shown below GTK's cut, copy and paste) for the word at
        it: suggestions if it is underlined."""
        menu = Gio.Menu()
        self._word = None
        buf = self.get_buffer()
        if self.spelling.active and it is not None and isinstance(buf, DraftBuffer) and it.has_tag(buf.tag_spell):
            text = buf.get_text(*buf.get_bounds(), True)
            bounds = word_at(text, it.get_offset())
            if bounds is not None:
                self._word = bounds
                menu.append_section(None, spelling_section(self.spelling.speller, text[slice(*bounds)], "answer"))
        self.set_extra_menu(menu)

    def _replace(self, _action, param):
        if self._word is None:
            return
        (start, end), self._word = self._word, None
        buf = self.get_buffer()
        if end > buf.get_char_count():
            return
        buf.begin_user_action()
        buf.delete(buf.get_iter_at_offset(start), buf.get_iter_at_offset(end))
        buf.insert(buf.get_iter_at_offset(start), param.get_string())
        buf.end_user_action()
        self.grab_focus()

    def _add(self, _action, param):
        if self.spelling.speller is not None:
            self.spelling.speller.add(param.get_string())
            self.recheck_spelling()

    def _ignore(self, _action, param):
        if self.spelling.speller is not None:
            self.spelling.speller.ignore(param.get_string())
            self.recheck_spelling()


class QuestionRow(Gtk.ListBoxRow):
    """A question in the list: its number, its prompt, icons for what you did with it in
    this attempt (answered it, revealed it), once revealed its original score, and under
    the prompt what you did with it in your last finished attempt (set_last)."""

    def __init__(self, question, **props):
        super().__init__(**props)
        self.number = question.number
        box = Gtk.Box(spacing=8, margin_top=4, margin_bottom=4)
        num = Gtk.Label(label=str(question.number), width_chars=2, xalign=1, valign=Gtk.Align.START,
                        css_classes=["dim-label", "numeric"])
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        text.append(Gtk.Label(label=" ".join(question.prompt.split()), xalign=0, ellipsize=Pango.EllipsizeMode.END))
        self.last = Gtk.Label(xalign=0, visible=False, ellipsize=Pango.EllipsizeMode.END,
                              css_classes=["dim-label", "caption", "numeric"])
        text.append(self.last)
        self.drafted = Gtk.Image(icon_name="document-edit-symbolic", visible=False)
        self.revealed = Gtk.Image(icon_name="view-reveal-symbolic", visible=False)
        self.score = Gtk.Label(visible=False, css_classes=["numeric"])
        for w in (num, text, self.drafted, self.revealed, self.score):
            box.append(w)
        self.set_child(box)
        self.set_state(False, False)

    def set_last(self, text):
        """What you did with the question in your last finished attempt ("Last time: 42
        words"), or None without one. Set before set_state, which says it too."""
        self.last.set_label(text or "")
        self.last.set_visible(text is not None)

    def set_state(self, drafted, revealed, score=None, highlight=True):
        """score: the original score (None if ungraded), shown once the question is
        revealed, as "0.75" when it is out of 1 (TopCoding's are); in TopCoding's color for
        it if highlight (the page's toggle)."""
        self.drafted.set_visible(drafted)
        self.revealed.set_visible(revealed)
        shown = revealed and score is not None
        self.score.set_visible(shown)
        self.score.set_label((score.got if score.maximum == 1 else str(score)) if shown else "")
        _show_result(self.score, store.result_category(score) if shown and highlight else None)
        state = ("drafted" if drafted else "unanswered") + (", revealed" if revealed else "") \
            + (f", original score {score}" if shown else "") \
            + (f"; {self.last.get_label().lower()}" if self.last.get_visible() else "")
        self.set_tooltip_text(f"Question {self.number}: {state}")
        self.update_property([Gtk.AccessibleProperty.DESCRIPTION], [state])


class PracticePage(Adw.NavigationPage):
    __gtype_name__ = "NtzPracticePage"

    def __init__(self, window, assessment, chapter_label, chapter=None):
        """chapter: the library.Chapter it goes with (None: none found), whose language the
        answers are checked in."""
        super().__init__(title=assessment.report.title, tag="practice")
        self.win = window
        self.a = assessment
        self.spelling = Spelling()  # the answer editor's, in the chapter's language (set_chapter)
        self.chapter = None         # the library.Chapter it goes with, if found
        self.questions = {q.number: q for q in assessment.report.questions}
        self.numbers = [q.number for q in assessment.report.questions]
        self.file = DraftFile(assessment)
        self.attempt = None   # the attempt in progress, once its draft is read
        self.last = None      # the attempt you finished last (store.last_attempt), if any
        self.buffers = {}     # {question number: DraftBuffer}, made as each question is shown
        self.current = None   # the question shown
        self.shown = set()    # questions whose details are shown now (they are revealed for good)
        self.released = False
        self._save_src = None
        self._dirty = False   # changed since the last copy went to be written
        self._writing = False
        self._again = False   # changed while a write was going: write again when it is done
        self._handlers = []   # (object, handler id) to disconnect when the page goes

        self._drafted = set()  # questions with an answer in this attempt
        tv = Adw.ToolbarView()
        tv.add_top_bar(self._build_header(chapter_label))
        # The question list beside the question, as wide as you drag the handle between them.
        self.list_pane, self.question_pane = self._build_list(), self._build_content()
        self.paned = Gtk.Paned(start_child=self.list_pane, end_child=self.question_pane, position=LIST_WIDTH,
                               resize_start_child=False, shrink_start_child=False, shrink_end_child=False)
        self._list_width = LIST_WIDTH  # as last dragged: it comes back with the list
        for obj, signal, method in ((self.list_pane, "notify::visible", self._list_shown),
                                    (self.paned, "notify::position", self._list_resized),
                                    (self.paned, "notify::max-position", self._room_changed),
                                    (window, "notify::focus-widget", self._keep_focus)):
            self._handlers.append((obj, obj.connect(signal, weak_handler(method))))
        tv.set_content(self.paned)
        # A narrow window shows the list or the question, not both (show_list); widened, it
        # has the list as before. The breakpoint is the page's own: one added to the window
        # would hold the page after it is gone. Up to 720 px, or 720sp with larger text: the
        # question's minimum width grows with the text size, but the list's (LIST_MIN) doesn't
        # shrink with smaller text.
        self.narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 720px or max-width: 720sp"))
        self.narrow.add_setter(self.list_pane, "visible", False)
        self.narrow.add_setter(self.question_pane, "visible", True)
        self.bin = Adw.BreakpointBin(child=tv, width_request=360, height_request=320)
        self.bin.add_breakpoint(self.narrow)
        self.set_child(self.bin)
        self.set_report(assessment)
        self.set_chapter(chapter)
        WORKER.run(self.file.read, done=self._loaded, failed=self._load_failed)
        WORKER.run(lambda a=assessment: store.last_attempt(a), done=self._last_found,
                   failed=lambda _e: None)  # (unreadable attempts are left out: none to show)

    # -- building ---------------------------------------------------------------------

    def _build_header(self, chapter_label):
        header = Adw.HeaderBar()
        self.title = Adw.WindowTitle(title=self.a.report.title, subtitle=chapter_label)
        header.set_title_widget(self.title)
        header.pack_start(Gtk.ToggleButton(icon_name="sidebar-show-symbolic", tooltip_text="Questions (F9)",
                                           action_name="win.sidebar"))
        header.pack_start(Gtk.ToggleButton(icon_name="preferences-color-symbolic", action_name="win.highlights",
                                           tooltip_text="Color the original scores as TopCoding does"))
        menu = Gio.Menu()
        menu.append("Earlier Attempts…", "win.attempts")
        menu.append("Attach to Chapter…", "win.attach")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Menu"))
        header.pack_end(Gtk.Button(label="Finish Attempt", action_name="win.finish",
                                   tooltip_text="Keep this attempt's answers and start a blank one"))
        return header

    def _build_list(self):
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["navigation-sidebar"])
        self.rows = {}
        for q in self.a.report.questions:
            self.rows[q.number] = row = QuestionRow(q)
            self.list.append(row)
        self.list.connect("row-selected", _row_selected)
        self.list.connect("row-activated", _row_activated)
        return Gtk.ScrolledWindow(child=self.list, hscrollbar_policy=Gtk.PolicyType.NEVER, width_request=LIST_MIN,
                                  css_classes=["sidebar-pane", "assessment-questions"])

    def _build_content(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self._build_summary())
        box.append(Gtk.Separator())
        self.stack = Gtk.Stack(vexpand=True)
        self.stack.add_named(Adw.Spinner(), "loading")
        area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18, margin_bottom=24,
                       margin_start=18, margin_end=18)
        self.heading = Gtk.Label(xalign=0, css_classes=["dim-label", "caption-heading"])
        self.prompt = Gtk.Label(xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, selectable=True,
                                css_classes=["title-4"])
        self.view = AnswerView(self.spelling, wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=10, bottom_margin=10,
                               left_margin=12, right_margin=12)
        self.view.update_property([Gtk.AccessibleProperty.LABEL], ["Your answer"])
        editor = Gtk.ScrolledWindow(child=self.view, min_content_height=200, max_content_height=460,
                                    propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                    css_classes=["assessment-answer"])
        under = Gtk.Box(spacing=12)
        self.counts = Gtk.Label(xalign=0, hexpand=True, css_classes=["dim-label", "caption", "numeric"])
        self.saved = Gtk.Label(xalign=1, css_classes=["dim-label", "caption"])
        under.append(self.counts)
        under.append(self.saved)
        buttons = Gtk.Box(spacing=8)
        self.load_btn = Gtk.Button(label="Load My Original Answer")
        self.load_btn.connect("clicked", _load_clicked)
        self.reveal_btn = Gtk.ToggleButton(tooltip_text="Show your original answer, its score, the sample answer "
                                                        "and the feedback")
        self.reveal_btn.set_child(Adw.ButtonContent(icon_name="view-reveal-symbolic", label="Reveal"))
        self.reveal_btn.connect("toggled", _reveal_toggled)
        buttons.append(self.load_btn)
        buttons.append(self.reveal_btn)
        buttons.append(Gtk.Box(hexpand=True))
        buttons.append(Gtk.Button(label="Earlier Attempts…", action_name="win.attempts"))
        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=6,
                               css_classes=["assessment-details"])
        self.revealer = Gtk.Revealer(child=self.details, transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        steps = Gtk.Box(spacing=8, margin_top=6)
        self.prev_btn = Gtk.Button(action_name="win.prev-question", tooltip_text="Previous question (Ctrl+PgUp)")
        self.prev_btn.set_child(Adw.ButtonContent(icon_name="go-previous-symbolic", label="Previous"))
        self.next_btn = Gtk.Button(action_name="win.next-question", tooltip_text="Next question (Ctrl+PgDn)")
        self.next_btn.set_child(Adw.ButtonContent(icon_name="go-next-symbolic", label="Next"))
        steps.append(self.prev_btn)
        steps.append(Gtk.Box(hexpand=True))
        steps.append(self.next_btn)
        for w in (self.heading, self.prompt, editor, under, buttons, self.revealer, steps):
            area.append(w)
        self.scroller = Gtk.ScrolledWindow(child=Adw.Clamp(maximum_size=860, tightening_threshold=600, child=area),
                                           hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.stack.add_named(self.scroller, "question")
        self.problem = Adw.StatusPage(icon_name="dialog-error-symbolic", title="Couldn't Read Your Draft")
        self.stack.add_named(self.problem, "problem")
        box.append(self.stack)
        return box

    def _build_summary(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=10, margin_bottom=10,
                      margin_start=18, margin_end=18)
        self.facts = Gtk.Label(xalign=0, wrap=True, hexpand=True, css_classes=["dim-label"])
        # the original score: on its own, to show in TopCoding's color for it (_show_result)
        self.final_score = Gtk.Label(valign=Gtk.Align.START, css_classes=["numeric"])
        about = Gtk.Box(spacing=12)
        about.append(self.facts)
        about.append(self.final_score)
        self.grading = Gtk.Label(xalign=0, wrap=True, css_classes=["warning"])
        line = Gtk.Box(spacing=12)
        self.progress_label = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.progress = Gtk.ProgressBar(valign=Gtk.Align.CENTER, width_request=160)
        line.append(self.progress_label)
        line.append(self.progress)
        for w in (about, self.grading, line):
            box.append(w)
        return box

    # -- the report -------------------------------------------------------------------

    def set_report(self, assessment, chapter_label=None):
        """Show this assessment's report: at first, and after a Replace brought its scores
        and feedback. The answers in progress stay as they are."""
        self.a = self.file.assessment = assessment
        self.questions = {q.number: q for q in assessment.report.questions}
        if chapter_label is not None:
            self.title.set_subtitle(chapter_label)
        r = assessment.report
        when = f"{r.completed_at:%Y-%m-%d %H:%M}" if r.completed_at else r.completed
        facts = [r.difficulty.capitalize() if r.difficulty else "",
                 f"Completed {when}" if when else "",
                 f"Time spent {r.time_spent} of {r.time_allocated}" if r.time_spent and r.time_allocated
                 else (f"Time spent {r.time_spent}" if r.time_spent else ""),
                 f"TopCoding attempt {r.attempt}" if r.attempt else ""]
        self.facts.set_label(" · ".join(f for f in facts if f))
        self.final_score.set_label(f"Original score {_score(r)}" if r.final_result else "")
        self.final_score.set_visible(r.final_result is not None)
        self._show_final_score()
        self.grading.set_label("" if r.graded else "Not graded in this file. Import the report again after "
                                                   "TopCoding grades it to see your scores and feedback.")
        self.grading.set_visible(not r.graded)
        if self.current is not None:
            self._fill_details(self.questions[self.current])
        for n in self.rows:  # the scores a Replace brought
            self._update_row(n)
        self._update_progress()

    def show_highlights(self):
        """The scores' colors were turned on or off (win.highlights)."""
        self._show_final_score()
        for n in self.rows:
            self._update_row(n)
        if self.current is not None:
            self._fill_details(self.questions[self.current])

    def _show_final_score(self):
        _show_result(self.final_score, store.final_category(self.a.report) if self.win.highlights else None)

    # -- spelling ---------------------------------------------------------------------

    def set_chapter(self, chapter):
        """Check the answers in this chapter's language: the one chosen for it in the notes,
        else by its text (as the main window picks it); with no chapter, or one that can't
        be read, by the assessment's own text. Read on WORKER."""
        self.chapter = chapter
        own = self._report_text()
        if chapter is None:
            self._language_found((None, own))
            return
        WORKER.run(lambda path=chapter.path, own=own: _language_hints(path, own),
                   done=self._language_found, failed=lambda _e: self._language_found((None, own)))

    def goes_with(self, path):
        """Whether this assessment goes with the chapter file at path."""
        try:
            return self.chapter is not None and self.chapter.path.resolve() == path.resolve()
        except OSError:
            return False

    def set_language(self, lang):
        """Check the answers in lang: chosen for the chapter in the main window."""
        self._language_found((lang, ""))

    def _report_text(self):
        return " ".join(t for q in self.a.report.questions for t in (q.prompt, q.sample) if t)

    def _language_found(self, hints):
        if self.released:
            return
        wanted, text = hints
        speller = self.win.speller
        self.spelling.speller = speller
        if speller.available:
            speller.set_language(pick_language(wanted, text, self.win.languages, self.win.spell_lang))
        self.spelling_changed()

    def spelling_changed(self):
        """Check Spelling was turned on or off in the main window (or the language set)."""
        self.spelling.enabled = self.win.spell_on and self.spelling.speller is not None
        self.view.recheck_spelling()

    # -- the attempt ------------------------------------------------------------------

    def _loaded(self, attempt):
        if self.released:
            return
        self.attempt = attempt
        if attempt.set_aside is not None:
            self.win.toast(f"Your draft couldn't be read. It was kept as {attempt.set_aside.name} in the "
                           "assessment's folder, and a new one begins.")
        for n in self.rows:
            self._update_row(n)
        self.stack.set_visible_child_name("question")
        self.show_question(self.numbers[0])
        self._update_progress()
        self.win.update_actions()

    def _last_found(self, attempt):
        if self.released:
            return
        self.last = attempt
        for n in self.rows:
            self._update_row(n)

    def _load_failed(self, error):
        if self.released:
            return
        reason = GLib.markup_escape_text(str(getattr(error, "strerror", None) or error))  # the description is markup
        self.problem.set_description(f"{reason}. Nothing is saved until it can be read, so that it isn't written over.")
        self.stack.set_visible_child_name("problem")
        self.win.update_actions()

    def show_question(self, number):
        if self.attempt is None or number not in self.questions:
            return
        self.current = number
        q = self.questions[number]
        self.heading.set_label(f"Question {self.numbers.index(number) + 1} of {len(self.numbers)}")
        self.prompt.set_label(q.prompt)
        self.view.set_buffer(self._buffer(number))
        self.load_btn.set_sensitive(q.answer is not None)
        self.load_btn.set_tooltip_text("Put the answer you gave on TopCoding in the editor" if q.answer is not None
                                       else "You gave no answer to this question on TopCoding")
        self._fill_details(q)
        shown = number in self.shown
        self.revealer.set_transition_duration(0)  # a question comes as it was left, without sliding
        self.reveal_btn.set_active(shown)
        self.revealer.set_reveal_child(shown)
        self.revealer.set_transition_duration(250)
        if self.list.get_selected_row() is not self.rows[number]:
            self.list.select_row(self.rows[number])
        self.win.update_actions()  # Previous and Next (their actions: a button's own sensitivity wouldn't last)
        self.scroller.get_vadjustment().set_value(0)
        self._update_counts()

    def step(self, delta):
        """Ctrl+PgUp / Ctrl+PgDn: the previous or next question, the editor focused."""
        if self.current is None:
            return
        i = self.numbers.index(self.current) + delta
        if 0 <= i < len(self.numbers):
            self.show_question(self.numbers[i])
            self.view.grab_focus()

    def _buffer(self, number):
        buf = self.buffers.get(number)
        if buf is None:
            buf = self.buffers[number] = DraftBuffer(number, self.attempt.answer(number).text)
            self._handlers.append((buf, buf.connect("changed", weak_handler(self._changed))))
        return buf

    def _text(self, number):
        buf = self.buffers.get(number)
        return buf.get_text(*buf.get_bounds(), False) if buf is not None else self.attempt.answer(number).text

    def _changed(self, buf):
        could_finish = self.can_finish()
        self._dirty = True
        text = buf.get_text(*buf.get_bounds(), False)
        if buf.number == self.current:
            self._show_counts(text)
        self._update_row(buf.number, text)
        self._update_progress()
        self._schedule_save()
        if self.can_finish() != could_finish:
            self.win.update_actions()

    def toggle_details(self, on):
        """Reveal: show or hide the question's details. Shown once, it counts as revealed in
        this attempt, even when hidden again."""
        if self.current is None:
            return
        self.revealer.set_reveal_child(on)
        if on:
            self.shown.add(self.current)
        else:
            self.shown.discard(self.current)
        answer = self.attempt.answers.setdefault(self.current, Answer())
        if on and not answer.revealed:
            answer.revealed = True
            self._dirty = True
            self._update_row(self.current)
            self._update_progress()
            self._schedule_save()
            self.win.update_actions()

    def load_original(self):
        """Load My Original Answer: the answer given on TopCoding, in place of the editor's
        text (asked first if there is any); Ctrl+Z takes it back."""
        q = self.questions.get(self.current)
        if q is None or q.answer is None:
            return
        buf = self._buffer(q.number)
        text = buf.get_text(*buf.get_bounds(), False)
        if text == q.answer:
            self.view.grab_focus()
            return
        if not text.strip():
            self._put(buf, q.answer)
            return
        dlg = Adw.AlertDialog(heading="Replace Your Answer?",
                              body=f"Question {q.number} already has an answer here. Replace it with the one you "
                                   "gave on TopCoding? Ctrl+Z brings yours back.")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("replace", "Replace")
        dlg.set_response_appearance("replace", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        dlg.connect("response", lambda _d, response: response == "replace" and self._put(buf, q.answer))
        dlg.present(self.win)

    def _put(self, buf, text):
        """Replace buf's text as one step Ctrl+Z undoes."""
        buf.begin_user_action()
        buf.delete(*buf.get_bounds())
        buf.insert(buf.get_start_iter(), text)
        buf.end_user_action()
        buf.place_cursor(buf.get_start_iter())
        if self.view is not None and self.view.get_buffer() is buf:
            self.view.grab_focus()

    def show_attempts(self):
        q = self.questions.get(self.current)
        if q is not None:
            AttemptsDialog(self.a, q).present(self.win)

    # -- finishing --------------------------------------------------------------------

    def can_finish(self):
        """Whether there is anything to finish: an answer, or a question revealed."""
        return self.attempt is not None and (bool(self._drafted) or any(a.revealed for a in self.attempt.answers.values()))

    def finish_attempt(self):
        """Finish Attempt: asks, then keeps the answers among the attempts and starts blank."""
        if not self.can_finish():
            self.win.toast("Answer or reveal a question first")
            return
        drafted = len(self._drafted)
        dlg = Adw.AlertDialog(heading="Finish This Attempt?",
                              body=f"Your answers ({drafted} of {len(self.numbers)} questions) are kept in Earlier "
                                   "Attempts, and the next attempt starts blank.")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("finish", "Finish Attempt")
        dlg.set_response_appearance("finish", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("finish")
        dlg.set_close_response("cancel")
        dlg.connect("response", lambda _d, response: response == "finish" and self._finish())
        dlg.present(self.win)

    def _finish(self):
        if self.released:
            return
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        snapshot = self._snapshot()
        self._dirty = self._again = False
        self.set_sensitive(False)  # nothing typed now would be in either attempt
        WORKER.run(lambda f=self.file, s=snapshot: f.finish(s),
                   done=lambda result, s=snapshot: self._finished(result, s), failed=self._finish_failed)

    def _finished(self, result, attempt):
        """attempt: the one just finished, now the last (the list shows it)."""
        _path, kept = result
        if self.released:
            return
        self.set_sensitive(True)
        self.last = attempt
        self.a.attempts += 1
        self.a.has_draft = False
        self.attempt = Attempt()
        self._disconnect_buffers()
        self.buffers.clear()
        self.shown.clear()
        for n in self.rows:
            self._update_row(n)
        self.show_question(self.numbers[0])
        self._update_progress()
        self._show_saved("")
        self.win.toast("Attempt finished. Its answers are in Earlier Attempts; this one starts blank.")
        if kept is not None:
            self.win.toast("Another computer had changed this draft. Its version is kept in Earlier Attempts too.")
        self.win.update_actions()
        self.win.assessments_changed()
        self.view.grab_focus()

    def _finish_failed(self, error):
        if self.released:
            return
        self.set_sensitive(True)
        self._dirty = True
        self.win.toast(f"Couldn't finish the attempt: {getattr(error, 'strerror', None) or error}")

    # -- saving -----------------------------------------------------------------------

    def _snapshot(self):
        """The attempt with the editors' text, as plain data for the worker's thread; dated
        now if this is its first save."""
        if self.attempt.started is None:
            self.attempt.started = datetime.now().astimezone()
        answers = {n: Answer(a.text, a.revealed, dict(a.extra)) for n, a in self.attempt.answers.items()}
        for n in self.buffers:
            answers.setdefault(n, Answer()).text = self._text(n)
        return Attempt(started=self.attempt.started, answers=answers, origin=self.attempt.origin,
                       format=self.attempt.format, extra=dict(self.attempt.extra))

    def _schedule_save(self):
        if self._save_src:
            GLib.source_remove(self._save_src)
        self._save_src = GLib.timeout_add(SAVE_DELAY, self._autosave)
        self._show_saved("Saving…")

    def _autosave(self):
        self._save_src = None
        self.save()
        return GLib.SOURCE_REMOVE

    def save(self):
        """Write the draft in the background if it changed: one write at a time, and a
        change made meanwhile is written when it is done."""
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        if not self._dirty or self.attempt is None:
            return
        if self._writing:
            self._again = True
            return
        self._write()

    def _write(self):
        snapshot = self._snapshot()
        self._dirty = False
        self._writing = True
        return WORKER.run(lambda f=self.file, s=snapshot: f.write(s), done=self._saved, failed=self._save_failed)

    def flush(self, wait=False):
        """Write the draft now if it changed: before Earlier Attempts reads the folder,
        when the page goes, when the window closes. wait: block until it is written,
        raising OSError if it couldn't be."""
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        future = self._write() if self._dirty and self.attempt is not None else None
        if wait:
            if future is not None:
                future.result()
            WORKER.wait()

    def _saved(self, result):
        self._writing = False
        kept, set_aside = result
        if self.released:
            return
        self.a.has_draft = True
        if kept is not None:
            self.win.toast("Another computer changed this draft. Its version is kept in Earlier Attempts.")
        if set_aside is not None:
            self.win.toast(f"The draft on disk couldn't be read. It was kept as {set_aside.name}.")
        if self._again:
            self._again = False
            self.save()
        elif not self._dirty and not self._save_src:
            self._show_saved("Saved")

    def _save_failed(self, error):
        self._writing = False
        self._again = False
        self._dirty = True  # written with the next change, or when the page goes
        if not self.released:
            self._show_saved(f"Not saved: {getattr(error, 'strerror', None) or error}")

    def _show_saved(self, text):
        self.saved.set_label(text)
        self.saved.set_tooltip_text("Your answers are saved as you type" if text == "Saved" else None)

    # -- showing ----------------------------------------------------------------------

    def _fill_details(self, q):
        """What Reveal shows for question q."""
        while (child := self.details.get_first_child()) is not None:
            self.details.remove(child)
        graded = self.a.report.graded
        score = f"Score {q.score}" if q.score is not None else ("" if graded else "Not graded in this file")
        self.details.append(_section("Your Original Answer", q.answer, "No answer provided", aside=score,
                                     result=store.result_category(q.score) if self.win.highlights else None))
        self.details.append(_section("Sample Answer", q.sample, "This report has no sample answer for it."))
        if q.feedback is not None:
            self.details.append(_section("Feedback", q.feedback, ""))
        else:
            self.details.append(_section("Feedback", None, "No feedback (score 0)." if graded else
                                         "Not graded in this file: import the report again once TopCoding has "
                                         "graded it."))

    def _update_counts(self):
        if self.current is not None:
            self._show_counts(self._text(self.current))

    def _show_counts(self, text):
        words = store.count_words(text)
        self.counts.set_label(f"{words} word{'s' if words != 1 else ''} · "
                              f"{len(text)} character{'s' if len(text) != 1 else ''}")

    def _update_row(self, number, text=None):
        if self.attempt is None:
            return
        drafted = bool((self._text(number) if text is None else text).strip())
        if drafted:
            self._drafted.add(number)
        else:
            self._drafted.discard(number)
        q = self.questions.get(number)
        self.rows[number].set_last(_last_label(self.last, number))
        self.rows[number].set_state(drafted, self.attempt.answer(number).revealed, q.score if q else None,
                                    self.win.highlights)

    def _update_progress(self):
        if self.attempt is None:
            self.progress_label.set_label("")
            self.progress.set_fraction(0)
            return
        total = len(self.numbers)
        drafted = len(self._drafted)
        revealed = sum(1 for n in self.numbers if self.attempt.answer(n).revealed)
        self.progress_label.set_label(f"Practice attempt {self.a.attempts + 1} · {drafted} of {total} drafted · "
                                      f"{revealed} revealed")
        self.progress.set_fraction(drafted / total if total else 0)

    def show_list(self, show):
        """F9: show or hide the question list. A narrow window shows it in the question's
        place, until a question is chosen."""
        self.list_pane.set_visible(show)
        if self.bin.get_current_breakpoint() is self.narrow:
            self.question_pane.set_visible(not show)

    def _list_shown(self, pane, _pspec):
        action = self.win.lookup_action("sidebar")
        if action is not None:
            action.set_state(GLib.Variant.new_boolean(pane.get_visible()))
        if pane.get_visible():
            self.paned.set_position(self._list_width)
        self._keep_focus()  # the paned may have the focus already (F8): no focus change tells then

    def _keep_focus(self, *_):
        # GTK moves the focus out of a side that is hidden (F9, a narrow window) to the paned,
        # on the next frame, where the arrow keys would move the hidden handle: it goes to the
        # side shown instead, to the answer or else to the question chosen in the list. With
        # both sides shown, the paned keeps it (F8: the handle, moved with the arrow keys).
        if self.win.get_focus() is not self.paned or (self.list_pane.get_visible()
                                                       and self.question_pane.get_visible()):
            return
        if self.question_pane.get_visible():
            self.view.grab_focus()
        elif (row := self.list.get_selected_row()) is not None:
            row.grab_focus()

    def _list_resized(self, paned, _pspec):
        # Not a width a narrower window cut the list down to (GTK keeps the position at most
        # max-position): at max-position, only a width wider than before, which is a drag as
        # far as it goes. Nor one it leaves no room to change: a window that narrows by much
        # at once (unmaximized, tiled) is too narrow for both sides until the breakpoint
        # drops the list.
        position, most = paned.get_position(), paned.props.max_position
        if paned.props.min_position < most and (position < most or position > self._list_width):
            self._list_width = position

    def _room_changed(self, paned, _pspec):
        # The window widened: the list grows back to the width a narrower one took from it.
        width = min(self._list_width, paned.props.max_position)
        if self.list_pane.get_visible() and paned.get_position() < width:
            paned.set_position(width)

    # -- going ------------------------------------------------------------------------

    def _disconnect_buffers(self):
        keep = []
        for obj, handler in self._handlers:
            if isinstance(obj, DraftBuffer):
                obj.disconnect(handler)
            else:
                keep.append((obj, handler))
        self._handlers = keep

    def release(self):
        """The page is gone (back to the list, or the window closed): let go of its
        widgets, whose handlers hold it (R29). Call flush() first."""
        if self.released:
            return
        self.released = True
        if self._save_src:
            GLib.source_remove(self._save_src)
            self._save_src = None
        self.view.stop()
        for obj, handler in self._handlers:
            obj.disconnect(handler)
        self._handlers = []
        self.buffers.clear()
        self.set_child(None)
        self.paned = self.list_pane = self.question_pane = self.bin = self.narrow = None
        self.list = self.rows = self.stack = self.view = self.scroller = self.details = None
        self.revealer = self.reveal_btn = self.load_btn = self.prev_btn = self.next_btn = self.problem = None
        self.heading = self.prompt = self.counts = self.saved = self.facts = self.final_score = self.grading = None
        self.progress = self.progress_label = self.title = self.win = None


# Handlers on the page's widgets find the page when the event comes (CR18): one that held
# it would make a cycle through GTK.

def _page(widget):
    w = widget
    while w is not None and not isinstance(w, PracticePage):
        w = w.get_parent()
    return w


def _row_selected(listbox, row):
    page = _page(listbox)
    if page is not None and row is not None and row.number != page.current:
        page.show_question(row.number)


def _row_activated(listbox, _row):
    page = _page(listbox)
    if page is not None:
        if not page.question_pane.get_visible():  # a narrow window shows the list in its place
            page.show_list(False)
        page.view.grab_focus()


def _load_clicked(button):
    page = _page(button)
    if page is not None:
        page.load_original()


def _reveal_toggled(button):
    page = _page(button)
    if page is not None and page.current is not None and button.get_active() != (page.current in page.shown):
        page.toggle_details(button.get_active())


def _last_label(attempt, number):
    """What you did with question `number` in attempt (your last finished one): its
    answer's length, not its text, and no score (the app doesn't grade). None without one."""
    if attempt is None:
        return None
    answer = attempt.answer(number)
    words = store.count_words(answer.text) if answer.text.strip() else 0
    did = f"{words} word{'s' if words != 1 else ''}" if words else "left blank"
    return f"Last time: {did}" + (" · revealed" if answer.revealed else "")


def _language_hints(path, own):
    """On WORKER: (the chapter's chosen language or None, its text) for pick_language; the
    assessment's own text (own) if the chapter can't be read."""
    try:
        doc = Document.load(path)
    except (OSError, ValueError):
        return None, own
    return doc.lang, " ".join(n.text for n in doc.root.walk())


def _show_result(score_label, result):
    """A score's look: in TopCoding's color for it (result: assessments.result_category or
    final_category), or plain (None: highlights off, or ungraded). Its text says the same
    either way."""
    for category in (store.GOOD, store.PARTIAL, store.POOR):
        set_class(score_label, f"result-{category}", category == result)
    set_class(score_label, "result-score", result is not None)
    set_class(score_label, "dim-label", result is None)


def _section(title, text, missing, aside="", result=None):
    """A part of what Reveal shows: its title (and score), then the text, or `missing`.
    result: the score's category (assessments.result_category), coloring the part too."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    if result is not None:
        box.add_css_class("assessment-result")
        box.add_css_class(f"result-{result}")
    head = Gtk.Box(spacing=12)
    head.append(Gtk.Label(label=title, xalign=0, hexpand=True, css_classes=["heading"]))
    if aside:
        label = Gtk.Label(label=aside, css_classes=["numeric"])
        _show_result(label, result)
        head.append(label)
    box.append(head)
    body = Gtk.Label(label=text if text is not None else missing, xalign=0, wrap=True,
                     wrap_mode=Pango.WrapMode.WORD_CHAR, selectable=True, css_classes=["assessment-text"])
    if text is None:
        body.add_css_class("dim-label")
    box.append(body)
    return box


def _score(report):
    pct = f" ({report.final_percent}%)" if report.final_percent else ""
    return f"{report.final_result}{pct}"
