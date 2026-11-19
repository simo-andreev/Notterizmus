"""The node tree and its operations, and reading and writing chapter files."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from notterizmus.model import (FORMAT, Document, Node, Run, can_contain, chapter_filename, display_order,
                               enclosing_heading, fresh_ids, heading_numbers, indent, is_text,
                               leaf_insert_index, move, new_table_data, normalize_runs, outdent,
                               remove_items, remove_promote, runs_text, selected_json, set_kind)


def H(text, *kids):
    return Node("heading", [Run(text)], children=list(kids))


def B(text, *kids, marker="dot"):
    return Node("bullet", [Run(text)], marker=marker, children=list(kids))


def T(*rows):
    return Node("table", data={"header": False, "rows": [[[Run(c)] for c in row] for row in rows]})


def texts(nodes):
    return [n.text for n in nodes]


class RunsTest(unittest.TestCase):
    def test_neighbours_with_the_same_format_merge_and_empty_runs_go(self):
        runs = [Run("a"), Run(""), Run("b"), Run("c", bold=True), Run("d", True, True), Run("", True),
                Run("e", True, True)]
        self.assertEqual(normalize_runs(runs), [Run("ab"), Run("c", bold=True), Run("de", True, True)])
        self.assertEqual(normalize_runs([Run(""), Run("", italic=True)]), [])

    def test_normalizing_leaves_the_given_runs_alone(self):
        first = Run("a")
        normalize_runs([first, Run("b")])
        self.assertEqual(first.text, "a")

    def test_a_run_is_stored_with_only_the_formats_it_has(self):
        self.assertEqual(Run("x").to_json(), {"t": "x"})
        self.assertEqual(Run("x", bold=True).to_json(), {"t": "x", "b": True})
        self.assertEqual(Run("x", italic=True).to_json(), {"t": "x", "i": True})
        for run in (Run("plain"), Run("both", True, True), Run("Ⅱ и кирилица", italic=True)):
            self.assertEqual(Run.from_json(run.to_json()), run)

    def test_a_run_with_missing_fields_reads_as_plain_text(self):
        self.assertEqual(Run.from_json({}), Run(""))
        self.assertEqual(Run.from_json({"t": "x", "b": 1, "i": 0}), Run("x", bold=True))

    def test_text_of_runs(self):
        self.assertEqual(runs_text([Run("a "), Run("b", bold=True)]), "a b")
        self.assertEqual(H("title").text, "title")


class TreeTest(unittest.TestCase):
    def test_children_know_their_parent_and_place(self):
        a, b, c = B("a"), B("b"), B("c")
        top = H("top", a, c)
        top.insert(1, b)
        self.assertEqual(texts(top.children), ["a", "b", "c"])
        self.assertTrue(all(n.parent is top for n in (a, b, c)))
        self.assertEqual((a.index(), c.index()), (0, 2))
        self.assertIsNone(a.prev_sibling())
        self.assertIs(c.prev_sibling(), b)
        self.assertIs(top.append(B("d")).parent, top)
        b.detach()
        self.assertIsNone(b.parent)
        self.assertEqual(texts(top.children), ["a", "c", "d"])

    def test_walk_and_display_order_go_depth_first(self):
        root = Node("root", children=[H("A", B("a1", B("a2")), H("A1")), H("B")])
        self.assertEqual(texts(display_order(root)), ["A", "a1", "a2", "A1", "B"])
        self.assertIs(next(root.walk()), root)
        self.assertNotIn(root, display_order(root))

    def test_every_node_gets_its_own_id(self):
        nodes = [Node("bullet") for _ in range(200)]
        self.assertEqual(len({n.id for n in nodes}), 200)
        self.assertEqual(Node("bullet", id="mine").id, "mine")

    def test_fresh_ids_renames_the_whole_subtree(self):
        top = H("A", B("a", B("b")), T(["x"]))
        before = [n.id for n in top.walk()]
        self.assertIs(fresh_ids(top), top)
        after = [n.id for n in top.walk()]
        self.assertFalse(set(before) & set(after))
        self.assertEqual(len(set(after)), len(after))

    def test_what_can_sit_under_what(self):
        allowed = {(p, c): can_contain(Node(p), Node(c))
                   for p in ("root", "heading", "bullet", "table", "drawing")
                   for c in ("heading", "bullet", "table", "drawing")}
        for child in ("heading", "bullet", "table", "drawing"):
            self.assertTrue(allowed["root", child])
            self.assertTrue(allowed["heading", child])
            self.assertFalse(allowed["table", child], "a table holds cells, not items")
            self.assertFalse(allowed["drawing", child], "nothing is put into a block we don't know")
        self.assertFalse(allowed["bullet", "heading"], "a numbered item can't sit under a bullet")
        self.assertTrue(allowed["bullet", "bullet"])
        self.assertTrue(allowed["bullet", "table"])

    def test_only_headings_and_bullets_hold_text(self):
        self.assertEqual([is_text(Node(k)) for k in ("heading", "bullet", "table", "drawing", "root")],
                         [True, True, False, False, False])

    def test_new_table_cells_are_separate_lists(self):
        data = new_table_data(2, 3)
        self.assertEqual((data["header"], len(data["rows"]), [len(r) for r in data["rows"]]), (False, 2, [3, 3]))
        data["rows"][0][0].append(Run("x"))
        self.assertEqual([cell for row in data["rows"] for cell in row].count([]), 5,
                         "typing in one cell must not show up in the others")


class IndentTest(unittest.TestCase):
    def test_indent_moves_an_item_under_the_one_above(self):
        b1, b2 = B("b1"), B("b2")
        top = H("A", b1, b2)
        self.assertTrue(indent(b2))
        self.assertIs(b2.parent, b1)
        self.assertEqual(texts(top.children), ["b1"])

    def test_indent_appends_after_the_children_already_there(self):
        b1, b2 = B("b1", B("old")), B("b2")
        H("A", b1, b2)
        indent(b2)
        self.assertEqual(texts(b1.children), ["old", "b2"])

    def test_the_first_item_cannot_be_indented(self):
        b1 = B("b1")
        top = H("A", b1)
        self.assertFalse(indent(b1))
        self.assertIs(b1.parent, top)
        self.assertFalse(indent(Node("root", children=[top]).children[0]))

    def test_a_numbered_item_cannot_be_indented_under_a_bullet(self):
        b1, sub = B("b1"), H("A1")
        top = H("A", b1, sub)
        self.assertFalse(indent(sub))
        self.assertEqual(texts(top.children), ["b1", "A1"])

    def test_nothing_is_indented_under_a_table(self):
        table, after = T(["x"]), B("after")
        top = H("A", table, after)
        self.assertFalse(indent(after))
        self.assertEqual(top.children, [table, after])

    def test_outdent_puts_an_item_right_after_its_parent(self):
        b2 = B("b2")
        b1, b3 = B("b1", b2), B("b3")
        top = H("A", b1, b3)
        self.assertTrue(outdent(b2))
        self.assertEqual(texts(top.children), ["b1", "b2", "b3"])
        self.assertEqual(b2.kind, "bullet")

    def test_a_bullet_outdented_to_the_top_level_becomes_numbered(self):
        b1 = B("b1", marker="plus")
        root = Node("root", children=[H("A", b1), H("B")])
        self.assertTrue(outdent(b1))
        self.assertEqual([(n.kind, n.text) for n in root.children],
                         [("heading", "A"), ("heading", "b1"), ("heading", "B")])

    def test_a_top_level_item_cannot_be_outdented(self):
        root = Node("root", children=[H("A")])
        self.assertFalse(outdent(root.children[0]))
        self.assertFalse(outdent(root))

    def test_indent_then_outdent_restores_the_outline(self):
        root = Node("root", children=[H("A", H("A1", B("x")), H("A2"), H("A3"))])
        a2 = root.children[0].children[1]
        before = [c.to_json() for c in root.children]
        self.assertTrue(indent(a2))
        self.assertTrue(outdent(a2))
        self.assertEqual([c.to_json() for c in root.children], before)

    def test_move_swaps_with_a_sibling_and_stops_at_the_ends(self):
        root = Node("root", children=[H("A"), H("B"), H("C")])
        a, b, c = root.children
        self.assertFalse(move(a, -1))
        self.assertFalse(move(c, 1))
        self.assertTrue(move(a, 1))
        self.assertEqual(texts(root.children), ["B", "A", "C"])
        self.assertTrue(move(c, -1))
        self.assertEqual(texts(root.children), ["B", "C", "A"])
        self.assertTrue(all(n.parent is root for n in (a, b, c)))


class RemoveAndKindTest(unittest.TestCase):
    def test_removing_an_item_puts_its_children_in_its_place(self):
        gone = H("A1", B("x"), H("A1a"), B("y"))
        top = H("A", B("before"), gone, H("A2"))
        remove_promote(gone)
        self.assertEqual(texts(top.children), ["before", "x", "A1a", "y", "A2"])
        self.assertTrue(all(c.parent is top for c in top.children))
        self.assertEqual((gone.parent, gone.children), (None, []))

    def test_bullets_of_a_removed_top_level_item_become_numbered(self):
        gone = H("Going", B("was a bullet", B("nested stays a bullet"), marker="plus"), T(["x"]), H("Sub"))
        root = Node("root", children=[H("Before"), gone, H("After")])
        remove_promote(gone)
        self.assertEqual([(n.kind, n.text) for n in root.children],
                         [("heading", "Before"), ("heading", "was a bullet"), ("table", ""), ("heading", "Sub"),
                          ("heading", "After")], "top-level items are always numbered")
        self.assertEqual([(n.kind, n.text) for n in root.children[1].children], [("bullet", "nested stays a bullet")])

    def test_removing_a_leaf_just_removes_it(self):
        leaf = B("leaf")
        top = H("A", B("a"), leaf, B("b"))
        remove_promote(leaf)
        self.assertEqual(texts(top.children), ["a", "b"])

    def test_removing_selected_items_keeps_the_sub_items_that_werent_selected(self):
        sub = H("Sub", B("one", B("one.a")), B("two"))
        top = H("A", B("before"), sub, B("after"))
        root = Node("root", children=[top, H("B", B("b1"))])
        remove_items([top.children[0], sub])
        self.assertEqual(texts(top.children), ["one", "two", "after"], "they move up into the section's place")
        self.assertEqual(texts(top.children[0].children), ["one.a"])
        remove_items([root.children[1]])
        self.assertEqual([(n.kind, n.text) for n in root.children], [("heading", "A"), ("heading", "b1")],
                         "a top-level item's bullets become numbered, as with remove_promote")

    def test_removing_an_item_with_everything_under_it_selected_removes_them_all(self):
        top = H("A", B("x", B("x1", B("x1a"))), B("y"))
        Node("root", children=[top])
        x = top.children[0]
        remove_items(list(x.walk()))
        self.assertEqual(texts(top.children), ["y"])

    def test_a_block_from_a_newer_version_goes_whole(self):
        newer = Node("chart", children=[H("inside")])
        top = H("A", newer, B("after"))
        Node("root", children=[top])
        remove_items([newer])
        self.assertEqual(texts(top.children), ["after"], "its sub-items aren't shown, so they aren't promoted")
        hidden = H("hidden")
        newer = Node("chart", children=[hidden])
        top.insert(0, newer)
        remove_items([hidden])
        self.assertEqual(newer.children, [hidden], "an item inside one isn't removed on its own")

    def test_selected_json_holds_exactly_the_selected_items_in_their_shape(self):
        sub = H("Sub", B("one", B("one.a")), B("two"))
        top = H("A", B("before"), sub, B("after"))
        Node("root", children=[top])
        one, one_a = sub.children[0], sub.children[0].children[0]

        def shape(js):
            return [(j["runs"][0]["t"], shape(j.get("children", []))) for j in js]

        self.assertEqual(shape(selected_json([top.children[0], sub])), [("before", []), ("Sub", [])])
        self.assertEqual(shape(selected_json([sub, one, one_a])), [("Sub", [("one", [("one.a", [])])])])
        self.assertEqual(shape(selected_json([sub, one_a])), [("Sub", [("one.a", [])])],
                         "an unselected item in between gives way to its selected sub-items")
        self.assertEqual(shape(selected_json(list(top.walk()))), shape([top.to_json()]))

    def test_selected_json_keeps_a_block_from_a_newer_version_whole(self):
        newer = Node("chart", children=[H("inside")])
        newer.extra = {"spec": {"bars": 3}}
        top = H("A", newer)
        Node("root", children=[top])
        self.assertEqual(selected_json([newer]), [newer.to_json()])

    def test_a_numbered_item_cannot_become_a_bullet_while_it_has_numbered_children(self):
        top = H("A", B("b"), H("A1"))
        Node("root", children=[top])
        self.assertIn("numbered sub-items", set_kind(top, "bullet"))
        self.assertEqual(top.kind, "heading")
        self.assertIsNone(set_kind(top.children[1], "bullet", "plus"))
        self.assertEqual((top.children[1].kind, top.children[1].marker), ("bullet", "plus"))

    def test_a_top_level_item_cannot_become_a_bullet(self):
        """Top-level items are always numbered (README, the guide), but only outdent and
        remove_promote kept to it: "* " typed at the start of one made a bullet (CR11)."""
        top = H("A", B("b"))
        Node("root", children=[top])
        self.assertIn("always numbered", set_kind(top, "bullet"))
        self.assertEqual(top.kind, "heading")
        self.assertIsNone(set_kind(top.children[0], "bullet", "plus"), "below the top level it can")

    def test_a_bullet_under_a_bullet_cannot_become_numbered(self):
        inner = B("inner")
        H("A", B("outer", inner))
        self.assertIn("under a bullet", set_kind(inner, "heading"))
        self.assertEqual(inner.kind, "bullet")

    def test_changing_the_kind_keeps_the_marker_unless_one_is_given(self):
        item = B("x", marker="minus")
        H("A", item)
        self.assertIsNone(set_kind(item, "heading"))
        self.assertIsNone(set_kind(item, "bullet"))
        self.assertEqual((item.kind, item.marker), ("bullet", "minus"), "back to the marker it had")
        self.assertIsNone(set_kind(item, "bullet", "dot"))
        self.assertEqual(item.marker, "dot")


class NumberingTest(unittest.TestCase):
    def setUp(self):
        self.deep = B("deep")
        self.b2b = H("B2b", self.deep)
        self.b = H("B", B("b"), H("B1"), B("mid"), H("B2", H("B2a"), self.b2b))
        self.stray = B("stray")
        self.root = Node("root", children=[H("A"), self.stray, self.b])

    def test_numbers_count_only_numbered_siblings(self):
        self.assertEqual(heading_numbers(self.b), [2], "the bullet between A and B doesn't count")
        self.assertEqual(heading_numbers(self.b2b), [2, 2, 2])
        self.assertEqual(heading_numbers(self.deep), [], "a bullet has no number")

    def test_the_enclosing_numbered_item(self):
        self.assertIs(enclosing_heading(self.b2b), self.b2b)
        self.assertIs(enclosing_heading(self.deep), self.b2b)
        self.assertIsNone(enclosing_heading(self.stray))
        self.assertIsNone(enclosing_heading(self.root))

    def test_new_bullets_go_after_the_leading_ones_and_before_numbered_children(self):
        self.assertEqual(leaf_insert_index(self.b), 1)
        self.assertEqual(leaf_insert_index(self.b2b), 1, "no numbered children: at the end")
        self.assertEqual(leaf_insert_index(H("empty")), 0)


class NodeJsonTest(unittest.TestCase):
    def test_each_kind_stores_what_it_needs(self):
        self.assertEqual(H("t").to_json().keys(), {"kind", "id", "runs"})
        self.assertEqual(B("t", marker="plus").to_json().keys(), {"kind", "id", "runs", "marker"})
        table = T(["a", "b"]).to_json()
        self.assertEqual(table.keys(), {"kind", "id", "data"})
        self.assertEqual(table["data"], {"header": False, "rows": [[[{"t": "a"}], [{"t": "b"}]]]})
        self.assertEqual(H("t", B("c")).to_json()["children"][0]["runs"], [{"t": "c"}])

    def test_a_tree_survives_json(self):
        top = H("A", B("b", B("c", marker="minus"), T(["x", "y"], ["", "z"])), H("A1"))
        top.children[0].runs = [Run("b"), Run("old", True), Run("it", italic=True)]
        top.children[0].children[1].data["header"] = True
        again = Node.from_json(json.loads(json.dumps(top.to_json())))
        self.assertEqual(again.to_json(), top.to_json())
        self.assertIs(again.children[0].parent, again)
        self.assertEqual(again.children[0].children[1].data["rows"][0][1], [Run("y")])

    def test_missing_fields_get_defaults(self):
        bullet = Node.from_json({"kind": "bullet"})
        self.assertEqual((bullet.runs, bullet.marker, bullet.children), ([], "dot", []))
        self.assertTrue(bullet.id)
        table = Node.from_json({"kind": "table", "id": "t", "data": None})
        self.assertEqual(table.to_json(), {"kind": "table", "id": "t", "data": {"header": False, "rows": []}})


class DocumentTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_a_new_chapter_starts_with_one_empty_numbered_item(self):
        doc = Document.new("Book", 7, "Title")
        self.assertEqual([(n.kind, n.text) for n in doc.root.children], [("heading", "")])
        self.assertEqual(doc.to_json()["chapter"], {"number": 7, "title": "Title"})
        self.assertEqual(doc.to_json()["format"], FORMAT)
        self.assertNotIn("lang", doc.to_json(), "no language until one is chosen")

    def test_an_empty_file_opens_with_one_empty_item(self):
        doc = Document.from_json({})
        self.assertEqual((doc.book, doc.chapter_no, doc.chapter_title, doc.lang), ("", 1, "", None))
        self.assertEqual([n.kind for n in doc.root.children], ["heading"])
        self.assertEqual(len(Document.from_json({"content": [], "chapter": {}}).root.children), 1)

    def test_a_file_that_is_not_a_chapter_is_refused_with_one_kind_of_error(self):
        # Each of these used to raise something the app didn't expect (AttributeError,
        # TypeError...) or open and fail later; as the last chapter open, it kept the
        # app from starting.
        for text in ("[]", "null", '"just text"', "5", '{"content": [1]}', '{"content": {"a": 1}}',
                     '{"content": "abc"}', '{"chapter": 5}', '{"chapter": {"number": "x"}}', '{"book": 5}',
                     '{"lang": 3}', '{"format": 2}', '{"content": [{"id": "no kind"}]}', '{"content": [{"kind": 3}]}',
                     '{"content": [{"kind": "bullet", "runs": [{"t": 5}]}]}',
                     '{"content": [{"kind": "bullet", "runs": "text"}]}',
                     '{"content": [{"kind": "bullet", "marker": []}]}',
                     '{"content": [{"kind": "bullet", "id": 7}]}',
                     '{"content": [{"kind": "bullet", "children": {"a": 1}}]}',
                     '{"content": [{"kind": "heading", "children": [{"kind": "bullet", "children": [null]}]}]}',
                     '{"content": [{"kind": "table", "data": {"rows": [[5]]}}]}',
                     '{"content": [{"kind": "table", "data": "rows"}]}'):
            with self.subTest(text=text):
                path = self.dir / "c.notz"
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError) as caught:
                    Document.load(path)
                self.assertEqual(str(caught.exception), "this isn't a Notterizmus chapter file")
                self.assertEqual(path.read_text(encoding="utf-8"), text, "and the file is left as it is")

    def test_a_file_that_is_not_json_or_not_there(self):
        path = self.dir / "c.notz"
        for data in (b"", b"{not json", b"\xff\xfe not utf-8"):
            path.write_bytes(data)
            with self.assertRaises(ValueError):
                Document.load(path)
        with self.assertRaises(OSError):
            Document.load(self.dir / "missing.notz")

    def test_missing_fields_and_a_whole_number_written_as_a_fraction_are_accepted(self):
        doc = Document.from_json({"chapter": {"number": 3.0}, "content": [{"kind": "table", "data": []}]})
        self.assertEqual((doc.chapter_no, type(doc.chapter_no), doc.book, doc.chapter_title), (3, int, "", ""))
        self.assertEqual(doc.root.children[0].data, {"header": False, "rows": []})
        nulls = Document.from_json({"format": None, "book": None, "lang": None, "content": None,
                                    "chapter": {"number": None, "title": None}})
        self.assertEqual(nulls.to_json()["chapter"], {"number": 1, "title": ""})
        self.assertEqual((nulls.book, nulls.format, len(nulls.root.children)), ("", FORMAT, 1))
        item = Document.from_json({"content": [{"kind": "bullet", "id": None, "children": None}]}).root.children[0]
        self.assertTrue(item.id, "an item without an id gets one")
        with self.assertRaises(ValueError):
            Document.from_json({"chapter": {"number": 3.5}})
        with self.assertRaises(ValueError):
            Document.from_json({"chapter": {"number": True}})

    def test_a_null_marker_or_null_text_gets_its_default(self):
        doc = Document.from_json({"content": [{"kind": "heading", "marker": None, "runs": [{"t": None}],
                                               "children": [{"kind": "bullet", "marker": None}]}]})
        h = doc.root.children[0]
        self.assertEqual((h.text, h.marker, h.children[0].marker), ("", "dot", "dot"))

    def test_a_file_nested_too_deep_is_refused_as_not_a_chapter(self):
        path = self.dir / "deep.notz"
        for depth in (5000, 100000):  # too deep for Node.from_json; too deep for json itself
            with self.subTest(depth=depth):
                path.write_text('{"content": [' + '{"kind": "heading", "children": [' * depth
                                + "]}" * depth + "]}", encoding="utf-8")
                with self.assertRaises(ValueError):
                    Document.load(path)

    def test_saving_and_loading_keeps_everything(self):
        path = self.dir / "new" / "folders" / "02 Т.notz"
        doc = Document(Node("root", children=[H("Заглавие ✓", B("бележка"))]), "Книга", 2, "Т", path,
                       lang="bg_BG")
        doc.save()
        again = Document.load(path)
        self.assertEqual(again.to_json(), doc.to_json())
        self.assertEqual((again.path, again.lang, again.book), (path, "bg_BG", "Книга"))

    def test_the_file_is_readable_json_with_the_text_as_typed(self):
        path = self.dir / "c.notz"
        Document(Node("root", children=[H("Ⅱ) Заглавие")]), "B", 1, "T", path).save()
        raw = path.read_text(encoding="utf-8")
        self.assertIn("Ⅱ) Заглавие", raw, "not \\u escapes")
        self.assertTrue(raw.endswith("\n"))
        self.assertEqual(json.loads(raw)["format"], FORMAT)

    def test_saving_leaves_only_the_chapter_file(self):
        path = self.dir / "c.notz"
        doc = Document.new("B", 1, "T", path)
        for text in ("one", "two", "three"):
            doc.root.children[0].runs = [Run(text)]
            doc.save()
        self.assertEqual(os.listdir(self.dir), ["c.notz"])
        self.assertEqual(Document.load(path).root.children[0].text, "three")

    def test_a_failed_save_keeps_the_old_file_and_leaves_nothing_behind(self):
        path = self.dir / "c.notz"
        doc = Document(Node("root", children=[H("safe")]), "B", 1, "T", path)
        doc.save()
        doc.root.children[0].runs = [Run("lost?")]
        doc.root.children[0].extra["newer"] = object()  # can't be written as JSON
        with self.assertRaises(TypeError):
            doc.save()
        self.assertEqual(os.listdir(self.dir), ["c.notz"], "no half-written temporary file")
        self.assertEqual(Document.load(path).root.children[0].text, "safe")

    def test_saving_elsewhere_moves_the_document_there(self):
        doc = Document.new("B", 1, "T", self.dir / "a.notz")
        doc.save(self.dir / "b.notz")
        self.assertEqual(doc.path, self.dir / "b.notz")
        self.assertFalse((self.dir / "a.notz").exists())

    def test_chapter_file_names(self):
        self.assertEqual(chapter_filename(3, "The Title"), "03 The Title.notz")
        self.assertEqual(chapter_filename(123, "x"), "123 x.notz")
        self.assertEqual(chapter_filename("7", "  "), "07.notz", "no title: just the number")
        self.assertEqual(chapter_filename(1, " padded "), "01 padded.notz")
        self.assertEqual(chapter_filename(3, "a/b\\c\0d"), "03 a_b_c_d.notz", "nothing that changes the path")


if __name__ == "__main__":
    unittest.main()
