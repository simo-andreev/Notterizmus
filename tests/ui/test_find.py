"""Find (Ctrl+F) and replace (Ctrl+H, Ctrl+R) in the chapter, items and table cells (R3)."""
from notterizmus.guide import b, h, key, table

from . import support as ui


def tagged(view, tag):
    buf = view.get_buffer()
    out, it = [], buf.get_start_iter()
    while it.forward_to_tag_toggle(tag):
        if it.starts_tag(tag):
            end = it.copy()
            end.forward_to_tag_toggle(tag)
            out.append((it.get_offset(), end.get_offset()))
    if buf.get_start_iter().starts_tag(tag):
        end = buf.get_start_iter()
        end.forward_to_tag_toggle(tag)
        out.insert(0, (0, end.get_offset()))
    return out


class FindTest(ui.UITestCase):
    def setUp(self):
        super().setUp()
        self.doc = ui.open_chapter([h("Scaling", b("scale the scale"), b((key("Scale"), " in bold")),
                                      table([["scale", "x"], ["y", "rescaled"]]))])
        self.bar = self.win.findbar
        self.intro = self.doc.root.children[0]

    def tearDown(self):
        self.bar.set_search_mode(False)

    def find(self, text, replace=False):
        self.win.lookup_action("replace" if replace else "find").activate(None)
        self.bar.entry.set_text(text)
        ui.wait_for(lambda: self.bar._found_for == text, "the find bar to search for the text")

    def test_keys(self):
        accels = {a: self.app.get_accels_for_action(f"win.{a}") for a in ("find", "replace", "find-next", "find-prev")}
        parsed = {a: [ui.Gtk.accelerator_parse(x) for x in v] for a, v in accels.items()}
        self.assertEqual(parsed, {a: [ui.Gtk.accelerator_parse(x) for x in xs] for a, xs in (
            ("find", ["<Control>f"]), ("replace", ["<Control>h", "<Control>r"]), ("find-next", ["<Control>g"]),
            ("find-prev", ["<Control><Shift>g"]))})

    def test_finds_in_items_and_table_cells_and_counts(self):
        self.find("scale")
        self.assertTrue(self.bar.get_search_mode())
        self.assertEqual(len(self.bar.matches), 5)  # 2 + 1 in bullets, 2 in cells ("Scaling" has no e)
        self.assertEqual(self.bar.count.get_text(), f"{self.bar.current + 1} of 5")
        first = ui.row(self.intro.children[0]).view
        self.assertEqual(tagged(first, first.tag_found), [(0, 5), (10, 15)])

    def test_next_and_previous_wrap_and_select_the_match(self):
        r = ui.focus(self.intro, 0)
        self.find("scale")
        self.assertEqual(self.bar.current, 0)
        ui.press(self.bar.entry, "Return", shift=True)  # previous from the first wraps to the last
        self.assertEqual(self.bar.current, 4)
        self.win.lookup_action("find-next").activate(None)
        self.assertEqual(self.bar.current, 0)
        self.bar.entry.emit("activate")  # Enter: next
        view, s, e = self.bar.matches[1]
        self.assertEqual(tagged(view, view.tag_found_current), [(s, e)])
        self.assertEqual(view.selection_offsets(), (s, e))
        self.assertIsNotNone(r)

    def test_match_case_and_whole_words(self):
        self.find("scale")
        self.bar.case.set_active(True)
        self.assertEqual(len(self.bar.matches), 4)  # not "Scaling" or "Scale"
        self.bar.whole.set_active(True)
        self.assertEqual(len(self.bar.matches), 3)  # not "rescaled"
        self.bar.case.set_active(False)
        self.bar.whole.set_active(False)

    def test_no_results(self):
        self.find("zebra")
        self.assertEqual(self.bar.count.get_text(), "No results")
        self.assertTrue(self.bar.entry.has_css_class("error"))

    def test_starts_from_the_selected_text(self):
        r = ui.focus(self.intro.children[0], 0)
        r.view.select_range(10, 15)
        self.win.lookup_action("find").activate(None)
        ui.wait_for(lambda: self.bar.entry.get_text() == "scale" and self.bar.matches, "the selection searched for")
        self.assertEqual(self.bar.matches[self.bar.current][1:], (10, 15))

    def test_replace_keeps_bold_and_is_one_undo_step(self):
        self.find("scale", replace=True)
        bold = self.intro.children[1]
        idx = next(i for i, (v, _s, _e) in enumerate(self.bar.matches) if v is ui.row(bold).view)
        self.bar.current = idx
        self.bar.replace_entry.set_text("size")
        self.bar.replace_current()
        self.assertEqual([(r.text, r.bold) for r in bold.runs], [("size", True), (" in bold", False)])
        self.assertEqual(len(self.bar.matches), 4)
        ui.press(ui.row(bold).view, "z", ctrl=True)
        self.assertEqual([(r.text, r.bold) for r in self.win.doc.root.children[0].children[1].runs],
                         [("Scale", True), (" in bold", False)])

    def test_replace_all_including_table_cells_is_one_undo_step(self):
        toasts = []
        self.bar.toast = lambda msg, *a: toasts.append(msg)
        try:
            self.find("scale", replace=True)
            self.bar.replace_entry.set_text("size")
            self.bar.replace_all()
        finally:
            self.bar.toast = self.win.toast
        self.assertEqual(toasts, ["Replaced 5 matches"])
        intro = self.win.doc.root.children[0]
        self.assertEqual(intro.text, "Scaling")
        self.assertEqual(intro.children[0].text, "size the size")
        rows = intro.children[2].data["rows"]
        self.assertEqual(["".join(r.text for r in cell) for row in rows for cell in row], ["size", "x", "y", "resized"])
        self.assertEqual(self.bar.count.get_text(), "No results")
        ui.press(ui.row(intro.children[0]).view, "z", ctrl=True)
        intro = self.win.doc.root.children[0]
        self.assertEqual((intro.text, intro.children[0].text), ("Scaling", "scale the scale"))

    def test_typing_in_the_chapter_updates_the_matches(self):
        self.find("scale")
        ui.type_text(ui.row(self.intro.children[1]).view, " scale")
        ui.wait_for(lambda: len(self.bar.matches) == 6, "the matches to follow the typing")

    def test_escape_closes_it_and_leaves_the_match_selected(self):
        self.find("bold")
        view, s, e = self.bar.matches[self.bar.current]
        self.bar.entry.emit("stop-search")
        self.assertFalse(self.bar.get_search_mode())
        self.assertEqual(tagged(view, view.tag_found), [])
        self.assertEqual(view.selection_offsets(), (s, e))
