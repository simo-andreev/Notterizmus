"""OutlineEditor, part: spelling fixes and word completion (Ctrl+Space)."""
from __future__ import annotations

from gi.repository import Gdk, GLib, Graphene, Gtk

from ..completion import complete, count_words, dictionary_words, node_texts
from ..model import Run
from ..spell import should_check
from .helpers import run_once
from .richtext import SPELL
from .rows import _mods
from .outline_menus import MenuRow, _digit, _number_rows


class AssistMixin:
    """Mixed into OutlineEditor (outline.py); uses its state."""

    # -- spelling ------------------------------------------------------------------------

    def set_spelling(self, speller, enabled):
        SPELL["speller"] = speller
        SPELL["enabled"] = enabled
        for v in self.all_views():
            v.recheck_spelling()

    def _spell_replace(self, word):
        self._replace_word(word)

    def _replace_word(self, word):
        """Replace the word recorded in self._ctx, keeping its bold/italic."""
        if not self._ctx:
            return
        view, s, e = self._ctx
        buf = view.get_buffer()
        it = buf.get_iter_at_offset(s)
        fmt = (it.has_tag(view.tag_bold), it.has_tag(view.tag_italic))
        view.grab_focus()
        view.select_range(s, e)
        with self._op():
            view.insert_runs([Run(word, *fmt)])

    def _spell_add(self, word):
        if SPELL["speller"]:
            SPELL["speller"].add(word)
            for v in self.all_views():
                v.recheck_spelling()

    def _spell_ignore(self, word):
        if SPELL["speller"]:
            SPELL["speller"].ignore(word)
            for v in self.all_views():
                v.recheck_spelling()

    # -- Ctrl+Space: spelling fixes and word completion ------------------------------------

    def _assist_sections(self, view):
        """[(title, [(label, callback|None)])] for the word at the cursor."""
        self._ctx = None
        it = view.cursor_iter()
        wb = view.word_bounds(it)
        if wb is None:
            return []
        s, e = wb
        text = view.get_plain()
        word, prefix = text[s:e], text[s:it.get_offset()]
        self._ctx = (view, s, e)
        sp = SPELL["speller"]
        comps = []
        if prefix:
            if self._assist_counts is None:
                # Once per popup: while it is open only the word being typed changes, and that
                # word isn't counted. Every key used to count the chapter's words again and look
                # at every other chapter of the book (CR34 in CODE_REVIEW.md).
                current = count_words(node_texts(self.doc.root))
                current[word] -= 1  # the word being typed doesn't count as a source
                path = self.doc.path
                self._assist_counts = (+current, self._book_words.counts(path.parent, exclude=path) if path else None)
            current, book = self._assist_counts
            words = dictionary_words(sp.tag_for(prefix)) if sp is not None else []
            comps = complete(prefix, current, book, words)
        sections = []
        if comps:
            sections.append(("Complete", [(c, lambda c=c: self._replace_word(c)) for c in comps]))
        # While a word is being completed it is "misspelled" only because it's unfinished,
        # so spelling fixes show when nothing completes it or the cursor is inside it.
        mid_word = it.get_offset() < e
        if (mid_word or not comps) and SPELL["enabled"] and sp is not None \
                and should_check(word) and not sp.check(word):
            sugg = sp.suggest(word)
            rows = [(w, lambda w=w: self._replace_word(w)) for w in sugg]
            if not sugg:
                rows.append(("No spelling suggestions", None))
            rows.append((f"Add “{word}” to Dictionary", lambda: self._spell_add(word)))
            rows.append(("Ignore", lambda: self._spell_ignore(word)))
            sections.insert(0, ("Spelling", rows))
        return sections

    def show_assist(self, view):
        """Popup at the cursor with spelling fixes and completions. Typing keeps going
        into the text and refilters; Enter or Tab picks, Esc closes."""
        self.clear_carets()
        pop = Gtk.Popover(has_arrow=False)
        pop.add_css_class("menu")
        pop.add_css_class("ntz-menu")
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, activate_on_single_click=True)
        pop.set_child(lb)
        pop.set_parent(view)
        self._assist_pop = pop

        def place():
            rect = view.cursor_rect()
            pop.set_pointing_to(rect)
            ok, pt = view.compute_point(self, Graphene.Point().init(rect.x, rect.y))
            pop.set_position(Gtk.PositionType.TOP if ok and pt.y > self.get_height() * 0.6
                             else Gtk.PositionType.BOTTOM)

        def add_row(child, cb=None, kind=None):
            row = MenuRow(choice=kind == "choice", cb=cb, activatable=cb is not None, selectable=False,
                          can_focus=cb is not None)
            row.set_child(child)
            if kind:
                row.add_css_class(kind)
            lb.append(row)
            return row

        def fill():
            while (c := lb.get_first_child()) is not None:
                lb.remove(c)
            sections = self._assist_sections(view)
            first = None
            for title, rows in sections:
                if lb.get_first_child() is not None:
                    add_row(Gtk.Separator(), kind="sep")
                head = Gtk.Label(label=title, xalign=0, css_classes=["heading", "dim-label"])
                add_row(head, kind="head")
                for label, cb in rows:
                    r = add_row(Gtk.Label(label=label, xalign=0), cb, kind="choice")
                    r.set_sensitive(cb is not None)
                    first = first or (r if cb else None)
            if not sections:
                add_row(Gtk.Label(label="No suggestions", xalign=0, css_classes=["dim-label"]))
            numbered.clear()
            numbered.update(_number_rows(lb))
            place()
            return first, bool(sections)

        numbered = {}

        def pick(row):
            if row is None or row.cb is None:
                return
            pop.popdown()
            cb = row.cb

            def run():
                cb()
                view.grab_focus()
            GLib.idle_add(run_once, run)

        lb.connect("row-activated", lambda _lb, row: pick(row))

        def on_key(_c, keyval, _kc, state):
            name = Gdk.keyval_name(keyval)
            ctrl, shift, alt = _mods(state)
            n = None if ctrl or alt else _digit(keyval)
            if n in numbered:
                pick(numbered[n])
                return True
            if name in ("Up", "Down", "Page_Up", "Page_Down", "Return", "KP_Enter", "space") \
                    and not ctrl:
                return False if name != "space" else self._assist_type(view, " ", pop)
            if name == "Tab":
                pick(lb.get_focus_child())
                return True
            if name == "Escape":
                pop.popdown()
                return True
            buf = view.get_buffer()
            if name == "BackSpace":
                it = view.cursor_iter()
                if it.get_offset() > 0:
                    start = it.copy()
                    start.backward_char()
                    buf.delete(start, it)
            else:
                uni = Gdk.keyval_to_unicode(keyval)
                if ctrl or alt or not uni or not chr(uni).isprintable():
                    return False
                buf.insert_interactive_at_cursor(chr(uni), -1, True)
            first, any_ = fill()
            if not any_:
                pop.popdown()
            elif first is not None:
                first.grab_focus()
            return True

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", on_key)
        pop.add_controller(keys)

        def closed(p):
            self._assist_pop = None
            view.grab_focus()
            GLib.idle_add(run_once, p.unparent)

        pop.connect("closed", closed)
        self._assist_counts = None  # counted afresh for this popup
        first, _ = fill()
        pop.popup()
        if first is not None:
            GLib.idle_add(run_once, first.grab_focus)
        return pop

    def _assist_type(self, view, ch, pop):
        """A space ends the word: type it and close the popup."""
        view.get_buffer().insert_interactive_at_cursor(ch, -1, True)
        pop.popdown()
        return True
