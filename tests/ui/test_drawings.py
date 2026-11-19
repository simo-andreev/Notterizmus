"""Drawing blocks in the editor: adding, editing, the picture, undo, copying.

The drawing window itself (Excalidraw in a web view) is replaced here by a stand-in that
records what it was opened on and lets the test answer as the user would; the real one
is tried at the end, where WebKitGTK is installed and works on the test display."""
import base64
import copy
import gc
import json
import os
import unittest
from pathlib import Path

from notterizmus import drawing
from notterizmus.guide import b, h
from notterizmus.model import Document, Node

from ..test_drawing import BR, editor_copy, editor_drawing, editor_paragraph, editor_text
from . import support as ui

# A 2×2 white PNG.
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAADklEQVR4nGP4DwYMEAoAU7oL9ZisIGcAAAAASUVORK5CYII=")


def png(width, height):
    """A white PNG of this size in pixels."""
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

    rows = (b"\x00" + b"\xff" * (3 * width)) * height
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def png_size(data):
    """(width, height) of a PNG, from its header."""
    import struct
    return struct.unpack(">II", data[16:24])


def scene(text="one", x=10):
    return {"elements": [{"type": "rectangle", "id": "r1", "x": x, "y": 10, "width": 200, "height": 80},
                         {"type": "text", "id": "t1", "x": 30, "y": 35, "width": 160, "height": 25, "fontSize": 20,
                          "text": text}],
            "appState": {"viewBackgroundColor": "#ffffff"}, "files": {}}


def block(data=None):
    return Node("drawing", data=copy.deepcopy(data or scene()))


class _FakeWindow:
    """Stands in for the drawing window: open until Done, or until the test ends."""

    def __init__(self):
        self.open = True
        self.presented = 0

    def get_visible(self):
        return self.open

    def present(self):
        self.presented += 1


class _FakeWeb:
    """Stands in for notterizmus.ui.drawing_web: edit() and render() only record."""

    def __init__(self):
        self.edits = []    # (data, done: what the window's Done does)
        self.renders = []  # (data, done)
        self.windows = []
        self.can_edit = True

    def edit(self, _parent, data, on_done):
        if not self.can_edit:
            return None
        win = _FakeWindow()

        def done(new):
            win.open = False
            on_done(new)
        self.windows.append(win)
        self.edits.append((copy.deepcopy(data), done))
        return win

    def close_all(self):
        for win in self.windows:
            win.open = False

    def render(self, data, done):
        self.renders.append((copy.deepcopy(data), done))


class DrawingTestCase(ui.UITestCase):
    def setUp(self):
        super().setUp()
        from notterizmus.ui import drawing_web
        self.web = _FakeWeb()
        real = drawing_web.edit, drawing_web.render
        drawing_web.edit, drawing_web.render = self.web.edit, self.web.render
        self.addCleanup(lambda: (setattr(drawing_web, "edit", real[0]), setattr(drawing_web, "render", real[1])))
        self.addCleanup(self.web.close_all)

    def kinds(self):
        return [c.kind for c in self.win.doc.root.children[0].children]

    def drawings(self):
        return [n for n in self.win.doc.root.walk() if n.kind == "drawing"]


class AddDrawingTest(DrawingTestCase):
    def open(self):
        doc = ui.open_chapter([h("Intro", b("before"), b("after"))])
        intro = doc.root.children[0]
        return doc, intro.children[0], intro.children[1]

    def test_ctrl_d_opens_an_empty_drawing_and_done_adds_it_after_the_item(self):
        _doc, before, _after = self.open()
        self.assertTrue(ui.press(ui.focus(before).view, "d", ctrl=True))
        self.assertEqual(len(self.web.edits), 1)
        data, done = self.web.edits[0]
        self.assertTrue(drawing.is_empty(data))
        self.assertEqual(self.kinds(), ["bullet", "bullet"], "nothing is added before Done")
        done(scene())
        ui.settle()
        self.assertEqual(self.kinds(), ["bullet", "drawing", "bullet"])
        self.assertEqual(drawing.scene(self.drawings()[0].data), scene())
        from notterizmus.ui.rows import DrawingRow
        self.assertIsInstance(ui.row(self.drawings()[0]), DrawingRow)

    def test_a_file_opened_while_the_drawing_window_is_open_waits(self):
        """A chapter opened from Files while the drawing window was open replaced the one
        the drawing came from, and Done then put the drawing into the other chapter (CR19)."""
        doc, before, _after = self.open()
        ui.press(ui.focus(before).view, "d", ctrl=True)
        other = ui.scratch() / "elsewhere-for-a-drawing.notz"
        Document.new("Elsewhere", 1, "Other", other).save()
        ui.app().do_open([ui.Gio.File.new_for_path(str(other))], 1, "")
        self.assertEqual(Path(self.win.doc.path), Path(doc.path), "the chapter stays")
        self.assertEqual(self.web.windows[0].presented, 1, "the drawing window comes to the front")
        self.web.edits[0][1](scene())
        ui.settle()
        self.assertEqual(self.kinds(), ["bullet", "drawing", "bullet"])

    def test_done_never_puts_a_drawing_into_another_chapter(self):
        _doc, before, _after = self.open()
        ui.press(ui.focus(before).view, "d", ctrl=True)
        other = ui.open_chapter([h("Other", b("text"))], title="Other")  # however it came to be open
        self.web.edits[0][1](scene())
        ui.settle()
        self.assertEqual([n.kind for n in other.root.walk() if n.kind == "drawing"], [])

    def test_the_cursor_stays_in_the_item_it_was_added_from(self):
        _doc, before, _after = self.open()
        view = ui.focus(before).view
        ui.press(view, "d", ctrl=True)
        self.web.edits[0][1](scene())
        ui.settle()
        ui.wait_editor()
        self.assertIs(self.ed.current, before)
        ui.type_text(view, "!")
        self.assertEqual(before.text, "before!")

    def test_a_drawing_left_empty_or_cancelled_adds_nothing(self):
        _doc, before, _after = self.open()
        ui.press(ui.focus(before).view, "d", ctrl=True)
        self.web.edits[0][1](drawing.new_data())  # Done on an empty canvas
        ui.press(ui.focus(before).view, "d", ctrl=True)  # ... and one never answered: Cancel
        ui.settle()
        self.assertEqual(self.kinds(), ["bullet", "bullet"])

    def test_adding_is_one_undo_step(self):
        _doc, before, _after = self.open()
        view = ui.focus(before).view
        ui.press(view, "d", ctrl=True)
        self.web.edits[0][1](scene())
        ui.settle()
        ui.press(view, "z", ctrl=True)
        self.assertEqual(self.kinds(), ["bullet", "bullet"])
        ui.press(self.ed.cur_view, "z", ctrl=True, shift=True)
        self.assertEqual(self.kinds(), ["bullet", "drawing", "bullet"])
        self.assertEqual(drawing.scene(self.drawings()[0].data), scene())

    def test_the_menu_command_and_the_add_menu_open_it_too(self):
        _doc, before, _after = self.open()
        r = ui.focus(before)
        self.win.lookup_action("insert-drawing").activate(None)
        ui.pump_until(lambda: len(self.web.edits) == 1)
        self.assertEqual(len(self.web.edits), 1)
        self.ed.show_add_menu(r, r.view)
        ui.pump_until(ui.open_popovers)
        labels = [label for _n, label, _row in ui.menu_choices(ui.open_popovers()[0])]
        self.assertIn("Drawing", labels)

    def test_without_webkit_it_says_what_is_missing(self):
        _doc, before, _after = self.open()
        self.web.can_edit = False
        said = []
        handler = self.ed.connect("message", lambda _e, msg: said.append(msg))
        self.addCleanup(self.ed.disconnect, handler)
        ui.press(ui.focus(before).view, "d", ctrl=True)
        self.assertEqual(len(said), 1)
        self.assertIn("gir1.2-webkit-6.0", said[0])
        self.assertEqual(self.kinds(), ["bullet", "bullet"])


class DrawingRowTest(DrawingTestCase):
    def open(self, data=None, cached=True):
        data = data or scene()
        if cached:
            drawing.store_preview(data, PNG)
        else:
            drawing.preview_path(data).unlink(missing_ok=True)
        doc = ui.open_chapter([h("Intro", b("before"), block(data), b("after"))])
        intro = doc.root.children[0]
        return doc, intro.children[0], intro.children[1], intro.children[2]

    def button(self, node, label=None, tooltip=None):
        return next(w for w in ui.walk(ui.row(node)) if isinstance(w, ui.Gtk.Button)
                    and (w.get_label() == label if label else w.get_tooltip_text() == tooltip))

    def test_it_shows_the_cached_picture_at_the_drawings_size(self):
        _doc, _before, node, _after = self.open()
        r = ui.row(node)
        self.assertTrue(r.picture.get_visible())
        self.assertFalse(r.note.get_visible())
        self.assertEqual(self.web.renders, [], "a cached picture isn't made again")
        paintable = r.picture.get_paintable()
        self.assertEqual((paintable.get_intrinsic_width(), paintable.get_intrinsic_height()), (1, 1))

    def test_the_picture_takes_its_room_in_the_outline(self):
        """It once had no height at all: only the buttons above it showed."""
        for name, (w, h_) in {"tall": (130, 190), "wide": (400, 90)}.items():
            data = scene(name)
            drawing.store_preview(data, png(w * drawing.PREVIEW_SCALE, h_ * drawing.PREVIEW_SCALE))
            doc = ui.open_chapter([h("Intro", b("before")), h("Design", block(data), h("Parts", b("after")))])
            node = doc.root.children[1].children[0]
            pic = ui.row(node).picture
            ui.settle()
            self.assertEqual((pic.get_width(), pic.get_height()), (w, h_), name)
            # ... and keeps it when the outline is short of room (a long chapter)
            self.assertGreaterEqual(pic.measure(ui.Gtk.Orientation.VERTICAL, -1).minimum, h_, name)

    def test_a_very_large_drawing_is_shown_smaller(self):
        data = scene("huge")
        drawing.store_preview(data, png(3000, 1000))
        doc = ui.open_chapter([h("Intro", block(data), b("after"))])
        pic = ui.row(doc.root.children[0].children[0]).picture
        ui.settle()
        self.assertLessEqual(pic.get_width(), drawing.PREVIEW_MAX[0])
        paintable = pic.get_paintable()
        self.assertEqual((paintable.get_intrinsic_width(), paintable.get_intrinsic_height()),
                         (drawing.PREVIEW_MAX[0], round(drawing.PREVIEW_MAX[0] / 3)))
        self.assertEqual(pic.get_height(), round(drawing.PREVIEW_MAX[0] / 3))

    def test_a_missing_picture_is_made_from_the_scene(self):
        _doc, _before, node, _after = self.open(scene("uncached"), cached=False)
        r = ui.row(node)
        self.assertFalse(r.picture.get_visible())
        self.assertEqual(len(self.web.renders), 1)
        data, done = self.web.renders[0]
        self.assertEqual(drawing.scene(data), scene("uncached"))
        drawing.store_preview(data, PNG)  # what the real renderer does before answering
        done(PNG)
        self.assertTrue(r.picture.get_visible())
        self.assertFalse(r.note.get_visible())

    def test_a_picture_that_cannot_be_made_leaves_a_note(self):
        _doc, _before, node, _after = self.open(scene("unrenderable"), cached=False)
        r = ui.row(node)
        self.web.renders[0][1](None)
        self.assertFalse(r.picture.get_visible())
        self.assertIn("2 elements", r.note.get_text())

    def test_the_edit_button_opens_its_scene_and_done_replaces_it(self):
        _doc, _before, node, _after = self.open()
        self.button(node, label="Edit Drawing").emit("clicked")
        self.assertEqual(len(self.web.edits), 1)
        data, done = self.web.edits[0]
        self.assertEqual(drawing.scene(data), scene())
        new = scene("two", x=50)
        drawing.store_preview(new, PNG)
        done(copy.deepcopy(new))
        ui.settle()
        self.assertEqual(drawing.scene(self.drawings()[0].data), new)
        ui.wait_for(lambda: json.loads(self.win.doc.path.read_text(encoding="utf-8"))
                    ["content"][0]["children"][1]["data"]["elements"][1]["text"] == "two", "the autosave")

    def test_an_edit_can_be_undone_and_redone(self):
        _doc, before, node, _after = self.open()
        view = ui.focus(before).view
        self.button(node, label="Edit Drawing").emit("clicked")
        new = scene("two")
        drawing.store_preview(new, PNG)
        self.web.edits[0][1](copy.deepcopy(new))
        ui.settle()
        ui.press(view, "z", ctrl=True)
        self.assertEqual(drawing.scene(self.drawings()[0].data), scene())
        self.assertEqual(ui.row(self.drawings()[0])._key, drawing.preview_key(scene()))
        ui.press(self.ed.cur_view, "z", ctrl=True, shift=True)
        self.assertEqual(drawing.scene(self.drawings()[0].data), new)
        self.assertEqual(ui.row(self.drawings()[0])._key, drawing.preview_key(new))

    def test_done_without_changes_is_not_an_undo_step(self):
        _doc, before, node, _after = self.open()
        view = ui.focus(before).view
        ui.type_text(view, "!")
        self.button(node, label="Edit Drawing").emit("clicked")
        self.web.edits[0][1](scene())
        ui.settle()
        ui.press(view, "z", ctrl=True)
        self.assertEqual(self.win.doc.root.children[0].children[0].text, "before", "one undo takes the typing back")

    def test_undo_steps_share_the_scene_instead_of_copying_it(self):
        """Every undo step held the whole chapter as text, scenes and all: up to 8 MB a step
        with pasted pictures, at up to 500 steps (R29d)."""
        _doc, before, node, _after = self.open()
        data = node.data
        view = ui.focus(before).view
        for word in (" one", " two", " three"):
            ui.type_text(view, word)
        steps = [*self.ed._undo, self.ed._cur]
        self.assertGreaterEqual(len(steps), 4)
        for content, _fid, _off, scenes in steps:
            self.assertNotIn('"elements"', content)
            self.assertEqual(len(scenes), 1)
            self.assertIs(scenes[0], data)
        for _ in range(3):
            ui.press(self.ed.cur_view or view, "z", ctrl=True)
        self.assertEqual(self.win.doc.root.children[0].children[0].text, "before")
        self.assertIs(self.drawings()[0].data, data, "the undone chapter has the same scene back")
        self.assertEqual(drawing.scene(data), scene())

    def test_an_earlier_version_brings_its_drawing_back_and_undo_returns(self):
        _doc, before, _node, _after = self.open()
        view = ui.focus(before).view
        earlier = scene("earlier")
        drawing.store_preview(earlier, PNG)
        self.ed.replace_content(Node("root", children=[h("Intro", b("before"), block(earlier), b("after"))]))
        ui.settle()
        self.assertEqual(drawing.scene(self.drawings()[0].data), earlier)
        ui.press(self.ed.cur_view or view, "z", ctrl=True)
        self.assertEqual(drawing.scene(self.drawings()[0].data), scene())
        ui.press(self.ed.cur_view or view, "z", ctrl=True, shift=True)
        self.assertEqual(drawing.scene(self.drawings()[0].data), earlier)

    def test_erasing_everything_removes_the_block(self):
        _doc, before, node, _after = self.open()
        ui.focus(before)
        self.button(node, label="Edit Drawing").emit("clicked")
        self.web.edits[0][1](drawing.new_data())
        ui.settle()
        self.assertEqual(self.kinds(), ["bullet", "bullet"])

    def test_the_item_menu_edits_and_deletes(self):
        _doc, before, node, _after = self.open()
        ui.focus(before)
        self.ed.show_item_menu(ui.row(node))
        ui.pump_until(ui.open_popovers)
        choices = {label: row for _n, label, row in ui.menu_choices(ui.open_popovers()[0])}
        self.assertEqual(list(choices), ["Edit Drawing", "Copy Drawing", "Delete Drawing"])
        choices["Edit Drawing"].activate()
        ui.pump_until(lambda: self.web.edits)
        self.assertEqual(drawing.scene(self.web.edits[0][0]), scene())

    def test_the_trash_button_deletes_it_and_undo_brings_it_back(self):
        _doc, before, node, _after = self.open()
        view = ui.focus(before).view
        self.button(node, tooltip="Delete drawing").emit("clicked")
        ui.settle()
        self.assertEqual(self.kinds(), ["bullet", "bullet"])
        ui.press(self.ed.cur_view or view, "z", ctrl=True)
        self.assertEqual(self.kinds(), ["bullet", "drawing", "bullet"])
        self.assertEqual(drawing.scene(self.drawings()[0].data), scene())

    def test_the_cursor_skips_it(self):
        _doc, before, _node, after = self.open()
        self.assertTrue(ui.press(ui.focus(before).view, "Down"))
        self.assertIs(self.ed.current, after)
        self.assertTrue(ui.press(ui.row(after).view, "Up"))
        self.assertIs(self.ed.current, before)

    def test_copy_for_topcoding_carries_the_scene(self):
        self.open()
        self.win.lookup_action("copy").activate(None)
        from notterizmus import lexical
        cb = self.win.get_clipboard()
        ui.wait_for(lambda: cb.get_formats().contain_mime_type(lexical.CHROME_CUSTOM_MIME), "the copy")
        self.assertTrue(cb.get_formats().contain_mime_type(lexical.FIREFOX_CUSTOM_MIME))
        self.assertIn("before", ui.clipboard("text/html"))
        self.assertIn("[Drawing]", ui.clipboard("text/plain"))

    def test_a_chapter_without_drawings_is_copied_as_before(self):
        from notterizmus import lexical
        ui.open_chapter([h("Intro", b("before"))])
        self.win.lookup_action("copy").activate(None)
        self.assertIn("before", ui.clipboard("text/html"))
        formats = self.win.get_clipboard().get_formats()
        self.assertFalse(formats.contain_mime_type(lexical.CHROME_CUSTOM_MIME))
        self.assertFalse(formats.contain_mime_type(lexical.FIREFOX_CUSTOM_MIME))

    def copied(self):
        said = []
        handler = self.ed.connect("message", lambda _e, msg: said.append(msg))
        self.addCleanup(self.ed.disconnect, handler)
        return said

    def test_the_copy_button_copies_the_drawing_alone(self):
        from notterizmus import lexical
        _doc, before, node, _after = self.open()
        ui.focus(before)
        said = self.copied()
        self.button(node, label="Copy").emit("clicked")
        self.assertEqual(said, ["Copied 1 item"])
        self.assertEqual(self.ed.sel, [node])
        cb = self.win.get_clipboard()
        ui.wait_for(lambda: cb.get_formats().contain_mime_type(lexical.CHROME_CUSTOM_MIME), "the copy")
        self.assertNotIn("before", ui.clipboard("text/html"))
        self.assertEqual(ui.clipboard("text/plain").strip(), "[Drawing]")
        nodes = json.loads(ui.clipboard("application/x-notterizmus-nodes+json"))["nodes"]
        self.assertEqual([n["kind"] for n in nodes], ["drawing"])

    def test_a_click_selects_it_and_ctrl_c_copies_only_it(self):
        _doc, before, node, _after = self.open()
        view = ui.focus(before).view
        ui.row(node)._clicked(None, 1, 0, 0)
        self.assertEqual(self.ed.sel, [node])
        self.assertTrue(ui.row(node).has_css_class("node-selected"))
        said = self.copied()
        self.assertTrue(ui.press(view, "c", ctrl=True))
        self.assertEqual(said, ["Copied 1 item"])
        self.assertEqual(self.web.edits, [], "a single click doesn't open the drawing")

    def test_a_double_click_opens_it(self):
        _doc, _before, node, _after = self.open()
        ui.row(node)._clicked(None, 2, 0, 0)
        self.assertEqual(len(self.web.edits), 1)

    def test_copied_items_paste_back_with_their_drawing(self):
        doc, _before, node, after = self.open()
        self.ed.sel = [node]
        self.ed.copy_items()
        self.ed.clear_selection()
        r = ui.focus(after)
        self.ed.paste(r, r.view)
        ui.wait_for(lambda: len(self.drawings()) == 2, "the pasted drawing")
        first, second = self.drawings()
        self.assertEqual(drawing.scene(second.data), drawing.scene(first.data))
        self.assertNotEqual(first.id, second.id)


class PasteFromTopCodingTest(DrawingTestCase):
    """Ctrl+V of a copy from TopCoding's editor: its drawings come only in the editor's
    own JSON, which the browser packs into its custom clipboard data."""

    def setUp(self):
        super().setUp()
        self.toasts = []
        self.win.toast = lambda msg, button=None, cb=None: self.toasts.append((msg, button, cb))
        self.addCleanup(lambda: self.win.__dict__.pop("toast", None))

    def put(self, nodes, html, browser="chrome"):
        """Put a copy from TopCoding's editor on the clipboard, as the browser leaves it."""
        mime, data = editor_copy(nodes, browser)
        formats = [(mime, data), ("text/html", html.encode("utf-8")),
                   ("text/plain;charset=utf-8", b"[from the browser]")]
        self.win.get_clipboard().set_content(ui.Gdk.ContentProvider.new_union(
            [ui.Gdk.ContentProvider.new_for_bytes(m, ui.GLib.Bytes.new(d)) for m, d in formats]))
        ui.pump(0.05)

    def paste(self, row, until, what="the paste"):
        row.view.emit("paste-clipboard")
        ui.wait_for(until, what)
        ui.settle()
        ui.wait_editor()

    def test_a_copy_with_a_drawing_builds_the_outline_with_the_drawing_in_place(self):
        doc = ui.open_chapter([h("")])
        self.put([editor_paragraph(editor_text("Ⅰ) Intro"), BR, editor_text("├ • before")),
                  editor_drawing(scene()),
                  editor_paragraph(editor_text("└ • after"))],
                 html="<p>Ⅰ) Intro<br>├ • before<br>└ • after</p>")
        self.paste(ui.focus(doc.root.children[0], 0), lambda: self.drawings())
        intro, = self.win.doc.root.children
        self.assertEqual(intro.text, "Intro")
        self.assertEqual([(n.kind, n.text) for n in intro.children], [("bullet", "before"), ("drawing", ""),
                                                                      ("bullet", "after")])
        self.assertEqual(drawing.scene(intro.children[1].data), scene())
        from notterizmus.ui.rows import DrawingRow
        self.assertIsInstance(ui.row(intro.children[1]), DrawingRow)

    def test_a_drawing_copied_by_itself_goes_after_the_item(self):
        doc = ui.open_chapter([h("Intro", b("first"), b("second"))])
        first = doc.root.children[0].children[0]
        self.put([editor_drawing(scene())], html="<p></p>", browser="firefox")
        self.paste(ui.focus(first, 2), lambda: self.drawings())
        self.assertEqual(self.kinds(), ["bullet", "drawing", "bullet"])
        self.assertEqual(first.text, "first")
        self.assertIs(self.ed.current, first, "the cursor stays in the item")
        self.assertEqual(self.toasts, [])
        ui.press(self.ed.cur_view, "z", ctrl=True)
        self.assertEqual(self.kinds(), ["bullet", "bullet"], "one undo step")

    def test_a_copy_without_a_drawing_is_pasted_from_its_html(self):
        doc = ui.open_chapter([h("Intro", b(""))])
        item = doc.root.children[0].children[0]
        self.put([editor_paragraph(editor_text("from the JSON"))], html="<p>from the <b>HTML</b></p>")
        self.paste(ui.focus(item, 0), lambda: item.text)
        self.assertEqual([(r.text, r.bold) for r in item.runs], [("from the ", False), ("HTML", True)])

    def test_copy_for_topcoding_pastes_back_with_its_drawing(self):
        doc = ui.open_chapter([h("Intro", b("before"), block(), b("after")), h("")])
        self.win.lookup_action("copy").activate(None)
        from notterizmus import lexical
        cb = self.win.get_clipboard()
        ui.wait_for(lambda: cb.get_formats().contain_mime_type(lexical.CHROME_CUSTOM_MIME), "the copy")
        self.paste(ui.focus(doc.root.children[1], 0), lambda: len(self.drawings()) == 2)
        pasted = self.win.doc.root.children[1]
        self.assertEqual((pasted.text, [n.kind for n in pasted.children]), ("Intro", ["bullet", "drawing", "bullet"]))
        self.assertEqual(drawing.scene(pasted.children[1].data), scene())


class EvenSizeTest(ui.UITestCase):
    """WebKit 2.52 drew a canvas over 2048 pixels wide half a pixel off when its width was
    odd, which blurred the drawing (R29g), so the web view always gets an even size."""

    def test_the_web_view_gets_an_even_width_and_height(self):
        from gi.repository import Gtk
        from notterizmus.ui import drawing_web
        rooms = []
        for width, height in ((901, 601), (900, 600)):
            child = Gtk.DrawingArea()
            win = Gtk.Window(default_width=width, default_height=height, child=drawing_web._even_size(child))
            self.addCleanup(win.destroy)
            win.present()
            ui.wait_for(lambda: child.get_width() > 0, "the window to be laid out")
            room = child.get_parent()
            self.assertEqual((child.get_width(), child.get_height()),
                             (room.get_width() - room.get_width() % 2, room.get_height() - room.get_height() % 2))
            self.assertEqual((child.get_width() % 2, child.get_height() % 2), (0, 0))
            rooms.append((room.get_width() % 2, room.get_height() % 2))
        self.assertIn((1, 1), rooms, "no odd room was tried")


class RealDrawingWindowTest(ui.UITestCase):
    """Excalidraw itself, where it can run: opens a scene, hands it back with a picture."""

    def setUp(self):
        super().setUp()
        from notterizmus.ui import drawing_web
        if not drawing_web.available():
            self.skipTest("WebKitGTK (gir1.2-webkit-6.0) isn't installed")
        if os.environ.get("NOTTERIZMUS_UI_WEBKIT") != "1":
            self.skipTest("set NOTTERIZMUS_UI_WEBKIT=1 to run Excalidraw itself (slow; needs a working web view)")
        self.web = drawing_web
        self.addCleanup(drawing_web.shutdown)

    def test_a_preview_is_rendered_without_a_window(self):
        data = scene("rendered off screen")
        drawing.preview_path(data).unlink(missing_ok=True)
        got = []
        self.web.render(data, got.append)
        ui.wait_for(lambda: got, "the preview", timeout=60)
        self.assertTrue(got[0] and got[0].startswith(b"\x89PNG"), "no PNG came back")
        self.assertEqual(drawing.preview_path(data).read_bytes(), got[0])

    def test_a_closed_window_ends_its_web_process_and_is_freed(self):
        self.web.shutdown()  # the preview page has its own process
        ui.wait_for(lambda: ui.web_processes() == 0, "the preview page's process to end")
        freed, refs = [], []  # a weak ref lasts only as long as its handle
        for how in ("cancel", "done"):
            win = self.web.edit(self.win, scene(how), lambda _data: None)
            refs.append(win.weak_ref(lambda how=how: freed.append(how)))
            ui.wait_for(lambda: win.done_btn.get_sensitive(), "Excalidraw to start", timeout=60)
            self.assertEqual(ui.web_processes(), 1)
            if how == "cancel":
                win.close()  # nothing was changed, so it closes without asking
            else:
                win.finish()
            ui.wait_for(lambda: not win.get_visible(), f"the window to close ({how})", timeout=60)
            del win
            ui.wait_for(lambda: ui.web_processes() == 0, f"the web process to end ({how})")
            # Freed by Python's garbage collector: its own handlers on itself are a cycle too.
            ui.wait_for(lambda: (gc.collect(), how in freed)[1], f"the window to be freed ({how})")

    def test_done_hands_back_the_scene_and_stores_its_picture(self):
        data = scene("edited in Excalidraw")
        got = []
        win = self.web.edit(self.win, data, got.append)
        self.addCleanup(lambda: win.destroy())
        ui.wait_for(lambda: win.done_btn.get_sensitive(), "Excalidraw to start", timeout=60)
        win.finish()
        ui.wait_for(lambda: got, "the scene", timeout=60)
        kept = got[0]
        self.assertEqual([e["type"] for e in kept["elements"]], ["rectangle", "text"])
        self.assertEqual(kept["elements"][1]["text"], "edited in Excalidraw")
        self.assertTrue(drawing.preview_path(kept).read_bytes().startswith(b"\x89PNG"))
        ui.wait_for(lambda: not win.get_visible(), "the drawing window to close")

    def page(self, win, body):
        """Run JavaScript in the drawing window's page; its result as text."""
        got = []
        self.web._call(win.view, self.web._JS_READY + body, lambda text, error: got.append((text, error)))
        ui.wait_for(lambda: got, "the page's answer", timeout=30)
        self.assertIsNone(got[0][1])
        return got[0][0]

    def test_cancel_notices_every_change(self):
        """changed() summed the versions of the elements still there: deleting one took its
        version out, so edits elsewhere could bring the sum back, and Cancel then discarded
        without asking. A new background alone was never noticed (CR17)."""
        edits = {
            "a deletion and an edit": """
                const [first, second] = JSON.parse(window.ntz.elements());
                window.ntz.updateScene({elements: [{...first, isDeleted: true, version: first.version + 1},
                                                   {...second, version: second.version + first.version}]});""",
            "a new background": 'window.ntz.updateScene({appState: {viewBackgroundColor: "#ffeeaa"}});',
        }
        for what, js in edits.items():
            win = self.web.edit(self.win, scene(what), lambda _data: None)
            self.addCleanup(win.destroy)
            ui.wait_for(lambda: win.done_btn.get_sensitive(), "Excalidraw to start", timeout=60)
            self.assertEqual(self.page(win, "return window.ntz.changed();"), "false", what)
            self.page(win, js)
            self.assertEqual(self.page(win, "return window.ntz.changed();"), "true", what)
            win._closing = True  # no question: nothing here is to be kept
            win.close()
            ui.wait_for(lambda: not win.get_visible(), "the drawing window to close")

    def test_the_page_offers_nothing_it_cannot_do(self):
        """Mermaid to Excalidraw needs a library the page leaves out (mermaid-stub.js), Web
        Embed shows web pages the page may not load, and the shape library keeps its items in
        browser storage the page doesn't have (CR29)."""
        win = self.web.edit(self.win, scene("menus"), lambda _data: None)
        self.addCleanup(win.destroy)
        ui.wait_for(lambda: win.done_btn.get_sensitive(), "Excalidraw to start", timeout=60)
        shown = json.loads(self.page(win, """
            const visible = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
            const more = document.querySelector(".App-toolbar__extra-tools-trigger");
            more.click();
            await new Promise((r) => setTimeout(r, 300));
            const items = [...document.querySelectorAll(".dropdown-menu-item")].filter(visible)
                .map((e) => e.textContent.trim());
            const library = [...document.querySelectorAll("[class*=sidebar-trigger], button, label")]
                .filter((e) => visible(e) && /library/i.test(e.className + " " + e.textContent)).length;
            more.click();
            return JSON.stringify({items, library});"""))
        self.assertEqual([i for i in shown["items"] if "Mermaid" in i or "Embed" in i], [])
        self.assertTrue(any(i.startswith("Frame tool") for i in shown["items"]), "the rest of the menu stays")
        self.assertEqual(shown["library"], 0, "no way into the shape library")
        win._closing = True
        win.close()

    def test_the_page_loads_pictures_but_no_frames(self):
        """The CSP's default-src 'self' data: blob: also let frames and connections use data:
        and blob: (CR31). Pictures, which Excalidraw shows from data: and blob: addresses,
        must still load."""
        win = self.web.edit(self.win, scene("csp"), lambda _data: None)
        self.addCleanup(win.destroy)
        ui.wait_for(lambda: win.done_btn.get_sensitive(), "Excalidraw to start", timeout=60)
        got = json.loads(self.page(win, """
            const violations = [];
            document.addEventListener("securitypolicyviolation", (e) => violations.push(e.effectiveDirective));
            const png = "data:image/png;base64,""" + base64.b64encode(PNG).decode() + """";
            const image = (src) => new Promise((done) => {
              const i = new Image();
              i.onload = () => done(true);
              i.onerror = () => done(false);
              i.src = src;
            });
            const blob = URL.createObjectURL(await (await fetch(png)).blob());
            const frame = document.createElement("iframe");
            frame.src = "data:text/html,<p>embedded</p>";
            document.body.append(frame);
            await new Promise((r) => setTimeout(r, 300));
            frame.remove();
            return JSON.stringify({data: await image(png), blob: await image(blob), violations});"""))
        self.assertEqual((got["data"], got["blob"]), (True, True), "pictures load")
        self.assertIn("frame-src", got["violations"], "a frame doesn't")
        win._closing = True
        win.close()

    def test_a_preview_is_made_at_twice_the_size_it_is_shown_at(self):
        """Twice the drawing's own size made PNGs of 5000 px and more for large drawings,
        slow to export and to decode (R29b). Both the preview page and Done cap it."""
        wide = {"elements": [{"type": "rectangle", "id": "w1", "x": 0, "y": 0, "width": 3000, "height": 400}],
                "appState": {"viewBackgroundColor": "#ffffff"}, "files": {}}
        for data in (scene("small"), wide):
            drawing.preview_path(data).unlink(missing_ok=True)
        got = []
        self.web.render(scene("small"), got.append)
        self.web.render(wide, got.append)
        ui.wait_for(lambda: len(got) == 2, "the previews", timeout=60)
        self.assertGreaterEqual(png_size(got[0])[0], 2 * 200, "a small drawing has 2 pixels per unit")
        width, height = png_size(got[1])
        self.assertEqual(width, 1520)  # drawing.PREVIEW_PIXELS
        self.assertAlmostEqual(height, 1520 * (400 + 24) / (3000 + 24), delta=3)  # 12 px of padding around it

        done = []
        win = self.web.edit(self.win, wide, done.append)
        self.addCleanup(lambda: win.destroy())
        ui.wait_for(lambda: win.done_btn.get_sensitive(), "Excalidraw to start", timeout=60)
        win.finish()
        ui.wait_for(lambda: done, "the scene", timeout=60)
        self.assertEqual(png_size(drawing.preview_path(done[0]).read_bytes())[0], 1520)


if __name__ == "__main__":
    unittest.main()
