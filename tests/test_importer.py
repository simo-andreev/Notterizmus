import unittest

from notterizmus.export import to_html, to_plain
from notterizmus.importer import (block_nodes, drop_chars, html_items, join_lines, parse, strip_runs,
                                  text_items)
from notterizmus.layout import layout
from notterizmus.model import Node, Run
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


def shape(forest):
    """The outline as nested tuples: (kind or marker, text, children...)."""
    return [(n.marker if n.kind == "bullet" else n.kind, n.text, *shape(n.children)) for n in forest]


def pasted(text):
    return shape(parse(text_items(text), Rules()))


class LabelsAndMarkersTest(unittest.TestCase):
    def test_labels_in_any_numbering_give_the_depth(self):
        self.assertEqual(pasted("2.1) Arabic\n2.1.1) deeper\n3) top"),
                         [("heading", "Arabic", ("heading", "deeper")), ("heading", "top")])
        self.assertEqual(pasted("II.1.a) x"), [("heading", "x")])
        self.assertEqual(pasted("Ⅱ) A\nⅡ.1) B\nⅡ.1.a) C\nⅢ) D"),
                         [("heading", "A", ("heading", "B", ("heading", "C"))), ("heading", "D")])

    def test_the_shallowest_label_pasted_becomes_the_top_level(self):
        self.assertEqual(pasted("Ⅱ.1.a) one\nⅡ.1.b) two\nⅡ.1.b.ⅰ) under two"),
                         [("heading", "one"), ("heading", "two", ("heading", "under two"))])

    def test_a_level_that_is_skipped_does_not_break_the_tree(self):
        self.assertEqual(pasted("1) A\n1.1.1) deep\n2) B"), [("heading", "A", ("heading", "deep")), ("heading", "B")])

    def test_a_label_needs_its_bracket_and_a_space(self):
        self.assertIsNone(parse(text_items("2.1 no bracket\n3.) odd"), Rules()))
        self.assertEqual(pasted("1)x\n- b"), [("dot", "1)x"), ("minus", "b")], "no space: ordinary text")

    def test_every_bullet_character_is_recognised(self):
        self.assertEqual(pasted("• a\n· b\n▪ c\n◦ d\n‣ e\n* f\n+ g\n- h\n– i\n— j\n! k\n? l"),
                         [("dot", "a"), ("dot", "b"), ("dot", "c"), ("dot", "d"), ("dot", "e"), ("dot", "f"),
                          ("plus", "g"), ("minus", "h"), ("minus", "i"), ("minus", "j"),
                          ("important", "k"), ("question", "l")])

    def test_a_marker_needs_a_space_after_it(self):
        self.assertEqual(pasted("- real\n-not a bullet\n+1 vote\n!!!\n?why"),
                         [("minus", "real"), ("dot", "-not a bullet"), ("dot", "+1 vote"), ("dot", "!!!"),
                          ("dot", "?why")])

    def test_a_marker_alone_is_an_empty_bullet(self):
        self.assertEqual(pasted("- a\n-\n- c"), [("minus", "a"), ("minus", ""), ("minus", "c")])

    def test_your_own_markers_are_recognised(self):
        rules = Rules()
        rules.data["markers"]["idea"] = {"symbol": "→", "trigger": ">", "label": "Idea"}
        forest = parse(text_items("→ why\n=> so"), rules)
        self.assertEqual(shape(forest), [("idea", "why"), ("dot", "=> so")])

    def test_bullets_go_under_the_numbered_item_above_them(self):
        self.assertEqual(pasted("I) Head\n  - a\n      - a1\n  - b\nII) Next\n  - c"),
                         [("heading", "Head", ("minus", "a", ("minus", "a1")), ("minus", "b")),
                          ("heading", "Next", ("minus", "c"))])

    def test_lines_without_a_marker_become_bullets_once_anything_is_structured(self):
        self.assertEqual(pasted("I) Head\nplain line\n  - under it"),
                         [("heading", "Head", ("dot", "plain line", ("minus", "under it")))])

    def test_connectors_and_spacer_lines_are_dropped(self):
        self.assertEqual(pasted("Ⅰ) A\n│    • note\n├ Ⅰ.1) B\n│ │\n│\n└ Ⅰ.2) C\n\n"),
                         [("heading", "A", ("dot", "note"), ("heading", "B"), ("heading", "C"))])

    def test_windows_line_ends_tabs_and_hard_spaces(self):
        self.assertEqual(pasted("- a\r\n\t- b\r- c"), [("minus", "a", ("minus", "b")), ("minus", "c")])
        self.assertEqual(pasted("I)\u00a0Head\n\u00a0\u00a0-\u00a0b"), [("heading", "Head", ("minus", "b"))])

    def test_trailing_spaces_are_trimmed(self):
        forest = parse(text_items("- text   \n-    padded start"), Rules())
        self.assertEqual([n.text for n in forest], ["text", "padded start"])


class HtmlTest(unittest.TestCase):
    def test_bold_and_italic_come_from_tags_and_styles(self):
        items = html_items('<p><b>b</b> <strong>s</strong> <i>i</i> <em>e</em> '
                           '<span style="font-weight: 700">w</span> <span style="font-weight:bold">wb</span> '
                           '<span style="FONT-STYLE: Italic">fs</span></p>')
        runs = items[0][1]
        self.assertEqual([r.text for r in runs if r.bold], ["b", "s", "w", "wb"])
        self.assertEqual([r.text for r in runs if r.italic], ["i", "e", "fs"])

    def test_a_style_can_switch_bold_off_again(self):
        runs = html_items('<b>x<span style="font-weight: normal">y</span>z</b>')[0][1]
        self.assertEqual(runs, [Run("x", bold=True), Run("y"), Run("z", bold=True)])
        self.assertEqual(html_items('<span style="font-weight: 400">thin</span>')[0][1], [Run("thin")])

    def test_whitespace_collapses_except_where_it_is_kept(self):
        items = html_items("<p>a   b\n c</p><pre>x   y</pre><p style=\"white-space: pre-wrap\">p  q</p>")
        self.assertEqual([it[1] for it in items], [[Run("a b c")], [Run("x   y")], [Run("p  q")]])

    def test_blocks_and_line_breaks_start_new_lines(self):
        items = html_items("<div>one<br>two</div><h2>three</h2><ul><li>four</li><li>five</li></ul>")
        self.assertEqual([it[1][0].text for it in items if it[1]], ["one", "two", "three", "four", "five"])

    def test_styles_scripts_and_the_head_are_skipped(self):
        items = html_items("<head><title>T</title><style>p {}</style></head><script>x()</script><p>- a</p>")
        self.assertEqual([it[1] for it in items], [[Run("- a")]])

    def test_entities_and_hard_spaces_become_plain_characters(self):
        self.assertEqual(html_items("<p>a&nbsp;&amp;&nbsp;b &lt;c&gt;</p>")[0][1], [Run("a & b <c>")])

    def test_a_table_keeps_its_rows_and_cells_on_one_line_each(self):
        items = html_items("<table><tr><td>a<br>b</td><td><p>c</p><p>d</p></td></tr><tr><td>only</td></tr></table>")
        kind, rows, header = items[0]
        self.assertEqual((kind, header), ("table", False))
        self.assertEqual(rows, [[[Run("a b")], [Run("c d")]], [[Run("only")]]])

    def test_a_short_table_row_is_filled_out(self):
        forest = parse(html_items("<p>- x</p><table><tr><td>a</td><td>b</td></tr><tr><td>only</td></tr></table>"),
                       Rules())
        table = forest[1]
        self.assertEqual(table.kind, "table")
        self.assertEqual(table.data["rows"], [[[Run("a")], [Run("b")]], [[Run("only")], []]])

    def test_a_table_alone_is_not_an_outline_but_its_tables_can_be_had(self):
        items = html_items("<p>Some text about it.</p><table><tr><th>k</th><th>v</th></tr><tr><td>1</td></tr></table>"
                           "<table><tr><td>second</td></tr></table>")
        self.assertIsNone(parse(items, Rules()), "no markers: the text is ordinary text")
        first, second = block_nodes(items)
        self.assertEqual((first.kind, first.data["header"], second.data["header"]), ("table", True, False))
        self.assertEqual(first.data["rows"], [[[Run("k")], [Run("v")]], [[Run("1")], []]], "short rows filled out")
        self.assertEqual(second.data["rows"], [[[Run("second")]]])
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(block_nodes(text_items("- no table here")), [])

    def test_text_before_a_table_ends_its_line(self):
        items = html_items("- before<table><tr><td>c</td></tr></table>- after")
        self.assertEqual([it[0] for it in items], ["line", "table", "line"])

    def test_the_apps_own_html_comes_back_as_the_same_outline(self):
        root = sample()
        root.children[1].children[0].runs = [Run("plain "), Run("bold", bold=True), Run(" it", italic=True)]
        root.children[0].append(Node("bullet", runs=[Run("remember this")], marker="important"))
        root.children[0].append(Node("bullet", runs=[Run("check this")], marker="question"))
        root.children[0].append(Node("table", data={"header": True, "rows": [[[Run("k")], [Run("v", bold=True)]],
                                                                               [[Run("1")], []]]}))
        forest = parse(html_items(to_html(layout(root, Rules()))), Rules())
        strip = lambda nodes: [{k: v for k, v in n.to_json().items() if k not in ("id", "children")}
                               | {"children": strip(n.children)} for n in nodes]
        self.assertEqual(strip(forest), strip(root.children))


class JoinLinesTest(unittest.TestCase):
    def lines(self, *texts):
        return [[Run(t)] for t in texts]

    def test_lines_join_with_one_space_and_blank_lines_go(self):
        self.assertEqual(join_lines(self.lines("  one  ", "", "two", "   ", "three ")), [Run("one two three")])
        self.assertEqual(join_lines(self.lines("", "  ")), [])

    def test_a_word_hyphenated_at_a_line_end_is_put_back_together(self):
        self.assertEqual(join_lines(self.lines("The quick brown fox jum-", "ps over")), [Run("The quick brown fox jumps over")])
        self.assertEqual(join_lines(self.lines("репли-", "кация")), [Run("репликация")])

    def test_other_hyphens_at_a_line_end_stay(self):
        self.assertEqual(join_lines(self.lines("well-", "Known")), [Run("well- Known")], "a capital starts a new word")
        self.assertEqual(join_lines(self.lines("pages 1-", "2")), [Run("pages 1- 2")], "numbers aren't hyphenated words")
        self.assertEqual(join_lines(self.lines("a dash -", "then text")), [Run("a dash - then text")])

    def test_formatting_survives_the_join(self):
        got = join_lines([[Run("bold ", bold=True)], [Run("plain "), Run("it", italic=True)]])
        self.assertEqual(got, [Run("bold", bold=True), Run(" plain "), Run("it", italic=True)])

    def test_line_breaks_inside_a_run_become_spaces(self):
        self.assertEqual(join_lines([[Run("a\nb")]]), [Run("a b")])


class RunHelpersTest(unittest.TestCase):
    def test_dropping_leading_characters_across_runs(self):
        runs = [Run("ab", bold=True), Run("cd")]
        self.assertEqual(drop_chars(runs, 0), runs)
        self.assertEqual(drop_chars(runs, 1), [Run("b", bold=True), Run("cd")])
        self.assertEqual(drop_chars(runs, 3), [Run("d")])
        self.assertEqual(drop_chars(runs, 9), [])

    def test_stripping_trailing_whitespace_across_runs(self):
        self.assertEqual(strip_runs([Run("a "), Run("  ", bold=True)]), [Run("a")])
        self.assertEqual(strip_runs([Run("  lead stays ")]), [Run("  lead stays")])
        self.assertEqual(strip_runs([Run(" "), Run("")]), [])


if __name__ == "__main__":
    unittest.main()
