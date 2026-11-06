"""A small GtkTextView with bold/italic runs, spell-check underlines and extra carets."""
from __future__ import annotations

from gi.repository import Gdk, GLib, GObject, Graphene, Gtk, Pango

from ..model import Run, normalize_runs
from ..spell import WORD_RE, should_check

# Shared spell-check state, set by the editor: {"speller": Speller|None, "enabled": bool}
SPELL = {"speller": None, "enabled": False}


class RichText(Gtk.TextView):
    __gtype_name__ = "NtzRichText"
    __gsignals__ = {"content-changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, **kw):
        super().__init__(wrap_mode=Gtk.WrapMode.WORD_CHAR, hexpand=True, accepts_tab=False,
                         top_margin=1, bottom_margin=1, **kw)
        self.add_css_class("rt")
        buf = self.get_buffer()
        buf.set_enable_undo(False)  # the editor keeps a document-wide history
        self.tag_bold = buf.create_tag("bold", weight=Pango.Weight.BOLD)
        self.tag_italic = buf.create_tag("italic", style=Pango.Style.ITALIC)
        red = Gdk.RGBA()
        red.parse("#e01b24")
        self.tag_spell = buf.create_tag("misspelled", underline=Pango.Underline.ERROR, underline_rgba=red)
        # find bar highlights: every match, and the current one
        found, current = Gdk.RGBA(), Gdk.RGBA()
        found.parse("rgba(245, 194, 17, 0.35)")
        current.parse("rgba(255, 120, 0, 0.75)")
        self.tag_found = buf.create_tag("found", background_rgba=found)
        self.tag_found_current = buf.create_tag("found-current", background_rgba=current)
        self._pending = None  # {"bold":..,"italic":..} after Ctrl+B/I with no selection
        self._loading = False
        self._inserting = False
        self._raw = False
        self._spell_src = None
        self.carets = []  # extra (multi-cursor) carets: GtkTextMarks
        self.last_edit = None  # ("ins"|"del", text, start offset) for undo grouping
        self._size_fix = None
        buf.connect("insert-text", self._before_insert)
        buf.connect_after("insert-text", self._after_insert)
        buf.connect("changed", self._on_changed)
        buf.connect("mark-set", self._on_mark_set)
        buf.connect_after("apply-tag", self._on_tag)
        buf.connect_after("remove-tag", self._on_tag)

    # -- content -------------------------------------------------------------

    def set_runs(self, runs):
        buf = self.get_buffer()
        self._loading = True
        buf.set_text("")
        for r in runs:
            buf.insert_with_tags(buf.get_end_iter(), r.text, *self._tags_for(r.bold, r.italic))
        self._loading = False
        self.schedule_spell(0)

    def _tags_for(self, bold, italic):
        return [t for t, on in ((self.tag_bold, bold), (self.tag_italic, italic)) if on]

    def insert_runs(self, runs):
        """Insert formatted runs at the cursor (replacing the selection)."""
        buf = self.get_buffer()
        self._raw = True
        buf.begin_user_action()
        buf.delete_selection(True, True)
        it = self.cursor_iter()
        for r in runs:
            text = r.text.replace("\n", " ")
            if text:
                buf.insert_with_tags(it, text, *self._tags_for(r.bold, r.italic))
        buf.place_cursor(it)
        buf.end_user_action()
        self._raw = False
        self.last_edit = ("paste", "", self.cursor_offset())
        self._emit()

    def replace_range(self, start, end, text):
        """Replace characters start..end with text, keeping the first replaced character's
        bold/italic. Reported as one content change."""
        buf = self.get_buffer()
        fmt = self._fmt_at(buf.get_iter_at_offset(start))
        self._raw = True
        buf.begin_user_action()
        buf.delete(buf.get_iter_at_offset(start), buf.get_iter_at_offset(end))
        if text:
            buf.insert_with_tags(buf.get_iter_at_offset(start), text, *self._tags_for(fmt["bold"], fmt["italic"]))
        buf.end_user_action()
        self._raw = False
        self.last_edit = ("paste", "", start + len(text))
        self._emit()

    def get_runs(self, start=None, end=None):
        buf = self.get_buffer()
        s0, e0 = buf.get_bounds()
        it = (start or s0).copy()
        end = end or e0
        runs = []
        while it.compare(end) < 0:
            nxt = it.copy()
            nxt.forward_to_tag_toggle(None)
            if nxt.compare(end) > 0:
                nxt = end.copy()
            runs.append(Run(buf.get_text(it, nxt, True), it.has_tag(self.tag_bold), it.has_tag(self.tag_italic)))
            it = nxt
        return normalize_runs(runs)

    def get_plain(self):
        buf = self.get_buffer()
        return buf.get_text(*buf.get_bounds(), True)

    def _emit(self):
        self.schedule_spell()
        self.emit("content-changed")

    # -- cursor helpers --------------------------------------------------------

    def cursor_iter(self):
        buf = self.get_buffer()
        return buf.get_iter_at_mark(buf.get_insert())

    def cursor_offset(self):
        return self.cursor_iter().get_offset()

    def set_cursor(self, offset):
        buf = self.get_buffer()
        it = buf.get_end_iter() if offset is None or offset < 0 else buf.get_iter_at_offset(offset)
        buf.place_cursor(it)

    def select_range(self, start, end):
        buf = self.get_buffer()
        buf.select_range(buf.get_iter_at_offset(end), buf.get_iter_at_offset(start))

    def selection_offsets(self):
        sel = self.get_buffer().get_selection_bounds()
        return (sel[0].get_offset(), sel[1].get_offset()) if sel else None

    def has_selection(self):
        return bool(self.get_buffer().get_selection_bounds())

    def on_first_line(self):
        buf = self.get_buffer()
        return self.get_iter_location(self.cursor_iter()).y == self.get_iter_location(buf.get_start_iter()).y

    def on_last_line(self):
        buf = self.get_buffer()
        return self.get_iter_location(self.cursor_iter()).y == self.get_iter_location(buf.get_end_iter()).y

    def word_bounds(self, it):
        """(start, end) offsets of the word at/next to iter, or None."""
        text = self.get_plain()
        off = it.get_offset()
        for m in WORD_RE.finditer(text):
            if m.start() <= off <= m.end():
                return m.start(), m.end()
        return None

    def iter_at_widget_point(self, x, y):
        bx, by = self.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        ok, it = self.get_iter_at_location(bx, by)
        return it if ok else None

    def cursor_rect(self):
        loc = self.get_iter_location(self.cursor_iter())
        x, y = self.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, loc.x, loc.y)
        r = Gdk.Rectangle()
        r.x, r.y, r.width, r.height = x, y, 1, loc.height
        return r

    # -- formatting ----------------------------------------------------------------

    def _fmt_at(self, it):
        return {"bold": it.has_tag(self.tag_bold), "italic": it.has_tag(self.tag_italic)}

    def toggle(self, name):
        tag = self.tag_bold if name == "bold" else self.tag_italic
        buf = self.get_buffer()
        sel = buf.get_selection_bounds()
        if sel:
            s, e = sel
            it = s.copy()
            all_on = True
            while it.compare(e) < 0:
                if not it.has_tag(tag):
                    all_on = False
                    break
                it.forward_char()
            (buf.remove_tag if all_on else buf.apply_tag)(tag, s, e)
        else:
            cur = dict(self._pending or self._typing_format(self.cursor_iter()))
            cur[name] = not cur[name]
            self._pending = cur

    def _typing_format(self, it):
        prev = it.copy()
        if prev.backward_char():
            return self._fmt_at(prev)
        return self._fmt_at(it) if not it.is_end() else {"bold": False, "italic": False}

    def _before_insert(self, *_):
        self._inserting = True

    def _after_insert(self, buf, end_iter, text, _length):
        if self._loading or self._raw:
            self._inserting = False
            return
        start = end_iter.copy()
        start.backward_chars(len(text))
        self.last_edit = ("ins", text, start.get_offset())
        fmt = self._pending
        if fmt is None:
            prev = start.copy()
            if prev.backward_char():
                fmt = self._fmt_at(prev)
            elif not end_iter.is_end():
                fmt = self._fmt_at(end_iter)
            else:
                fmt = {"bold": False, "italic": False}
        buf.remove_tag(self.tag_bold, start, end_iter)
        buf.remove_tag(self.tag_italic, start, end_iter)
        if fmt["bold"]:
            buf.apply_tag(self.tag_bold, start, end_iter)
        if fmt["italic"]:
            buf.apply_tag(self.tag_italic, start, end_iter)
        self._inserting = False
        self._emit()

    def _on_mark_set(self, buf, _it, mark):
        if mark == buf.get_insert() and not self._loading and not self._inserting:
            self._pending = None

    def _on_changed(self, _buf):
        # insertions are reported from _after_insert, once their tags are applied
        if not self._loading and not self._inserting and not self._raw:
            self.last_edit = ("del", "", self.cursor_offset())
            self._emit()

    def _on_tag(self, _buf, tag, *_):
        if tag in (self.tag_bold, self.tag_italic) and not self._loading and not self._inserting \
                and not self._raw:
            self._emit()

    # -- spelling ------------------------------------------------------------------------

    def schedule_spell(self, delay=400):
        if self._spell_src:
            GLib.source_remove(self._spell_src)
        self._spell_src = GLib.timeout_add(delay, self._spell_now)

    def _spell_now(self):
        self._spell_src = None
        self.recheck_spelling()
        return False

    def recheck_spelling(self):
        buf = self.get_buffer()
        buf.remove_tag(self.tag_spell, *buf.get_bounds())
        sp = SPELL["speller"]
        if not SPELL["enabled"] or sp is None or not sp.dict:
            return
        for m in WORD_RE.finditer(self.get_plain()):
            w = m.group()
            if should_check(w) and not sp.check(w):
                buf.apply_tag(self.tag_spell, buf.get_iter_at_offset(m.start()), buf.get_iter_at_offset(m.end()))

    def misspelled_at(self, it):
        if not it.has_tag(self.tag_spell):
            return None
        wb = self.word_bounds(it)
        return (wb, self.get_plain()[wb[0]:wb[1]]) if wb else None

    # -- extra carets (multi-cursor) -------------------------------------------------------

    def add_caret(self, offset):
        buf = self.get_buffer()
        it = buf.get_iter_at_offset(min(offset, buf.get_char_count()))
        self.carets.append(buf.create_mark(None, it, False))
        self.queue_draw()

    def clear_carets(self):
        buf = self.get_buffer()
        for m in self.carets:
            buf.delete_mark(m)
        self.carets = []
        self.queue_draw()

    def caret_iters(self):
        buf = self.get_buffer()
        return [buf.get_iter_at_mark(m) for m in self.carets]

    def do_size_allocate(self, width, height, baseline):
        Gtk.TextView.do_size_allocate(self, width, height, baseline)
        # GtkTextView doesn't always ask for a new size when its text re-wraps, e.g. a
        # line laid out before the view had a width keeps that (very tall) height. When
        # the height it's given is off from what its text needs, re-measure, once per
        # distinct situation so a parent that legitimately differs can't cause a loop.
        # width/height here exclude the CSS border (table cells have one), but measure()
        # works on the border box and warns when asked for less than the minimum width.
        ok, box = self.compute_bounds(self)
        fw, fh = (round(box.size.width) - self.get_width(), round(box.size.height) - self.get_height()) \
            if ok else (0, 0)
        width, height = width + max(fw, 0), height + max(fh, 0)
        need = self.measure(Gtk.Orientation.VERTICAL, width)[1]
        key = (width, height, need)
        if abs(need - height) > 4 and key != self._size_fix:
            self._size_fix = key
            GLib.idle_add(self._requeue)

    def _requeue(self):
        self.queue_resize()
        return False

    def do_snapshot_layer(self, layer, snapshot):
        if layer != Gtk.TextViewLayer.ABOVE_TEXT or not self.carets:
            return
        color = self.get_color()
        for it in self.caret_iters():
            loc = self.get_iter_location(it)
            snapshot.append_color(color, Graphene.Rect().init(loc.x, loc.y, 2, loc.height))
