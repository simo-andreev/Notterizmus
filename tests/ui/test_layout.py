"""Regressions in what the outline draws: rows that jump, a hidden cursor, a tall first item."""
import unittest

from notterizmus.guide import b, h

from . import support as ui

LONG = ("A long first item that wraps over several lines in a normal window, which is the "
        "situation where the first row used to be laid out as if it were very narrow. ") * 3


class LayoutTest(ui.UITestCase):
    def assert_no_jumps(self, frames):
        self.assertGreaterEqual(len(frames), 8, "not enough frames were drawn")
        final = frames[-1]
        for i, frame in enumerate(frames):
            moved = {w: (y, final[w]) for w, y in frame.items() if w in final and y != final[w]}
            self.assertFalse(moved, f"frame {i} drew rows away from where they end up: {list(moved.values())[:3]}")

    # With wrapping text, since a text view measures its height before it knows its
    # width. Disabling OutlineEditor.size_new_views makes the Enter test fail.
    def test_enter_does_not_make_rows_jump(self):
        doc = ui.open_chapter([h("Intro", h("One", b("x"), b(LONG)), h("Two", b(LONG)))])
        bullet = doc.root.children[0].children[0].children[0]
        r = ui.focus(bullet)
        self.assert_no_jumps(ui.record_frames(lambda: ui.press(r.view, "Return", wait=0)))

    # A wider or narrower prefix re-wraps the text, but GtkTextView reports the height for
    # the width it was last laid out at: one frame at the old height, then the rows below
    # jump. Shows at 60 Hz on Broadway. Making RichText.expect_width_change do nothing
    # makes these fail.
    def test_indent_does_not_make_rows_jump(self):
        doc = ui.open_chapter([h("Intro", b("x"), b(LONG), h("One", b(LONG)))])
        r = ui.focus(doc.root.children[0].children[1])
        self.assert_no_jumps(ui.record_frames(lambda: ui.press(r.view, "Tab", wait=0)))

    def test_outdent_does_not_make_rows_jump(self):
        doc = ui.open_chapter([h("Intro", b("x", b(LONG)), h("One", b(LONG)))])
        r = ui.focus(doc.root.children[0].children[0].children[0])
        self.assert_no_jumps(ui.record_frames(lambda: ui.press(r.view, "ISO_Left_Tab", wait=0)))

    def test_outdent_to_a_heading_does_not_make_rows_jump(self):
        # the bullet becomes a top-level heading: new prefix and bolder text
        doc = ui.open_chapter([h("Intro", b(LONG)), h("Two", b(LONG))])
        r = ui.focus(doc.root.children[0].children[0])
        self.assert_no_jumps(ui.record_frames(lambda: ui.press(r.view, "ISO_Left_Tab", wait=0)))

    def test_cursor_stays_visible_when_enter_is_pressed_at_the_bottom(self):
        items = [b(f"note {i}") for i in range(60)]
        doc = ui.open_chapter([h("Long list", *items)])
        last = doc.root.children[0].children[-1]
        r = ui.focus(last)
        ui.pump_until(lambda: ui.cursor_in_view(r.view))
        for _ in range(5):
            ui.type_text(self.ed.cur_view or r.view, " more", wait=0.02)
            ui.press(self.ed.cur_view or r.view, "Return", wait=0.4)
            view = self.ed.cur_view
            self.assertTrue(ui.pump_until(lambda: ui.cursor_in_view(view)),
                            "the cursor is below the visible area after Enter")

    def test_first_item_has_its_real_height_when_a_chapter_opens(self):
        ui.open_chapter([h(LONG, b("short")), h("Second")])
        for v in self.ed.all_views():
            ok, box = v.compute_bounds(v)
            need = v.measure(ui.Gtk.Orientation.VERTICAL, round(box.size.width))[1]
            self.assertLessEqual(abs(round(box.size.height) - need), 2,
                                 f"a row is {round(box.size.height)} px tall but its text needs {need}")

    def test_text_is_drawn_hinted(self):
        # GTK's "automatic" rendering drew the top bar of "=" between two pixel rows, so
        # faint that "1 + 1 = 2" read as "1 + 1 - 2". The app switches to "manual".
        settings = ui.Gtk.Settings.get_default()
        self.assertEqual(settings.get_property("gtk-font-rendering"), ui.Gtk.FontRendering.MANUAL)
        self.assertTrue(settings.get_property("gtk-hint-font-metrics"))
