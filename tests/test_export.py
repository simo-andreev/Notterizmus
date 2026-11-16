"""What Copy for TopCoding and Show Plain Text produce from the laid-out lines."""
import unittest

from notterizmus.export import runs_html, to_html, to_plain
from notterizmus.layout import layout
from notterizmus.model import Node, Run
from notterizmus.rules import Rules

PRE = '<span style="white-space: pre-wrap;">{}</span>'


def H(text, *kids):
    return Node("heading", [Run(text)], children=list(kids))


def B(text, *kids, marker="dot"):
    return Node("bullet", [Run(text)], marker=marker, children=list(kids))


def T(rows, header=False):
    return Node("table", data={"header": header, "rows": [[[Run(c)] if c else [] for c in row] for row in rows]})


def lines(*top, **changes):
    rules = Rules()
    for name, value in changes.items():
        section, key = name.split("__")
        rules.data[section][key] = value
    return layout(Node("root", children=list(top)), rules)


class HtmlTest(unittest.TestCase):
    def test_one_paragraph_with_a_line_break_per_line(self):
        html = to_html(lines(H("A", B("b")), H("B")))
        self.assertTrue(html.startswith('<meta charset="utf-8"><p>'))
        self.assertTrue(html.endswith("</p>"))
        self.assertEqual(html.count("<p>"), 1)
        self.assertEqual(html.count("<br>"), 3, "A, its bullet, the blank line, B")
        self.assertIn(f"<br><br>{PRE.format('Ⅱ) ')}", html, "the blank line between top-level items is an empty line")

    def test_text_that_looks_like_markup_is_escaped(self):
        html = to_html(lines(H('a < b & c > d "q"', T([["<td>", "&amp;"]]))))
        self.assertIn(PRE.format('a &lt; b &amp; c &gt; d "q"'), html)
        self.assertIn(PRE.format("&lt;td&gt;"), html)
        self.assertIn(PRE.format("&amp;amp;"), html)
        self.assertEqual(html.count("<td>"), 2, "the typed <td> didn't become a cell")

    def test_bold_and_italic_wrap_the_whitespace_keeping_span(self):
        self.assertEqual(runs_html([Run("a", True, True), Run(""), Run("b")]),
                         f"<strong><em>{PRE.format('a')}</em></strong>{PRE.format('b')}")
        self.assertEqual(runs_html([Run("  two  spaces  ", italic=True)]), f"<em>{PRE.format('  two  spaces  ')}</em>")
        self.assertEqual(runs_html([]), "")

    def test_spacer_lines_end_at_the_connector(self):
        html = to_html(lines(H("A", H("A1"), H("A2"))))
        self.assertIn(f"<br>{PRE.format('│')}<br>", html, "no trailing space after the trunk")

    def test_a_spacer_line_loses_the_trailing_space_of_a_custom_trunk(self):
        html = to_html(lines(H("A", H("A1"), H("A2")), tree__trunk="| "))
        self.assertIn(f"<br>{PRE.format('|')}<br>", html)
        self.assertNotIn(PRE.format("| "), html)

    def test_code_prefix_wraps_connectors_only(self):
        html = to_html(lines(H("A", B("b"), H("A1"))), code_prefix=True)
        self.assertIn(f"<code>{PRE.format('│    ')}</code>{PRE.format('• ')}{PRE.format('b')}", html)
        self.assertIn(f"<code>{PRE.format('└ ')}</code>{PRE.format('Ⅰ.1) ')}", html)
        self.assertEqual(html.count("<code>"), 2, "labels, markers and text stay as they are")
        self.assertNotIn("<code>", to_html(lines(H("A", B("b"), H("A1")))))

    def test_bold_labels_and_connectors_follow_the_rules(self):
        html = to_html(lines(H("A", H("A1")), tree__bold_connectors=True, numbering__bold_label=True))
        self.assertIn(f"<strong>{PRE.format('Ⅰ) ')}</strong>{PRE.format('A')}", html)
        self.assertIn(f"<strong>{PRE.format('└ ')}</strong><strong>{PRE.format('Ⅰ.1) ')}</strong>", html)

    def test_a_table_breaks_the_paragraph_and_keeps_its_cells(self):
        html = to_html(lines(H("A", T([["h1", "h2"], ["", "x"]], header=True), B("after"))))
        table = ("<table><tbody><tr><th><p>" + PRE.format("h1") + "</p></th><th><p>" + PRE.format("h2")
                 + "</p></th></tr><tr><td><p><br></p></td><td><p>" + PRE.format("x") + "</p></td></tr></tbody></table>")
        self.assertIn(f"</p>{table}<p>", html)
        self.assertEqual(html.count("<p>" + PRE.format("Ⅰ) ")), 1)

    def test_without_a_header_every_cell_is_a_plain_cell(self):
        html = to_html(lines(H("A", T([["a"], ["b"]]))))
        self.assertNotIn("<th>", html)
        self.assertEqual(html.count("<td>"), 2)

    def test_an_empty_chapter(self):
        self.assertEqual(to_html(lines()), '<meta charset="utf-8">')
        self.assertEqual(to_plain(lines()), "\n")
        self.assertEqual(to_plain(lines(H(""))), "Ⅰ)\n", "no trailing space after an empty item's label")


class PlainTest(unittest.TestCase):
    def test_lines_have_no_trailing_spaces_and_the_text_ends_with_a_newline(self):
        text = to_plain(lines(H("A  ", B("b "), H("A1")), H("B")))
        self.assertTrue(text.endswith("B\n"))
        for line in text.split("\n"):
            self.assertEqual(line, line.rstrip())

    def test_a_table_is_drawn_in_box_characters_under_its_item(self):
        text = to_plain(lines(H("t", T([["a", "bb"], ["ccc", ""]]))))
        self.assertEqual(text, "Ⅰ) t\n"
                               "     ┌─────┬────┐\n"
                               "     │ a   │ bb │\n"
                               "     │ ccc │    │\n"
                               "     └─────┴────┘\n")

    def test_a_header_row_is_ruled_off(self):
        text = to_plain(lines(H("t", T([["a", "b"], ["cc", ""]], header=True))))
        self.assertEqual(text.split("\n")[1:6], ["     ┌────┬───┐", "     │ a  │ b │", "     ├────┼───┤",
                                                  "     │ cc │   │", "     └────┴───┘"])

    def test_a_header_alone_has_no_rule_under_it(self):
        text = to_plain(lines(H("t", T([["a"]], header=True))))
        self.assertNotIn("├", text)
        self.assertEqual(text.count("│ a │"), 1)

    def test_rows_of_different_lengths_are_filled_out(self):
        table = Node("table", data={"rows": [[[Run("a")], [Run("b")]], [[Run("cc")]]]})
        self.assertEqual(to_plain(lines(H("t", table))).split("\n")[2:4], ["     │ a  │ b │", "     │ cc │   │"])

    def test_a_table_without_rows_draws_nothing(self):
        self.assertEqual(to_plain(lines(H("t", Node("table", data={"rows": []})), H("u"))), "Ⅰ) t\n\nⅡ) u\n")

    def test_a_table_under_a_bullet_keeps_the_trunk_beside_it(self):
        text = to_plain(lines(H("A", B("b", T([["x"]])), H("A1"))))
        self.assertEqual(text.split("\n")[2:5], ["│        ┌───┐", "│        │ x │", "│        └───┘"])

    def test_wide_and_cyrillic_text_is_counted_by_characters(self):
        text = to_plain(lines(H("t", T([["ключ", "ab"], ["x", "стойност"]]))))
        rows = [r for r in text.split("\n") if "│" in r]
        self.assertEqual(len({len(r) for r in rows}), 1, "the right edge lines up")


if __name__ == "__main__":
    unittest.main()
