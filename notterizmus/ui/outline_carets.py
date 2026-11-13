"""OutlineEditor, part: multiple cursors: tap Ctrl twice, keep it held, then press Up or Down."""
from __future__ import annotations

from gi.repository import Gdk

from .rows import TextRow


class CaretsMixin:
    """Mixed into OutlineEditor (outline.py); uses its state."""

    # -- multi-cursor (double-tap Ctrl, keep it held, then ↑/↓) ----------------------------

    def _text_views(self):
        return [self.rows[n.id].view for n in self._order()
                if isinstance(self.rows.get(n.id), TextRow)]

    def add_caret(self, view, delta):
        order = self._text_views()
        active = [v for v in [view] + self.mc_views if v in order]
        if not active:
            return
        idxs = [order.index(v) for v in active]
        t = (max(idxs) + 1) if delta > 0 else (min(idxs) - 1)
        if 0 <= t < len(order):
            target = order[t]
            target.add_caret(view.cursor_offset())
            if target not in self.mc_views:
                self.mc_views.append(target)

    def clear_carets(self):
        for v in self.mc_views:
            v.clear_carets()
        self.mc_views = []

    def _all_marks(self, view):
        marks = [(view, view.get_buffer().get_insert())]
        for v in self.mc_views:
            marks += [(v, m) for m in v.carets]
        return marks

    def _multi_key(self, view, keyval, name, ctrl, alt):
        if name == "Escape":
            self.clear_carets()
            return True
        uni = Gdk.keyval_to_unicode(keyval)
        ch = chr(uni) if uni else ""
        marks = self._all_marks(view)
        if not ctrl and not alt and ch and ch.isprintable():
            with self._op(group=("multi",)):
                for v, m in marks:
                    v.get_buffer().insert(v.get_buffer().get_iter_at_mark(m), ch)
            self._redraw_carets()
            return True
        if name in ("BackSpace", "Delete") and not ctrl:
            with self._op(group=("multi",)):
                for v, m in marks:
                    buf = v.get_buffer()
                    it = buf.get_iter_at_mark(m)
                    other = it.copy()
                    moved = other.backward_char() if name == "BackSpace" else other.forward_char()
                    if moved:
                        buf.delete(it, other)
            self._redraw_carets()
            return True
        if name in ("Left", "Right", "Home", "End") and not ctrl:
            for v, m in marks:
                buf = v.get_buffer()
                it = buf.get_iter_at_mark(m)
                if name == "Left":
                    it.backward_char()
                elif name == "Right":
                    it.forward_char()
                elif name == "Home":
                    it.set_line_offset(0)
                else:
                    it.forward_to_line_end()
                if m == buf.get_insert():
                    buf.place_cursor(it)
                else:
                    buf.move_mark(m, it)
            self._redraw_carets()
            return True
        self.clear_carets()
        return None

    def _redraw_carets(self):
        for v in self.mc_views:
            v.queue_draw()
