"""Practicing one assessment (assessments_window.py): its questions in a list beside the
one being answered, an editor for each answer that starts blank, and behind Reveal what
TopCoding showed: your original answer with its score, the sample answer and the
feedback.

The answers are a practice attempt (assessments.Attempt). It is saved as the assessment's
draft 800 ms after a change, and when the page or the window goes: the text is copied
here, on the main loop, and written by helpers.WORKER, one write at a time, the newest
text winning. Finish Attempt keeps it among the attempts and starts a blank one; Earlier
Attempts (attempts.py) shows them.

The window's actions drive the page: win.prev-question and win.next-question (Ctrl+PgUp,
Ctrl+PgDn), win.sidebar (F9: the question list), win.finish, win.attach and win.attempts."""
from __future__ import annotations

from datetime import datetime

from gi.repository import Adw, Gio, GLib, Gtk, Pango

from .. import assessments as store
from ..assessments import Answer, Attempt
from .attempts import AttemptsDialog
from .helpers import WORKER, weak_handler

SAVE_DELAY = 800  # ms after the last change, as for chapters


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
        self.set_text(text)  # (not undoable: it was there when the page opened)


class QuestionRow(Gtk.ListBoxRow):
    """A question in the list: its number, its prompt, and icons for what you did with it
    in this attempt (answered it, revealed it)."""

    def __init__(self, question, **props):
        super().__init__(**props)
        self.number = question.number
        box = Gtk.Box(spacing=8, margin_top=4, margin_bottom=4)
        num = Gtk.Label(label=str(question.number), width_chars=2, xalign=1, css_classes=["dim-label", "numeric"])
        prompt = Gtk.Label(label=" ".join(question.prompt.split()), xalign=0, hexpand=True,
                           ellipsize=Pango.EllipsizeMode.END)
        self.drafted = Gtk.Image(icon_name="document-edit-symbolic", visible=False)
        self.revealed = Gtk.Image(icon_name="view-reveal-symbolic", visible=False)
        for w in (num, prompt, self.drafted, self.revealed):
            box.append(w)
        self.set_child(box)
        self.set_state(False, False)

    def set_state(self, drafted, revealed):
        self.drafted.set_visible(drafted)
        self.revealed.set_visible(revealed)
        state = ("drafted" if drafted else "unanswered") + (", revealed" if revealed else "")
        self.set_tooltip_text(f"Question {self.number}: {state}")
        self.update_property([Gtk.AccessibleProperty.DESCRIPTION], [state])


class PracticePage(Adw.NavigationPage):
    __gtype_name__ = "NtzPracticePage"

    def __init__(self, window, assessment, chapter_label):
        super().__init__(title=assessment.report.title, tag="practice")
        self.win = window
        self.a = assessment
        self.questions = {q.number: q for q in assessment.report.questions}
        self.numbers = [q.number for q in assessment.report.questions]
        self.file = DraftFile(assessment)
        self.attempt = None   # the attempt in progress, once its draft is read
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
        self.split = Adw.OverlaySplitView(sidebar=self._build_list(), content=self._build_content(),
                                          min_sidebar_width=220, max_sidebar_width=320)
        for signal, method in (("notify::show-sidebar", self._sidebar_shown), ("notify::collapsed", self._collapsed)):
            self._handlers.append((self.split, self.split.connect(signal, weak_handler(method))))
        tv.set_content(self.split)
        # A narrow window shows the question list over the question. The breakpoint is the
        # page's own: one added to the window would hold the page after it is gone.
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 720px"))
        narrow.add_setter(self.split, "collapsed", True)
        bin_ = Adw.BreakpointBin(child=tv, width_request=360, height_request=320)
        bin_.add_breakpoint(narrow)
        self.set_child(bin_)
        self.set_report(assessment)
        WORKER.run(self.file.read, done=self._loaded, failed=self._load_failed)

    # -- building ---------------------------------------------------------------------

    def _build_header(self, chapter_label):
        header = Adw.HeaderBar()
        self.title = Adw.WindowTitle(title=self.a.report.title, subtitle=chapter_label)
        header.set_title_widget(self.title)
        header.pack_start(Gtk.ToggleButton(icon_name="sidebar-show-symbolic", tooltip_text="Questions (F9)",
                                           action_name="win.sidebar"))
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
        return Gtk.ScrolledWindow(child=self.list, hscrollbar_policy=Gtk.PolicyType.NEVER)

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
        self.view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=10, bottom_margin=10,
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
        self.facts = Gtk.Label(xalign=0, wrap=True, css_classes=["dim-label"])
        self.grading = Gtk.Label(xalign=0, wrap=True, css_classes=["warning"])
        line = Gtk.Box(spacing=12)
        self.progress_label = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.progress = Gtk.ProgressBar(valign=Gtk.Align.CENTER, width_request=160)
        line.append(self.progress_label)
        line.append(self.progress)
        for w in (self.facts, self.grading, line):
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
                 f"TopCoding attempt {r.attempt}" if r.attempt else "",
                 f"Original score {_score(r)}" if r.final_result else ""]
        self.facts.set_label(" · ".join(f for f in facts if f))
        self.grading.set_label("" if r.graded else "Not graded in this file. Import the report again after "
                                                   "TopCoding grades it to see your scores and feedback.")
        self.grading.set_visible(not r.graded)
        if self.current is not None:
            self._fill_details(self.questions[self.current])
        self._update_progress()

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
        WORKER.run(lambda f=self.file, s=snapshot: f.finish(s), done=self._finished, failed=self._finish_failed)

    def _finished(self, result):
        _path, kept = result
        if self.released:
            return
        self.set_sensitive(True)
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
        self.details.append(_section("Your Original Answer", q.answer, "No answer provided", aside=score))
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
        self.rows[number].set_state(drafted, self.attempt.answer(number).revealed)

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

    def _sidebar_shown(self, split, _pspec):
        action = self.win.lookup_action("sidebar")
        if action is not None:
            action.set_state(GLib.Variant.new_boolean(split.get_show_sidebar()))

    def _collapsed(self, split, _pspec):
        if split.get_collapsed():  # the list would cover the question
            split.set_show_sidebar(False)

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
        for obj, handler in self._handlers:
            obj.disconnect(handler)
        self._handlers = []
        self.buffers.clear()
        self.set_child(None)
        self.split = self.list = self.rows = self.stack = self.view = self.scroller = self.details = None
        self.revealer = self.reveal_btn = self.load_btn = self.prev_btn = self.next_btn = self.problem = None
        self.heading = self.prompt = self.counts = self.saved = self.facts = self.grading = None
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
        if page.split.get_collapsed():
            page.split.set_show_sidebar(False)
        page.view.grab_focus()


def _load_clicked(button):
    page = _page(button)
    if page is not None:
        page.load_original()


def _reveal_toggled(button):
    page = _page(button)
    if page is not None and page.current is not None and button.get_active() != (page.current in page.shown):
        page.toggle_details(button.get_active())


def _section(title, text, missing, aside=""):
    """A part of what Reveal shows: its title (and score), then the text, or `missing`."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    head = Gtk.Box(spacing=12)
    head.append(Gtk.Label(label=title, xalign=0, hexpand=True, css_classes=["heading"]))
    if aside:
        head.append(Gtk.Label(label=aside, css_classes=["dim-label", "numeric"]))
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
