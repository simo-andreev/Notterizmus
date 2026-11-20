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


def plain(root, **changes):
    rules = Rules()
    for name, value in changes.items():
        section, key = name.split("__")
        rules.data[section][key] = value
    return to_plain(layout(root, rules))


class ShapeTest(unittest.TestCase):
    """Smaller outlines, one rule at a time."""

    def tree(self):
        return Node("root", children=[H("A", B("b"), H("A1"), H("A2", B("c"))), H("B")])

    def test_bullets_nest_four_columns_deeper_each_level(self):
        root = Node("root", children=[H("A", B("b1", "dot", B("b2", "plus", B("b3", "minus"))), H("A1"))])
        self.assertEqual(plain(root), "Ⅰ) A\n"
                                      "│    • b1\n"
                                      "│        + b2\n"
                                      "│            - b3\n"
                                      "└ Ⅰ.1) A1\n")

    def test_bullets_after_the_last_numbered_child_have_no_trunk(self):
        """The trunk has ended, so the line that sets them apart from A1 is empty."""
        root = Node("root", children=[H("A", B("before"), H("A1"), B("after"))])
        self.assertEqual(plain(root), "Ⅰ) A\n"
                                      "│    • before\n"
                                      "└ Ⅰ.1) A1\n"
                                      "\n"
                                      "     • after\n")

    def test_bullets_after_a_numbered_child_are_set_apart_before_and_after(self):
        """A's bullets after A1 would read as A1's, their indent aside: spacers on both
        sides space them like a sibling of A1 and A2. Bullets in a row, and their own
        bullets, stay together; A1's bullets get none."""
        root = Node("root", children=[H("A", B("intro"), H("A1", B("a1")),
                                        B("x"), B("y", "dot", B("sub")), H("A2"))])
        self.assertEqual(plain(root), "Ⅰ) A\n"
                                      "│    • intro\n"
                                      "├ Ⅰ.1) A1\n"
                                      "│      • a1\n"
                                      "│\n"
                                      "│    • x\n"
                                      "│    • y\n"
                                      "│        • sub\n"
                                      "│\n"
                                      "└ Ⅰ.2) A2\n")

    def test_bullets_after_a_numbered_child_are_set_apart_in_deeper_levels(self):
        root = Node("root", children=[H("A", H("A1", H("a"), B("x"), H("b")))])
        self.assertEqual(plain(root), "Ⅰ) A\n"
                                      "│\n"
                                      "└ Ⅰ.1) A1\n"
                                      "  │\n"
                                      "  ├ Ⅰ.1.a) a\n"
                                      "  │\n"
                                      "  │    • x\n"
                                      "  │\n"
                                      "  └ Ⅰ.1.b) b\n")

    def test_a_table_after_a_numbered_child_is_set_apart_too(self):
        table = Node("table", data={"rows": [[[Run("c")]]]})
        lines = layout(Node("root", children=[H("A", H("A1"), table, H("A2"))]), Rules())
        self.assertEqual([ln.kind for ln in lines],
                         ["item", "spacer", "item", "spacer", "table", "spacer", "item"])

    def test_setting_apart_bullets_after_a_numbered_child_can_be_turned_off(self):
        root = Node("root", children=[H("A", H("A1"), B("x"), H("A2"), B("y"))])
        self.assertEqual(plain(root, tree__spacer_around_parent_leaves=False),
                         "Ⅰ) A\n"
                         "│\n"
                         "├ Ⅰ.1) A1\n"
                         "│    • x\n"
                         "└ Ⅰ.2) A2\n"
                         "     • y\n")
        self.assertEqual(plain(root, tree__spacer_lines=False),
                         "Ⅰ) A\n"
                         "├ Ⅰ.1) A1\n"
                         "│    • x\n"
                         "└ Ⅰ.2) A2\n"
                         "     • y\n")

    def test_a_spacer_comes_before_a_numbered_child_unless_a_bullet_precedes_it(self):
        self.assertEqual(plain(self.tree()), "Ⅰ) A\n"
                                             "│    • b\n"
                                             "├ Ⅰ.1) A1\n"
                                             "│\n"
                                             "└ Ⅰ.2) A2\n"
                                             "       • c\n"
                                             "\n"
                                             "Ⅱ) B\n")

    def test_spacer_lines_can_be_turned_off(self):
        self.assertNotIn("│\n", plain(self.tree(), tree__spacer_lines=False))
        self.assertIn("├ Ⅰ.1) A1\n└ Ⅰ.2) A2\n", plain(self.tree(), tree__spacer_lines=False))

    def test_spacers_after_bullets_can_be_turned_on(self):
        self.assertIn("│    • b\n│\n├ Ⅰ.1) A1\n", plain(self.tree(), tree__spacer_after_leaf=True))

    def test_the_blank_line_between_top_level_items_can_be_turned_off(self):
        text = plain(self.tree(), tree__blank_between_top_level=False)
        self.assertNotIn("\n\n", text)
        self.assertTrue(text.endswith("       • c\nⅡ) B\n"))

    def test_top_level_bullets_are_set_apart_from_numbered_items(self):
        """Top-level bullets are allowed (CR11's decision): one after a numbered item gets
        the blank line a numbered item gets, or it would read as that item's; bullets in a
        row stay together."""
        root = Node("root", children=[B("first"), H("One", B("a")), B("x"), B("y", "dot", B("sub")), H("Two")])
        self.assertEqual(plain(root), "• first\n"
                                      "\n"
                                      "Ⅰ) One\n"
                                      "     • a\n"
                                      "\n"
                                      "• x\n"
                                      "• y\n"
                                      "    • sub\n"
                                      "\n"
                                      "Ⅱ) Two\n")
        self.assertNotIn("\n\n", plain(root, tree__blank_between_top_level=False))

    def test_bullet_columns_follow_the_indent_rules(self):
        root = Node("root", children=[H("A", B("b", "dot", B("deep")), H("A1", B("c")))])
        self.assertEqual(plain(root, bullets__indent=2, bullets__nested_indent=1), "Ⅰ) A\n"
                                                                                  "│ • b\n"
                                                                                  "│  • deep\n"
                                                                                  "└ Ⅰ.1) A1\n"
                                                                                  "    • c\n")

    def test_connectors_come_from_the_rules(self):
        text = plain(self.tree(), tree__branch="+-", tree__last="`-", tree__trunk="|")
        self.assertIn("+-Ⅰ.1) A1\n", text)
        self.assertIn("`-Ⅰ.2) A2\n", text)
        self.assertIn("|    • b\n", text)

    def test_numbering_skips_bullets_and_restarts_in_each_item(self):
        root = Node("root", children=[H("A", H("x"), B("note"), H("y")), H("B", H("z"))])
        labels = [ln.prefix_text().strip("├└│ ") for ln in layout(root, Rules()) if ln.node and ln.node.kind == "heading"]
        self.assertEqual(labels, ["Ⅰ)", "Ⅰ.1)", "Ⅰ.2)", "Ⅱ)", "Ⅱ.1)"])

    def test_a_marker_from_a_newer_rules_file_is_drawn_as_a_bullet(self):
        root = Node("root", children=[H("A", B("b", "unheard-of"))])
        self.assertIn("     • b\n", plain(root))

    def test_each_item_is_one_line_and_knows_its_node(self):
        root = self.tree()
        lines = layout(root, Rules())
        items = [ln.node for ln in lines if ln.kind == "item"]
        self.assertEqual(items, [n for n in root.walk() if n is not root])
        self.assertEqual([ln.kind for ln in lines],
                         ["item", "item", "item", "spacer", "item", "item", "blank", "item"])
        self.assertTrue(all(ln.node is None for ln in lines if ln.kind in ("spacer", "blank")))

    def test_segments_tell_connectors_labels_markers_and_text_apart(self):
        root = Node("root", children=[H("A", Node("bullet", [Run("x"), Run("y", bold=True)]), H("A1"))])
        bullet = layout(root, Rules())[1]
        self.assertEqual([(s.role, s.text, s.bold) for s in bullet.segs()],
                         [("connector", "│    ", False), ("marker", "• ", False), ("text", "x", False),
                          ("text", "y", True)])
        heading = layout(root, Rules())[2]
        self.assertEqual([(s.role, s.text) for s in heading.segs()],
                         [("connector", "└ "), ("label", "Ⅰ.1) "), ("text", "A1")])


if __name__ == "__main__":
    unittest.main()
