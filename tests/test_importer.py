import unittest

from notterizmus.export import to_html, to_plain
from notterizmus.importer import html_items, parse, text_items
from notterizmus.layout import layout
from notterizmus.model import Node
from notterizmus.rules import Rules
from tests.test_layout import EXPECTED, sample


def render(forest):
    return to_plain(layout(Node("root", children=forest), Rules()))


class ImporterTest(unittest.TestCase):
    def test_plain_roundtrip(self):
        forest = parse(text_items(EXPECTED), Rules())
        self.assertEqual(render(forest), EXPECTED)

    def test_html_roundtrip_keeps_format(self):
        root = sample()
        root.children[0].children[0].runs[0].bold = True
        html = to_html(layout(root, Rules()))
        forest = parse(html_items(html), Rules())
        self.assertEqual(render(forest), EXPECTED)
        self.assertTrue(forest[0].children[0].runs[0].bold)

    def test_hand_written_ascii(self):
        text = "II) Framework\n├ II.1) Step one\n│ │      • note\n│      - con\n└ II.2) Step two\n"
        out = render(parse(text_items(text), Rules()))
        self.assertIn("Ⅰ.1) Step one", out)
        self.assertIn("- con", out)
        self.assertIn("└ Ⅰ.2) Step two", out)

    def test_bullets_nest_by_indent(self):
        forest = parse(text_items("- a\n    - b\n- c"), Rules())
        self.assertEqual([n.text for n in forest], ["a", "c"])
        self.assertEqual(forest[0].children[0].text, "b")

    def test_unstructured(self):
        self.assertIsNone(parse(text_items("just a sentence\nand another"), Rules()))

    def test_html_table(self):
        items = html_items("<p>Ⅰ) T</p><table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td><b>2</b></td></tr></table>")
        forest = parse(items, Rules())
        t = forest[0].children[0]
        self.assertEqual(t.kind, "table")
        self.assertTrue(t.data["header"])
        self.assertTrue(t.data["rows"][1][1][0].bold)


if __name__ == "__main__":
    unittest.main()
