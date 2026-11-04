import unittest

from notterizmus.export import to_html, to_plain
from notterizmus.layout import layout
from notterizmus.model import Document, Node, Run, indent, outdent
from notterizmus.rules import Rules


def H(text, *kids):
    return Node("heading", [Run(text)], children=list(kids))


def B(text, marker="dot", *kids):
    return Node("bullet", [Run(text)], marker=marker, children=list(kids))


def sample():
    return Node("root", children=[
        H("Goal of the SDI:",
          B("ability to communicate clearly", "plus"),
          B("overengineering", "minus")),
        H("4-step framework:",
          B("The SDI is open ended."),
          H("Step 1: Understand the problem.",
            H("Review given task:",
              B("What is the product/system?"),
              B("What is it's context?")),
            H("Discuss unclear constraints."),
            H("Check preexisting systems.")),
          H("Step 2: High-level design and buy-in")),
    ])


EXPECTED = """\
Ⅰ) Goal of the SDI:
     + ability to communicate clearly
     - overengineering

Ⅱ) 4-step framework:
│    • The SDI is open ended.
├ Ⅱ.1) Step 1: Understand the problem.
│ │
│ ├ Ⅱ.1.a) Review given task:
│ │      • What is the product/system?
│ │      • What is it's context?
│ │
│ ├ Ⅱ.1.b) Discuss unclear constraints.
│ │
│ └ Ⅱ.1.c) Check preexisting systems.
│
└ Ⅱ.2) Step 2: High-level design and buy-in
"""


class LayoutTest(unittest.TestCase):
    def test_sample(self):
        self.assertEqual(to_plain(layout(sample(), Rules())), EXPECTED)

    def test_roman(self):
        r = Rules()
        self.assertEqual(r.label([1]), "Ⅰ)")
        self.assertEqual(r.label([12]), "Ⅻ)")
        self.assertEqual(r.label([13]), "ⅩⅢ)")
        self.assertEqual(r.label([2, 3, 27, 4]), "Ⅱ.3.aa.ⅳ)")

    def test_html_keeps_whitespace_and_format(self):
        root = Node("root", children=[Node("heading", [Run("a "), Run("b", bold=True), Run("c", italic=True)],
                                           children=[B("x")])])
        h = to_html(layout(root, Rules()))
        self.assertIn('<strong><span style="white-space: pre-wrap;">b</span></strong>', h)
        self.assertIn('<em><span style="white-space: pre-wrap;">c</span></em>', h)
        self.assertIn('<span style="white-space: pre-wrap;">     </span>', h)

    def test_table(self):
        t = Node("table", data={"header": True, "rows": [[[Run("a")], [Run("bb")]], [[Run("1")], []]]})
        root = Node("root", children=[H("T", t)])
        self.assertIn("<th><p>", to_html(layout(root, Rules())))
        self.assertIn("│ a │ bb │", to_plain(layout(root, Rules())))

    def test_roundtrip_and_ops(self):
        doc = Document(sample(), "Book", 3, "Chap")
        d2 = Document.from_json(doc.to_json())
        self.assertEqual(to_plain(layout(d2.root, Rules())), EXPECTED)
        top2 = d2.root.children[1]
        step2 = top2.children[2]
        self.assertTrue(indent(step2))  # becomes Ⅱ.1.d
        self.assertIn("Ⅱ.1.d) Step 2", to_plain(layout(d2.root, Rules())))
        self.assertTrue(outdent(step2))
        self.assertEqual(to_plain(layout(d2.root, Rules())), EXPECTED)


if __name__ == "__main__":
    unittest.main()
