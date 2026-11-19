"""Rows the editor no longer shows are freed (R29c). A handler on a widget inside a row
that holds the row, or a text view, makes a cycle that runs through GTK, where Python's
garbage collector can't see it, and the row with all it holds (a drawing's picture is
tens of MB) would stay until the app quits."""
import gc

from notterizmus import drawing
from notterizmus.guide import b, h, table
from notterizmus.model import Node

from . import support as ui
from .test_drawings import PNG, scene
from .test_unknown import mindmap


class Watch:
    """Notes when the objects it is given are freed."""

    def __init__(self):
        self.names, self.freed, self._handles = [], set(), []  # a weak ref lasts as long as its handle

    def add(self, name, obj):
        self.names.append(name)
        self._handles.append(obj.weak_ref(lambda: self.freed.add(name)))

    def alive(self):
        gc.collect()
        return [n for n in self.names if n not in self.freed]

    def wait(self, test):
        ui.pump_until(lambda: not self.alive())
        test.assertEqual(self.alive(), [], "still alive")


def watch_rows(nodes):
    """A Watch on the rows of these nodes and on their text views."""
    w = Watch()
    for node in nodes:
        r = ui.row(node)
        w.add(f"{type(r).__name__} {node.kind}", r)
        for i, v in enumerate(r.views()):
            w.add(f"{type(r).__name__} {node.kind}, view {i}", v)
    return w


def watch_cells(table_row):
    """A Watch on a table's cell views (a helper, so no local variable keeps one alive)."""
    w = Watch()
    for (r, c), v in table_row.cells.items():
        w.add(f"cell {r},{c}", v)
    return w


class FreedRowsTest(ui.UITestCase):
    def open_every_kind(self):
        data = scene("freed")
        drawing.store_preview(data, PNG)  # shown from the cache: nothing to render
        doc = ui.open_chapter([h("Intro", b("text"), table([["a", "b"], ["c", "d"]]),
                                 Node("drawing", data=data), mindmap())])
        intro = doc.root.children[0]
        return [intro, *intro.children]

    def test_opening_another_chapter_frees_the_rows_of_the_one_before(self):
        nodes = self.open_every_kind()
        r = ui.focus(nodes[1])
        ui.type_text(r.view, " typed")
        del r
        w = watch_rows(nodes)
        ui.open_chapter([h("Other", b("x"))])
        w.wait(self)

    def test_a_deleted_item_frees_its_row(self):
        doc = ui.open_chapter([h("Intro", b("keep"), b("delete me"))])
        gone = doc.root.children[0].children[1]
        w = watch_rows([gone])
        ui.focus(gone)
        self.win.editor.delete_items([gone])
        ui.wait_editor()
        w.wait(self)

    def test_a_table_frees_the_cells_it_rebuilds(self):
        doc = ui.open_chapter([h("Intro", table([["a", "b"], ["c", "d"]]))])
        tr = ui.row(doc.root.children[0].children[0])
        w = watch_cells(tr)
        tr.focus_cell(1, 1)
        ui.pump_until(lambda: tr.cur == (1, 1))
        tr.add_row()
        ui.wait_editor()
        w.wait(self)


class FreedSidebarRowsTest(ui.UITestCase):
    def test_the_chapter_list_frees_its_rows_when_it_is_rebuilt(self):
        """Each rebuild of the chapter list (a chapter switch, folding a book, a changed
        folder) leaked the chapter rows it showed: their drag handlers held them, the same
        cycle through GTK the editor's rows had (CR18)."""
        if not self.win.split.get_show_sidebar():
            self.win.lookup_action("sidebar").activate(None)
            self.addCleanup(self.win.lookup_action("sidebar").activate, None)
        ui.open_chapter([h("One")], title="One", book="Freed list")
        ui.open_chapter([h("Two")], title="Two", book="Freed list")
        sidebar = self.win.sidebar
        sidebar.expanded.add("Freed list")
        sidebar._rebuild()
        w = Watch()
        for i, row in enumerate(r for r in sidebar.rows() if r._path is not None):
            w.add(f"chapter row {i}", row)
        self.assertGreaterEqual(len(w.names), 2)
        row = None  # (no local name may keep the last one)
        sidebar._rebuild()
        w.wait(self)
