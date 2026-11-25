"""Earlier Attempts: the finished practice attempts at one question of an assessment,
newest first, each answer read-only and, with Compare with Sample Answer, beside the
sample answer. Modelled on Earlier Versions (versions.py).

The attempts are listed by their file names when the dialog opens; each is read in the
background afterwards (helpers.WORKER), so the dialog shows at once however many there
are (CR32 in CODE_REVIEW.md)."""
from __future__ import annotations

from gi.repository import Adw, GLib, Gtk

from .. import assessments as store
from .helpers import WORKER
from .versions import _when


class AttemptRow(Adw.ActionRow):
    """A finished attempt (file: an assessments.AttemptFile); attempt is None until read."""

    def __init__(self, file, **props):
        super().__init__(**props)
        self.file, self.attempt, self.error = file, None, None


class AttemptsDialog(Adw.Dialog):
    def __init__(self, assessment, question):
        super().__init__(title="Earlier Attempts", content_width=900, content_height=620)
        self.question = question
        self._open = True
        tv = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Earlier Attempts", subtitle=f"Question {question.number}"))
        self.compare = Gtk.ToggleButton(label="Compare with Sample Answer", sensitive=question.sample is not None,
                                        tooltip_text="Show the sample answer beside yours" if question.sample
                                        else "This question has no sample answer")
        self.compare.connect("toggled", lambda b: self.sample_panel.set_visible(b.get_active()))
        header.pack_end(self.compare)
        tv.add_top_bar(header)

        self.stack = Gtk.Stack()
        self.stack.add_named(Adw.Spinner(), "loading")
        self.stack.add_named(Adw.StatusPage(
            icon_name="document-open-recent-symbolic", title="No Earlier Attempts",
            description="Finish an attempt to keep your answers here, then compare them with the sample answer."),
            "empty")
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["navigation-sidebar"])
        self.list.connect("row-selected", self._selected)
        self.answer_heading = Gtk.Label(xalign=0, css_classes=["heading"])
        self.answer = _text_label()
        self.sample = _text_label(question.sample or "")
        answer_panel = _panel(self.answer_heading, self.answer)
        self.sample_panel = _panel(Gtk.Label(label="Sample Answer", xalign=0, css_classes=["heading"]), self.sample)
        self.sample_panel.set_visible(False)
        panels = Gtk.Box(homogeneous=True, spacing=0)
        panels.append(answer_panel)
        panels.append(self.sample_panel)
        self.stack.add_named(Gtk.Paned(
            position=240, shrink_start_child=False, resize_start_child=False,
            start_child=Gtk.ScrolledWindow(child=self.list, hscrollbar_policy=Gtk.PolicyType.NEVER),
            end_child=panels), "attempts")
        tv.set_content(self.stack)
        self.set_child(tv)
        self.connect("closed", lambda *_: self._release())
        WORKER.run(lambda a=assessment: store.list_attempts(a), done=self._listed, failed=self._failed)

    def _listed(self, files):
        if not self._open:
            return
        if not files:
            self.stack.set_visible_child_name("empty")
            return
        for f in files:
            row = AttemptRow(f, title=_when(f.when), subtitle="…", use_markup=False)
            self.list.append(row)
            WORKER.run(lambda p=f.path: store.read_attempt(p),
                       done=lambda attempt, r=row: self._read(r, attempt, None),
                       failed=lambda e, r=row: self._read(r, None, e))
        self.stack.set_visible_child_name("attempts")
        self.list.select_row(self.list.get_row_at_index(0))

    def _failed(self, error):
        if self._open:
            reason = GLib.markup_escape_text(str(getattr(error, "strerror", None) or error))  # the description is markup
            self.stack.add_named(Adw.StatusPage(icon_name="dialog-error-symbolic", title="Couldn't List the Attempts",
                                                description=reason), "error")
            self.stack.set_visible_child_name("error")

    def _read(self, row, attempt, error):
        if not self._open:
            return
        row.attempt, row.error = attempt, error
        row.set_subtitle(_summary(attempt, self.question.number) if attempt else "can't be read")
        if self.list.get_selected_row() is row:
            self._selected(self.list, row)

    def _selected(self, _lb, row):
        if row is None:
            return
        self.answer_heading.set_label(f"Your Answer, {row.get_title()}")
        if row.attempt is None:
            text = "Reading…" if row.error is None else f"This attempt can't be read: {row.error}"
        else:
            text = row.attempt.answer(self.question.number).text.strip("\n") or "No answer to this question in this attempt."
        self.answer.set_label(text)

    def _release(self):
        """Let go of the content once closed: the handlers above hold the dialog (R29)."""
        self._open = False
        self.set_child(None)
        self.compare = self.stack = self.list = self.answer = self.sample = self.sample_panel = None
        self.answer_heading = None


def _summary(attempt, number):
    """'142 words · revealed · from another computer', or 'no answer'."""
    a = attempt.answer(number)
    words = store.count_words(a.text)
    parts = [f"{words} word{'s' if words != 1 else ''}" if words else "no answer"]
    if a.revealed:
        parts.append("revealed")
    if attempt.origin == store.ELSEWHERE:
        parts.append("from another computer")
    return " · ".join(parts)


def _text_label(text=""):
    return Gtk.Label(label=text, xalign=0, yalign=0, wrap=True, selectable=True, valign=Gtk.Align.START,
                     css_classes=["assessment-text"])


def _panel(heading, label):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                  margin_start=16, margin_end=16)
    box.append(heading)
    box.append(label)
    return Gtk.ScrolledWindow(child=box, hexpand=True, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
