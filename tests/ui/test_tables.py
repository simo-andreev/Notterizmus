"""Tables: moving between cells, adding and removing rows and columns, the header row."""
import json

from notterizmus.export import to_html
from notterizmus.guide import b, h, table
from notterizmus.layout import layout

from . import support as ui


def cells(node):
    return [["".join(run.text for run in cell) for cell in row] for row in node.data["rows"]]


class TableTest(ui.UITestCase):
    def chapter(self, rows=(("a", "b"), ("c", "d")), header=False):
        doc = ui.open_chapter([h("Intro", b("before"), table([list(r) for r in rows], header=header), b("after"))])
        self.doc = doc
        self.before, self.table, self.after = doc.root.children[0].children
        self.row = ui.row(self.table)
        return doc

    def at(self, r, c):
        """Put the cursor in a cell; returns its text view."""
        self.row.focus_cell(r, c)
        ui.wait_editor()
        return self.row.cells[(r, c)]

    def button(self, label=None, tooltip=None):
        return next(w for w in ui.walk(self.row) if isinstance(w, ui.Gtk.Button)
                    and (w.get_label() == label if label else w.get_tooltip_text() == tooltip))

    def click(self, label):
        """Click one of the table's buttons and wait for the cursor: the table rebuilds its
        cells and puts the cursor back from an idle callback."""
        self.button(label).emit("clicked")
        ui.wait_for(lambda: self.ed.cur_view is self.row.cells.get(self.row.cur), "the cursor to be back in the table")

    def current_table(self):
        return next(n for n in self.win.doc.root.walk() if n.kind == "table")

    def content(self):
        return json.dumps([c.to_json() for c in self.win.doc.root.children], ensure_ascii=False)

    def test_each_change_to_the_tables_shape_is_one_undo_step(self):
        """Rows, columns and the header row change the table inside one editor operation,
        so Ctrl+Z takes each back whole and Ctrl+Shift+Z brings it again (CR39)."""
        self.chapter()
        for label in ("+ Row", "+ Column", "− Row", "− Column", "Header row"):
            with self.subTest(label):
                self.row = ui.row(self.current_table())
                self.at(0, 0)
                before = self.content()
                if label == "Header row":
                    btn = self.row.header_btn
                    btn.set_active(not btn.get_active())
                else:
                    self.click(label)
                after = self.content()
                self.assertNotEqual(after, before)
                self.ed.undo()
                self.assertEqual(self.content(), before)
                self.ed.redo()
                self.assertEqual(self.content(), after)

    def test_tab_moves_through_the_cells_and_adds_a_row_at_the_end(self):
        self.chapter()
        cell = self.at(0, 0)
        self.assertTrue(ui.press(cell, "Tab"))
        self.assertEqual(self.row.cur, (0, 1))
        ui.press(self.row.cells[(0, 1)], "Tab")
        self.assertEqual(self.row.cur, (1, 0))
        ui.press(self.row.cells[(1, 0)], "Tab", shift=True)
        self.assertEqual(self.row.cur, (0, 1), "Shift+Tab goes back")
        self.assertTrue(ui.press(self.at(1, 1), "Tab"))
        ui.wait_for(lambda: self.row.cur == (2, 0) and self.ed.cur_view is self.row.cells.get((2, 0)),
                    "the cursor to be in the new row")
        self.assertEqual(cells(self.table), [["a", "b"], ["c", "d"], ["", ""]])
        self.assertTrue(ui.press(self.at(0, 0), "Tab", shift=True), "nothing before the first cell")
        self.assertEqual(self.row.cur, (0, 0))

    def test_enter_moves_down_a_row_and_out_of_the_table_after_the_last(self):
        self.chapter()
        self.assertTrue(ui.press(self.at(0, 1), "Return"))
        self.assertEqual(self.row.cur, (1, 1))
        self.assertTrue(ui.press(self.row.cells[(1, 1)], "Return"))
        ui.wait_editor()
        self.assertIs(self.ed.current, self.after)
        self.assertEqual(cells(self.table), [["a", "b"], ["c", "d"]], "Enter never adds a row")

    def test_enter_in_a_table_that_ends_the_chapter_starts_a_new_item(self):
        doc = ui.open_chapter([h("Intro", table([["x"]]))])
        intro = doc.root.children[0]
        row = ui.row(intro.children[0])
        row.focus_cell(0, 0)
        ui.wait_editor()
        ui.press(row.cells[(0, 0)], "Return")
        self.assertEqual([(n.kind, n.text) for n in intro.children], [("table", ""), ("bullet", "")])
        self.assertIs(self.ed.current, intro.children[1])

    def test_up_and_down_leave_the_table_at_its_edges(self):
        self.chapter()
        self.assertTrue(ui.press(self.at(1, 0), "Up"))
        self.assertEqual(self.row.cur, (0, 0))
        self.assertTrue(ui.press(self.row.cells[(0, 0)], "Up"))
        self.assertIs(self.ed.current, self.before)
        self.assertTrue(ui.press(ui.row(self.before).view, "Down"))
        self.assertIs(self.ed.current, self.table, "and arrows enter it again")
        self.assertEqual(self.row.cur, (0, 0))
        ui.press(self.at(1, 1), "Down")
        self.assertIs(self.ed.current, self.after)
        ui.press(ui.row(self.after).view, "Up")
        self.assertEqual((self.ed.current, self.row.cur), (self.table, (1, 0)), "from below: the last row")

    def test_the_buttons_add_and_remove_rows_and_columns_at_the_cursor(self):
        self.chapter()
        self.at(0, 0)
        self.click("+ Row")
        self.assertEqual(cells(self.table), [["a", "b"], ["", ""], ["c", "d"]])
        self.assertEqual(self.row.cur, (1, 0), "the cursor goes to the new row")
        self.at(0, 0)
        self.click("+ Column")
        self.assertEqual(cells(self.table), [["a", "", "b"], ["", "", ""], ["c", "", "d"]])
        self.assertEqual(self.row.cur, (0, 1), "and to the new column")
        self.click("− Column")
        self.at(1, 0)
        self.click("− Row")
        self.assertEqual(cells(self.table), [["a", "b"], ["c", "d"]])
        self.assertEqual(len(self.row.cells), 4)

    def test_a_column_of_a_table_that_was_ragged_in_the_file_can_be_deleted(self):
        """A table whose rows have different lengths (a hand-edited file, a newer version)
        made Delete Column raise and Tab skip cells (CR47)."""
        path = self.win.notes_root_path() / "Ragged tables" / "01 Ragged.notz"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [[[{"t": "a"}], [{"t": "b"}], [{"t": "c"}]], [[{"t": "d"}]]]
        path.write_text(json.dumps({"book": "Ragged tables", "chapter": {"number": 1, "title": "Ragged"},
                                    "content": [{"kind": "heading", "id": "h", "runs": [{"t": "Intro"}], "children": [
                                        {"kind": "table", "id": "t", "data": {"rows": rows}}]}]}), encoding="utf-8")
        self.win.open_path(path)
        ui.settle()
        self.table = self.current_table()
        self.row = ui.row(self.table)
        self.assertEqual(cells(self.table), [["a", "b", "c"], ["d", "", ""]], "read square")
        self.at(0, 2)
        self.click("− Column")
        self.assertEqual(cells(self.table), [["a", "b"], ["d", ""]])

    def test_the_last_row_and_column_cannot_be_removed(self):
        self.chapter(rows=(("only",),))
        self.at(0, 0)
        self.click("− Row")
        self.click("− Column")
        self.assertEqual(cells(self.table), [["only"]])
        self.assertEqual(len(self.row.cells), 1)

    def test_each_change_to_the_shape_is_one_undo_step(self):
        self.chapter()
        self.at(1, 1)
        self.click("+ Row")      # the cursor is now at the start of the new row
        self.click("+ Column")   # so the column goes in after the first
        self.assertEqual(cells(self.table), [["a", "", "b"], ["c", "", "d"], ["", "", ""]])
        ui.press(self.row.cells[(0, 0)], "z", ctrl=True)
        self.assertEqual(cells(self.current_table()), [["a", "b"], ["c", "d"], ["", ""]])
        ui.press(ui.row(self.current_table()).cells[(0, 0)], "z", ctrl=True)
        self.assertEqual(cells(self.current_table()), [["a", "b"], ["c", "d"]])
        self.assertEqual(len(ui.row(self.current_table()).cells), 4, "the cells on screen follow")

    def test_typing_in_a_cell_is_saved_in_the_table_and_can_be_undone(self):
        self.chapter()
        cell = self.at(1, 0)
        ui.type_text(cell, "!")
        self.assertEqual(cells(self.table), [["a", "b"], ["c!", "d"]])
        ui.press(cell, "z", ctrl=True)
        self.assertEqual(cells(self.current_table()), [["a", "b"], ["c", "d"]])
        self.assertEqual(ui.row(self.current_table()).cells[(1, 0)].get_plain(), "c")

    def test_ctrl_b_in_a_cell_makes_what_is_typed_next_bold(self):
        self.chapter(rows=(("", "x"),))
        cell = self.at(0, 0)
        self.assertTrue(ui.press(cell, "b", ctrl=True))
        ui.type_text(cell, "key")
        self.assertEqual([(run.text, run.bold) for run in self.table.data["rows"][0][0]], [("key", True)])

    def test_the_header_row_switch(self):
        self.chapter()
        self.assertFalse(self.row.header_btn.get_active())
        self.row.header_btn.set_active(True)
        ui.wait_editor()
        self.assertTrue(self.table.data["header"])
        self.assertTrue(self.row.cells[(0, 0)].has_css_class("header-cell"))
        self.assertFalse(self.row.cells[(1, 0)].has_css_class("header-cell"))
        self.assertIn("<th>", to_html(layout(self.doc.root, self.win.rules)))
        ui.press(self.row.cells[(0, 0)], "z", ctrl=True)
        again = self.current_table()
        self.assertFalse(again.data["header"])
        self.assertFalse(ui.row(again).header_btn.get_active(), "the switch follows an undo")
        self.assertFalse(ui.row(again).cells[(0, 0)].has_css_class("header-cell"))

    def test_the_trash_button_deletes_the_table_and_undo_restores_it(self):
        self.chapter()
        self.button(tooltip="Delete table").emit("clicked")
        ui.wait_editor()
        intro = self.win.doc.root.children[0]
        self.assertEqual([n.kind for n in intro.children], ["bullet", "bullet"])
        self.assertIs(self.ed.current, intro.children[0])
        ui.press(self.ed.cur_view, "z", ctrl=True)
        self.assertEqual(cells(self.current_table()), [["a", "b"], ["c", "d"]])

    def test_ctrl_t_puts_a_table_after_a_bullet_and_before_the_numbered_children_of_a_heading(self):
        doc = ui.open_chapter([h("Intro", b("note"), h("Sub"))])
        intro = doc.root.children[0]
        self.assertTrue(ui.press(ui.focus(intro).view, "t", ctrl=True))
        self.assertEqual([n.kind for n in intro.children], ["bullet", "table", "heading"])
        self.assertEqual(cells(intro.children[1]), [["", ""], ["", ""]])
        ui.press(ui.focus(intro.children[0]).view, "t", ctrl=True)
        self.assertEqual([n.kind for n in intro.children], ["bullet", "table", "table", "heading"])
