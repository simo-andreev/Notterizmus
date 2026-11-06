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
