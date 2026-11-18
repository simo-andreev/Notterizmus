"""Copy for TopCoding and pasting outlines, through the app's own clipboard."""
from notterizmus.guide import b, h, key

from . import support as ui


class ClipboardTest(ui.UITestCase):
    def test_copy_for_topcoding_puts_html_and_plain_text_on_the_clipboard(self):
        ui.open_chapter([h("Intro", b((key("bold"), " and plain")), h("Detail"))])
        self.win.lookup_action("copy").activate(None)
        ui.pump(0.2)
        html = ui.clipboard("text/html")
        self.assertIn("<strong>", html)
        self.assertIn("Ⅰ) ", html)
        self.assertIn("Ⅰ.1) ", html)
        plain = ui.clipboard("text/plain")
        self.assertTrue(plain.startswith("Ⅰ) Intro\n"), plain[:40])

    def test_pasting_hand_written_notes_builds_the_outline(self):
        doc = ui.open_chapter([h("")])
        first = doc.root.children[0]
        r = ui.focus(first, 0)
        self.win.get_clipboard().set("I) Pasted\n  • a note\n  I.1) Sub\nII) Second")
        ui.pump(0.1)
        r.view.emit("paste-clipboard")
        ui.pump_until(lambda: len(self.win.doc.root.children) == 2, 3)
        tops = self.win.doc.root.children
        self.assertEqual([n.text for n in tops], ["Pasted", "Second"])
        self.assertEqual([(c.kind, c.text) for c in tops[0].children], [("bullet", "a note"), ("heading", "Sub")])


class PasteTest(ui.UITestCase):
    """What Ctrl+V does with each kind of clipboard content."""

    def setUp(self):
        super().setUp()
        self.toasts = []
        self.win.toast = lambda msg, button=None, cb=None: self.toasts.append((msg, button, cb))
        self.addCleanup(lambda: self.win.__dict__.pop("toast", None))

    def put(self, **formats):
        """Put content on the clipboard by MIME type, e.g. html="<p>..</p>", plain=".."."""
        mimes = {"html": "text/html", "plain": "text/plain;charset=utf-8"}
        self.win.get_clipboard().set_content(ui.Gdk.ContentProvider.new_union([
            ui.Gdk.ContentProvider.new_for_bytes(mimes[kind], ui.GLib.Bytes.new(text.encode("utf-8")))
            for kind, text in formats.items()]))
        ui.pump(0.05)

    def paste(self, row, until, what="the paste"):
        row.view.emit("paste-clipboard")
        ui.wait_for(until, what)
        ui.wait_editor()

    def test_copied_text_keeps_its_formatting_when_pasted(self):
        doc = ui.open_chapter([h("Intro", b(("plain ", key("bold"), " end")), b(""))])
        first, second = doc.root.children[0].children
        r = ui.focus(first, 0)
        r.view.select_range(3, 10)
        r.view.emit("copy-clipboard")
        ui.pump(0.1)
        self.assertEqual(ui.clipboard("text/plain"), "in bold")
        self.assertIn("<strong>", ui.clipboard("text/html"))
        self.assertEqual(first.text, "plain bold end", "copying changes nothing")
        target = ui.focus(second, 0)
        self.paste(target, lambda: second.text)
        self.assertEqual([(run.text, run.bold) for run in second.runs], [("in ", False), ("bold", True)])

    def test_cut_text_is_removed_and_one_undo_brings_it_back(self):
        doc = ui.open_chapter([h("Intro", b("one two three"))])
        item = doc.root.children[0].children[0]
        r = ui.focus(item, 0)
        r.view.select_range(4, 8)
        r.view.emit("cut-clipboard")
        ui.pump(0.1)
        self.assertEqual(item.text, "one three")
        self.assertEqual(ui.clipboard("text/plain"), "two ")
        ui.press(r.view, "z", ctrl=True)
        self.assertEqual(self.win.doc.root.children[0].children[0].text, "one two three")

    def test_copy_without_a_selection_is_left_to_the_text_view(self):
        doc = ui.open_chapter([h("Intro", b("text"))])
        self.assertFalse(self.ed.copy_text(ui.focus(doc.root.children[0].children[0]).view))

    def test_pasting_replaces_the_selected_text(self):
        doc = ui.open_chapter([h("Intro", b("one two three"))])
        item = doc.root.children[0].children[0]
        self.put(plain="2")
        r = ui.focus(item, 0)
        r.view.select_range(4, 7)
        self.paste(r, lambda: "2" in item.text)
        self.assertEqual(item.text, "one 2 three")
        self.assertEqual(self.toasts, [], "a one-line paste needs no notice")

    def test_html_keeps_bold_and_italic(self):
        doc = ui.open_chapter([h("Intro", b("start: "))])
        item = doc.root.children[0].children[0]
        self.put(html="<p>plain <b>bold</b> <i>it</i></p>", plain="plain bold it")
        self.paste(ui.focus(item), lambda: "bold" in item.text)
        self.assertEqual([(run.text, run.bold, run.italic) for run in item.runs],
                         [("start: plain ", False, False), ("bold", True, False), (" ", False, False),
                          ("it", False, True)])

    def test_ctrl_shift_v_pastes_plain_text_into_the_item_whatever_it_looks_like(self):
        doc = ui.open_chapter([h("Intro", b(""))])
        intro = doc.root.children[0]
        self.put(html="<p>I) <b>Pasted</b></p><p>• a note</p>", plain="I) Pasted\n  • a note")
        r = ui.focus(intro.children[0], 0)
        self.assertTrue(ui.press(r.view, "V", ctrl=True, shift=True))
        ui.wait_for(lambda: intro.children[0].text, "the plain paste")
        self.assertEqual([(run.text, run.bold) for run in intro.children[0].runs], [("I) Pasted • a note", False)])
        self.assertEqual(len(intro.children), 1)

    def test_paragraphs_without_markers_join_the_item_and_can_be_split_afterwards(self):
        doc = ui.open_chapter([h("Intro", b("Notes: "))])
        intro = doc.root.children[0]
        item = intro.children[0]
        self.put(plain="The quick brown fox jum-\nps over the dog.\n\nSecond paragraph\nhere.\n")
        self.paste(ui.focus(item), lambda: "fox" in item.text)
        self.assertEqual(item.text, "Notes: The quick brown fox jumps over the dog. Second paragraph here.")
        self.assertEqual(len(intro.children), 1)
        msg, button, split = self.toasts[-1]
        self.assertEqual((msg, button), ("Pasted 2 paragraphs into one item", "One Item per Paragraph"))
        split()
        ui.wait_editor()
        intro = self.win.doc.root.children[0]
        self.assertEqual([n.text for n in intro.children],
                         ["Notes: The quick brown fox jumps over the dog.", "Second paragraph here."])
        ui.press(self.ed.cur_view, "z", ctrl=True)
        self.assertEqual([n.text for n in self.win.doc.root.children[0].children], ["Notes: "],
                         "splitting replaced the paste: one undo takes all of it back")

    def test_one_paragraph_over_several_lines_gets_no_offer_to_split(self):
        doc = ui.open_chapter([h("Intro", b(""))])
        item = doc.root.children[0].children[0]
        self.put(plain="one line\nand another")
        self.paste(ui.focus(item, 0), lambda: item.text)
        self.assertEqual(item.text, "one line and another")
        self.assertEqual(self.toasts, [])

    def test_an_outline_paste_can_be_taken_back_as_plain_text(self):
        doc = ui.open_chapter([h("")])
        self.put(plain="I) Pasted\n  • a note\nII) Second")
        self.paste(ui.focus(doc.root.children[0], 0), lambda: len(self.win.doc.root.children) == 2)
        msg, button, as_plain = self.toasts[-1]
        self.assertEqual((msg, button), ("Pasted 3 items as an outline", "Paste as Plain Text"))
        as_plain()
        ui.wait_for(lambda: len(self.win.doc.root.children) == 1 and self.win.doc.root.children[0].text, "the plain paste")
        self.assertEqual(self.win.doc.root.children[0].text, "I) Pasted • a note II) Second")

    def texts(self):
        return [n.text for n in self.win.doc.root.walk()]

    def test_the_toasts_button_leaves_an_outline_paste_alone_once_something_changed(self):
        """The buttons undid the last step, whatever it was: after a word typed within the
        toast's 6 seconds, Paste as Plain Text undid the word, kept the pasted items and
        pasted the same text again (CR3)."""
        doc = ui.open_chapter([h("")])
        self.put(plain="I) Pasted\n  • a note\nII) Second")
        self.paste(ui.focus(doc.root.children[0], 0), lambda: len(self.win.doc.root.children) == 2)
        as_plain = self.toasts[-1][2]
        pasted = self.texts()
        ui.type_text(self.ed.cur_view, " typed")
        typed = self.texts()
        as_plain()
        ui.wait_editor()
        self.assertEqual(self.texts(), typed, "the paste and the word are both kept")
        self.assertEqual(self.toasts[-1], ("The paste was changed since: use Ctrl+Z", None, None))
        self.ed.undo()  # the word: the paste is the last change again
        ui.wait_editor()
        self.assertEqual(self.texts(), pasted)
        as_plain()
        ui.wait_for(lambda: len(self.win.doc.root.children) == 1, "the plain paste")
        self.assertEqual(self.win.doc.root.children[0].text, "I) Pasted • a note II) Second")

    def test_one_item_per_paragraph_leaves_a_paste_alone_once_something_changed(self):
        doc = ui.open_chapter([h("Intro", b("Notes: "))])
        item = doc.root.children[0].children[0]
        self.put(plain="First paragraph.\n\nSecond paragraph.\n")
        self.paste(ui.focus(item), lambda: "First" in item.text)
        split = self.toasts[-1][2]
        ui.type_text(self.ed.cur_view, " typed")
        typed = self.texts()
        split()
        ui.wait_editor()
        self.assertEqual(self.texts(), typed)
        self.assertEqual(self.toasts[-1], ("The paste was changed since: use Ctrl+Z", None, None))

    def test_the_toast_goes_once_the_chapter_changes_again(self):
        del self.win.toast  # the window's own toasts, kept to watch them
        made = []
        real = self.win.toast
        self.win.toast = lambda *args: made.append(real(*args)) or made[-1]
        doc = ui.open_chapter([h("")])
        self.put(plain="I) Pasted\n  • a note\nII) Second")
        self.paste(ui.focus(doc.root.children[0], 0), lambda: len(self.win.doc.root.children) == 2)
        toast = made[-1]
        self.assertEqual(toast.get_button_label(), "Paste as Plain Text")
        gone = []
        toast.connect("dismissed", lambda *_: gone.append(True))
        ui.settle()
        self.assertEqual(gone, [], "the paste itself doesn't dismiss it")
        ui.type_text(self.ed.cur_view, " typed")
        ui.wait_for(lambda: gone, "the toast to go")

    def test_an_outline_pasted_into_an_item_with_text_goes_after_it(self):
        doc = ui.open_chapter([h("Intro", b("mine"), h("Sub")), h("Last")])
        intro = doc.root.children[0]
        self.put(plain="- pasted bullet\nI) Pasted heading\n  - under it")
        self.paste(ui.focus(intro.children[0]), lambda: len(self.win.doc.root.children) == 3)
        self.assertEqual([(n.kind, n.text) for n in intro.children],
                         [("bullet", "mine"), ("bullet", "pasted bullet"), ("heading", "Sub")])
        self.assertEqual([n.text for n in self.win.doc.root.children], ["Intro", "Pasted heading", "Last"],
                         "a numbered item can't go under a bullet: it follows the enclosing one")
        self.assertEqual([n.text for n in self.win.doc.root.children[1].children], ["under it"])
        self.assertIs(self.ed.current, self.win.doc.root.children[1].children[0], "the cursor ends on the last pasted item")

    def test_a_pasted_table_arrives_with_its_cells(self):
        doc = ui.open_chapter([h("Intro", b(""))])
        intro = doc.root.children[0]
        self.put(html="<p>• before</p><table><tr><th>k</th><th>v</th></tr><tr><td>1</td><td><b>2</b></td></tr></table>")
        self.paste(ui.focus(intro.children[0], 0), lambda: len(intro.children) == 2)
        self.assertEqual([n.kind for n in intro.children], ["bullet", "table"])
        data = intro.children[1].data
        self.assertTrue(data["header"])
        self.assertEqual([["".join(run.text for run in c) for c in row] for row in data["rows"]], [["k", "v"], ["1", "2"]])
        self.assertTrue(data["rows"][1][1][0].bold)
        self.assertEqual(len(ui.row(intro.children[1]).cells), 4, "and is drawn")

    TABLE = "<table><tr><th>k</th><th>v</th></tr><tr><td>1</td><td><b>2</b></td></tr></table>"

    def cells(self, node):
        return [["".join(run.text for run in c) for c in row] for row in node.data["rows"]]

    def test_a_table_copied_on_its_own_goes_after_the_item(self):
        # It used to vanish: nothing in it says "outline", and its text has no lines.
        doc = ui.open_chapter([h("Intro", b("first"), b("second"))])
        intro = doc.root.children[0]
        first = intro.children[0]
        self.put(html=self.TABLE)
        r = ui.focus(first, 2)
        self.paste(r, lambda: len(intro.children) == 3)
        self.assertEqual([(n.kind, n.text) for n in intro.children], [("bullet", "first"), ("table", ""), ("bullet", "second")])
        table = intro.children[1]
        self.assertEqual((self.cells(table), table.data["header"]), ([["k", "v"], ["1", "2"]], True))
        self.assertTrue(table.data["rows"][1][1][0].bold)
        ui.wait_for(lambda: self.ed.cur_view is ui.row(table).cells.get((0, 0)), "the cursor to be in the table")
        self.assertEqual(self.toasts, [])
        ui.press(self.ed.cur_view, "z", ctrl=True)
        self.assertEqual([n.kind for n in self.win.doc.root.children[0].children], ["bullet", "bullet"], "one undo step")

    def test_a_table_pasted_into_a_numbered_item_goes_with_its_notes(self):
        doc = ui.open_chapter([h("Intro", b("note"), h("Sub"))])
        intro = doc.root.children[0]
        self.put(html=self.TABLE)
        self.paste(ui.focus(intro), lambda: len(intro.children) == 3)
        self.assertEqual([n.kind for n in intro.children], ["bullet", "table", "heading"], "where Ctrl+T puts one")
        self.assertEqual(intro.text, "Intro")

    def test_a_table_pasted_into_an_empty_item_leaves_the_item(self):
        doc = ui.open_chapter([h("")])
        self.put(html=self.TABLE)
        self.paste(ui.focus(doc.root.children[0], 0), lambda: doc.root.children[0].children)
        root = self.win.doc.root
        self.assertEqual([(n.kind, [c.kind for c in n.children]) for n in root.children], [("heading", ["table"])],
                         "the table sits under the numbered item, not alone at the top level")

    def test_text_without_markers_and_a_table_both_arrive(self):
        doc = ui.open_chapter([h("Intro", b("Notes: "), b("after"))])
        intro = doc.root.children[0]
        item = intro.children[0]
        self.put(html="<p>Some <b>bold</b> text.</p>" + self.TABLE + "<table><tr><td>second</td></tr></table>")
        self.paste(ui.focus(item), lambda: len(intro.children) == 4)
        self.assertEqual([(run.text, run.bold) for run in item.runs],
                         [("Notes: Some ", False), ("bold", True), (" text.", False)], "the text joins the item")
        self.assertEqual([n.kind for n in intro.children], ["bullet", "table", "table", "bullet"])
        self.assertEqual([self.cells(n) for n in intro.children[1:3]], [[["k", "v"], ["1", "2"]], [["second"]]], "in order")
        ui.press(ui.row(item).view, "z", ctrl=True)
        intro = self.win.doc.root.children[0]
        self.assertEqual([(n.kind, n.text) for n in intro.children], [("bullet", "Notes: "), ("bullet", "after")])

    def test_splitting_pasted_paragraphs_keeps_the_table_that_came_with_them(self):
        doc = ui.open_chapter([h("Intro", b(""))])
        intro = doc.root.children[0]
        self.put(html="<p>First paragraph.</p><p></p><p>Second paragraph.</p>" + self.TABLE,
                 plain="First paragraph.\n\nSecond paragraph.")
        self.paste(ui.focus(intro.children[0], 0), lambda: len(intro.children) == 2)
        self.assertEqual(intro.children[0].text, "First paragraph. Second paragraph.")
        msg, button, split = self.toasts[-1]
        self.assertEqual((msg, button), ("Pasted 2 paragraphs into one item", "One Item per Paragraph"))
        split()
        ui.wait_for(lambda: len(self.win.doc.root.children[0].children) == 3, "one item per paragraph")
        intro = self.win.doc.root.children[0]
        self.assertEqual([(n.kind, n.text) for n in intro.children],
                         [("bullet", "First paragraph."), ("bullet", "Second paragraph."), ("table", "")])
        self.assertEqual(self.cells(intro.children[2]), [["k", "v"], ["1", "2"]])
