"""R29 (ROADMAP.md): how fast drawings are, measured rather than guessed. Not a test: it
prints a report, and fails only if something it drives breaks.

    NOTTERIZMUS_UI_WEBKIT=1 NOTTERIZMUS_UI_TEST_TIMEOUT=900 scripts/ui-tests.sh -p 'measure_*.py'

It runs on the UI tests' private display, so no window appears on your screen and your
notes, settings and preview cache are never touched. The normal UI test run leaves it
out (its file name doesn't start with test_). Without NOTTERIZMUS_UI_WEBKIT=1 only the
parts that don't need Excalidraw run.

Environment:
  NOTTERIZMUS_MEASURE_OUT=/abs/path.json  also write the numbers as JSON
  NOTTERIZMUS_MEASURE_CHAPTER=/abs/x.notz measure a real chapter too (a copy of it is
                                          made in the scratch folder; the file isn't written)

The chapters are generated with a fixed seed, so runs can be compared: about 100 items
of notes, like the real chapters, plus drawings like the one real chapter with drawings
(boxes with labels and arrows, all of Excalidraw's fields, about 700 bytes per element;
110 elements each), or of 30 elements and one pasted picture (a 1440×900 PNG of 1 MB).

Times are wall-clock milliseconds, "median / max" where something was repeated. On the
test display (Broadway) WebKit draws without a GPU, so frames inside Excalidraw are
slower than on the desktop; the Python side is the same.
"""
from __future__ import annotations

import base64
import gc
import json
import os
import random
import struct
import sys
import tempfile
import time
import unittest
import zlib
from datetime import datetime, timedelta
from pathlib import Path

from notterizmus import backups, drawing
from notterizmus.model import Document, Node, Run, chapter_filename

from . import support as ui

WEBKIT = os.environ.get("NOTTERIZMUS_UI_WEBKIT") == "1"
BOOK = "Measure"
PICTURE = 1_000_000  # bytes of PNG in the pictures' drawings
RESULTS = {}         # section → rows (dicts): printed at the end, and written as JSON

# --- chapters --------------------------------------------------------------------------------

EN = ("fan-out on write cache shard queue worker retry backoff replica leader quorum token "
      "bucket rate limit push pull device template delivery").split()
BG = "опашка кеш реплика лидер заявка услуга известие потребител устройство шаблон доставка".split()
B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def words(rnd, n):
    return " ".join(rnd.choice(EN if rnd.random() < 0.6 else BG) for _ in range(n))


def order_key(i):
    """Excalidraw's fractional index of the i-th element: a0 … az, b10, b11, …"""
    return "a" + B62[i] if i < 62 else "b" + B62[i // 62] + B62[i % 62]


def element(rnd, i, kind, x, y, w, h, **extra):
    """An element with the fields Excalidraw writes, as in the real chapter."""
    e = {"id": f"{rnd.getrandbits(80):020x}", "type": kind, "x": x, "y": y, "width": w, "height": h,
         "angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": "transparent", "fillStyle": "solid",
         "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100, "groupIds": [],
         "frameId": None, "index": order_key(i), "roundness": {"type": 3}, "seed": rnd.getrandbits(31),
         "version": rnd.randint(5, 90), "versionNonce": rnd.getrandbits(31), "isDeleted": False,
         "boundElements": [], "updated": 1763300000000 + i, "link": None, "locked": False}
    e.update(extra)
    return e


def png(rnd, size, width=1440, height=900):
    """A PNG of about `size` bytes: noise in some rows (it doesn't compress), white in the rest."""
    noisy = max(1, min(height, size // (width * 3)))
    marks = {int(k * height / noisy) for k in range(noisy)}
    white = b"\x00" + b"\xff" * (width * 3)
    raw = b"".join((b"\x00" + rnd.randbytes(width * 3)) if y in marks else white for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def scene(rnd, count=110, picture=0):
    """A scene like the real ones: rows of boxes, most with a label, arrows between them;
    with `picture`, one pasted PNG of that many bytes above them."""
    els, files = [], {}
    if picture:
        fid = f"{rnd.getrandbits(160):040x}"
        url = "data:image/png;base64," + base64.b64encode(png(rnd, picture)).decode("ascii")
        files[fid] = {"mimeType": "image/png", "id": fid, "dataURL": url,
                      "created": 1763300000000, "lastRetrieved": 1763300000000}
        els.append(element(rnd, 0, "image", 40, -560, 720, 450, roundness=None, fileId=fid,
                           status="saved", scale=[1, 1], crop=None, strokeColor="transparent"))
    col = 0
    while len(els) < count:
        x, y = 40 + col % 8 * 260, 120 + col // 8 * 140
        col += 1
        box = element(rnd, len(els), "rectangle", x, y, 160, 60)
        els.append(box)
        if col % 3 and len(els) < count:
            label = words(rnd, 2)
            text = element(rnd, len(els), "text", x + 10, y + 17, 140, 25, roundness=None, text=label,
                           originalText=label, fontSize=20, fontFamily=5, textAlign="center",
                           verticalAlign="middle", containerId=box["id"], autoResize=True, lineHeight=1.25)
            box["boundElements"].append({"type": "text", "id": text["id"]})
            els.append(text)
        if col % 2 == 0 and len(els) < count:
            els.append(element(rnd, len(els), "arrow", x + 165, y + 30, 90, 0, roundness={"type": 2},
                               points=[[0, 0], [90, 0]], lastCommittedPoint=None, startBinding=None,
                               endBinding=None, startArrowhead=None, endArrowhead="arrow", elbowed=False))
    return {"elements": els, "files": files,
            "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20, "gridStep": 5, "gridModeEnabled": False}}


def chapter(rnd, drawings=(), items=100):
    """Top-level items as JSON: `items` headings and bullets of notes, drawing i as the
    last item under heading i."""
    nodes, made = [], 0
    while made < items:
        h = Node("heading", runs=[Run(words(rnd, 5))])
        made += 1
        for _ in range(min(8, items - made)):
            h.append(Node("bullet", runs=[Run(words(rnd, 12))]))
            made += 1
        nodes.append(h)
    for i, data in enumerate(drawings):
        nodes[i % len(nodes)].append(Node("drawing", data=data))
    return [n.to_json() for n in nodes]


_chapters = {}


def chapters():
    if not _chapters:
        rnd = random.Random(29)
        _chapters["text only"] = chapter(rnd)
        _chapters["3 drawings"] = chapter(rnd, [scene(rnd) for _ in range(3)])
        _chapters["8 drawings"] = chapter(rnd, [scene(rnd) for _ in range(8)])
        _chapters["3 pictures"] = chapter(rnd, [scene(rnd, 30, PICTURE) for _ in range(3)])
        real = os.environ.get("NOTTERIZMUS_MEASURE_CHAPTER")
        if real:
            _chapters["real chapter"] = [c.to_json() for c in Document.load(real).root.children]
    return _chapters


def save_chapter(content, title):
    """Write a chapter into the scratch notes folder (without opening it)."""
    from notterizmus.ui.window import notes_root
    no = next(ui._chapter_no[BOOK])
    doc = Document(Node("root", children=[Node.from_json(c) for c in content]), BOOK, no, title,
                   notes_root() / BOOK / chapter_filename(no, title), lang="en_US")
    doc.save()
    return doc.path


# --- measuring -------------------------------------------------------------------------------

def stats(seconds):
    xs = sorted(seconds)
    return {"median": xs[len(xs) // 2] * 1000, "p95": xs[min(len(xs) - 1, int(len(xs) * 0.95))] * 1000,
            "max": xs[-1] * 1000, "n": len(xs)}


def drain():
    ctx = ui.GLib.MainContext.default()
    while ctx.pending():
        ctx.iteration(False)


class Freeze:
    """The longest the main loop went without running a short timeout: how long the window
    stayed frozen. Up to about 10 ms is the meter's own granularity."""

    def __enter__(self):
        self.worst = 0.0
        self.last = time.perf_counter()
        self.source = ui.GLib.timeout_add(4, self._tick)
        return self

    def _tick(self):
        now = time.perf_counter()
        self.worst = max(self.worst, now - self.last)
        self.last = now
        return True

    def __exit__(self, *_exc):
        self._tick()
        ui.GLib.source_remove(self.source)

    @property
    def ms(self):
        return self.worst * 1000


def _memory_kb(pid):
    """PSS of a process in KB (RSS where PSS can't be read)."""
    for name, key in (("smaps_rollup", "Pss:"), ("status", "VmRSS:")):
        try:
            for line in Path(f"/proc/{pid}/{name}").read_text().splitlines():
                if line.startswith(key):
                    return int(line.split()[1])
        except (OSError, ValueError):
            continue
    return 0


def memory():
    """MB used by this process ("app") and by the processes it started ("web": WebKit's
    and their sandboxes), and how many web processes (one per page) there are."""
    kids = ui.child_processes()
    return {"app MB": _memory_kb(os.getpid()) / 1024, "web MB": sum(_memory_kb(p) for p in kids) / 1024,
            "web processes": sum(1 for name in kids.values() if name.startswith("WebKitWebProc")),
            "network processes": sum(1 for name in kids.values() if name.startswith("WebKitNetwork"))}


def png_size(path):
    """(width, height) of a PNG file."""
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def copies_kept(days=30, hours=2):
    """How many earlier versions of a chapter Earlier Versions keeps after `days` days of
    editing it `hours` a day (a copy every BACKUP_EVERY seconds while editing)."""
    with tempfile.TemporaryDirectory(dir=ui.scratch()) as tmp:
        folder = Path(tmp)
        start = datetime(2026, 1, 5, 18, 0)
        for day in range(days):
            t = start + timedelta(days=day)
            end = t + timedelta(hours=hours)
            while t <= end:
                (folder / f"{t.strftime(backups._STAMP)}.notz").touch()
                t += timedelta(seconds=backups.BACKUP_EVERY)
            backups.thin(folder, end)
        return len(backups.list_backups(folder))


# Drives Excalidraw the way input would (pointer, wheel, key and input events on its
# canvas or text box) and times each event: `handler` is the event's own handling,
# `drawn` until the second frame after it. Excalidraw draws in an animation frame
# callback, in the first frame after the event or, when React renders the change first,
# in the second; the second frame begins only once the one before it has been painted.
PROBE = r"""
const n = Number(count);
const frame = () => new Promise((r) => requestAnimationFrame(r));
const canvas = document.querySelector("canvas.excalidraw__canvas.interactive");
if (!canvas) throw new Error("Excalidraw's canvas isn't there");
const box = canvas.getBoundingClientRect();
const out = {handler: [], drawn: [], canvas: [Math.round(box.width), Math.round(box.height), devicePixelRatio]};
const keep = [Element.prototype.setPointerCapture, Element.prototype.releasePointerCapture];
Element.prototype.setPointerCapture = function (id) { try { keep[0].call(this, id); } catch (e) {} };
Element.prototype.releasePointerCapture = function (id) { try { keep[1].call(this, id); } catch (e) {} };
const pointer = (type, x, y, buttons) => new PointerEvent(type, {bubbles: true, cancelable: true, composed: true,
  pointerId: 1, pointerType: "mouse", isPrimary: true, button: type === "pointermove" ? -1 : 0, buttons,
  clientX: box.left + x, clientY: box.top + y});
const key = (k, extra) => new KeyboardEvent("keydown", {key: k, bubbles: true, cancelable: true, ...(extra || {})});
async function step(fire) {
  const t0 = performance.now();
  fire();
  const t1 = performance.now();
  await frame();
  await frame();
  out.handler.push(t1 - t0); out.drawn.push(performance.now() - t0);
}
async function tool(name, k) {
  const radio = document.querySelector('[data-testid="toolbar-' + name + '"]');
  if (radio) radio.click(); else canvas.dispatchEvent(key(k));
  await frame(); await frame();
}
try {
  if (what === "draw") {
    await tool("freedraw", "p");
    const at = (i) => [120 + (i * 9) % Math.max(200, box.width - 240), 140 + 60 * Math.sin(i / 6)];
    canvas.dispatchEvent(pointer("pointerdown", ...at(0), 1));
    await frame();
    for (let i = 1; i <= n; i++) await step(() => canvas.dispatchEvent(pointer("pointermove", ...at(i), 1)));
    canvas.dispatchEvent(pointer("pointerup", ...at(n), 0));
  } else if (what === "type") {
    await tool("text", "t");
    // a gap between press and release, as with a real click: Excalidraw opens the text
    // box on release, from state it set on the press
    canvas.dispatchEvent(pointer("pointerdown", 60, box.height - 90, 1));
    await frame(); await frame();
    canvas.dispatchEvent(pointer("pointerup", 60, box.height - 90, 0));
    let ta = null;
    for (let i = 0; i < 120 && !(ta = document.querySelector("textarea.excalidraw-wysiwyg")); i++) await frame();
    if (!ta) throw new Error("no text box appeared");
    const text = "Fan-out on write: опашка за известия ";
    for (let i = 0; i < n; i++) {
      const ch = text[i % text.length];
      await step(() => { ta.value += ch; ta.dispatchEvent(new InputEvent("input", {bubbles: true, data: ch, inputType: "insertText"})); });
    }
    ta.dispatchEvent(key("Escape"));
  } else if (what === "pan") {
    await tool("selection", "v");
    for (let i = 0; i < n; i++) {
      const dy = (i % 20 < 10 ? 1 : -1) * 40;
      await step(() => canvas.dispatchEvent(new WheelEvent("wheel", {bubbles: true, cancelable: true, deltaY: dy,
        deltaMode: 0, clientX: box.left + box.width / 2, clientY: box.top + box.height / 2})));
    }
  } else if (what === "move") {
    await tool("selection", "v");
    canvas.dispatchEvent(key("a", {ctrlKey: true, code: "KeyA"}));
    await frame(); await frame();
    for (let i = 0; i < n; i++) {
      const k = i % 20 < 10 ? "ArrowRight" : "ArrowLeft";
      await step(() => canvas.dispatchEvent(key(k, {code: k})));
    }
    canvas.dispatchEvent(key("Escape"));
  }
  await frame(); await frame();
} finally {
  Element.prototype.setPointerCapture = keep[0];
  Element.prototype.releasePointerCapture = keep[1];
}
return JSON.stringify(out);
"""

PROBES = (("draw", 60, "drawing a line"), ("type", 40, "typing a label"),
          ("pan", 40, "scrolling the view"), ("move", 30, "moving everything (arrow keys)"))


def js(view, body, timeout=120, **args):
    """Run an async function body in a drawing page; its result as text."""
    from notterizmus.ui import drawing_web
    got = []
    drawing_web._call(view, body, lambda text, error: got.append((text, error)), **args)
    ui.wait_for(lambda: got, "the drawing page to answer", timeout)
    text, error = got[0]
    if error is not None:
        raise AssertionError(f"the drawing page failed: {error}")
    return text


class MeasureDrawings(ui.UITestCase):
    """The measurements, in order: the window opening first, so it starts WebKit cold."""

    def need_webkit(self):
        from notterizmus.ui import drawing_web
        if not drawing_web.available():
            self.skipTest("WebKitGTK (gir1.2-webkit-6.0) isn't installed")
        if not WEBKIT:
            self.skipTest("set NOTTERIZMUS_UI_WEBKIT=1 to measure Excalidraw itself")

    def between(self):
        """A small chapter to open in between, so the next open builds its rows afresh."""
        if not hasattr(self.__class__, "_between"):
            self.__class__._between = save_chapter([Node("heading", runs=[Run("between")]).to_json()], "Between")
        return self._between

    def open(self, path):
        """Open a chapter after the small one; (seconds the open blocked, seconds until settled)."""
        self.win.open_path(self.between())
        ui.settle()
        t = time.perf_counter()
        self.win.open_path(path)
        blocked = time.perf_counter() - t
        ui.settle()
        return blocked, time.perf_counter() - t

    def drawing_rows(self):
        from notterizmus.ui.rows import DrawingRow
        return [r for r in self.ed.rows.values() if isinstance(r, DrawingRow)]

    # -- 1. the window: opening it ----------------------------------------------------------

    def test_1_drawing_window(self):
        self.need_webkit()
        from notterizmus.ui import drawing_web
        rnd = random.Random(1)
        scenes = {"2 elements": scene(rnd, 2), "110 elements": scene(rnd), "440 elements": scene(rnd, 440),
                  "1 MB picture": scene(rnd, 30, PICTURE)}
        rows = [{"scene": "(nothing open)", **memory()}]
        for name, data in scenes.items():
            for i in range(3):
                marks = {}
                t0 = time.perf_counter()
                with Freeze() as freeze:
                    win = drawing_web.edit(self.win, data, lambda _d: None)
                    shown = time.perf_counter() - t0
                    win.view.connect("load-changed", lambda _v, ev: marks.setdefault(int(ev), time.perf_counter()))
                    ui.wait_for(lambda: win.done_btn.get_sensitive(), "Excalidraw to start", timeout=90)
                ready = time.perf_counter() - t0
                loaded = marks.get(int(drawing_web.WebKit.LoadEvent.FINISHED), t0) - t0
                mem = memory()
                win._closing = True
                win.close()
                ui.wait_for(lambda: not win.get_visible(), "the drawing window to close")
                del win
                gc.collect()
                ui.pump_until(lambda: ui.web_processes() <= rows[0]["web processes"], 5)
                rows.append({"scene": name, "open": i + 1, "window shown": shown * 1000,
                             "page loaded": loaded * 1000, "Excalidraw ready": ready * 1000,
                             "start on loaded page": (ready - loaded) * 1000, "longest freeze": freeze.ms,
                             **mem, "web processes after close": ui.web_processes()})
        RESULTS["drawing window"] = rows

    # -- 2. inside Excalidraw, and Done ---------------------------------------------------------

    def test_2_inside_and_done(self):
        self.need_webkit()
        from notterizmus.ui import drawing_web
        windows = []
        real_edit = drawing_web.edit

        def edit(*args):
            windows.append(real_edit(*args))
            return windows[-1]

        drawing_web.edit = edit
        self.addCleanup(setattr, drawing_web, "edit", real_edit)
        rnd = random.Random(2)
        scenes = {"110 elements": scene(rnd), "440 elements": scene(rnd, 440), "1 MB picture": scene(rnd, 30, PICTURE)}
        inside, done = [], []
        for name, data in scenes.items():
            content = [Node("heading", runs=[Run(name)], children=[Node("drawing", data=data)]).to_json()]
            self.win.open_path(save_chapter(content, f"Inside {name}"))
            ui.settle()
            row = self.drawing_rows()[0]
            ui.wait_for(lambda: row.picture.get_visible(), "the drawing's picture", 90)
            self.ed.edit_drawing(row.node)
            win = windows[-1]
            ui.wait_for(lambda: win.done_btn.get_sensitive(), "Excalidraw to start", timeout=90)
            for what, count, label in PROBES:
                got = json.loads(js(win.view, PROBE, what=what, count=str(count)))
                inside.append({"scene": name, "action": label, "canvas": got["canvas"],
                               "until drawn": stats([x / 1000 for x in got["drawn"]]),
                               "event handler": stats([x / 1000 for x in got["handler"]])})
            self.assertEqual(js(win.view, drawing_web._JS_CHANGED), "true", "the probes changed nothing")
            # Done makes the page export the scene and its picture, then the app takes them
            t = time.perf_counter()
            js(win.view, drawing_web._JS_SAVE)
            page = time.perf_counter() - t
            before = self.ed._cur
            with Freeze() as freeze:
                t = time.perf_counter()
                win.finish()
                ui.wait_for(lambda: self.ed._cur is not before, "the drawing back in the chapter", 90)
                total = time.perf_counter() - t
            t = time.perf_counter()
            self.win._flush_save()
            save = time.perf_counter() - t
            ui.wait_for(lambda: not win.get_visible(), "the drawing window to close")
            done.append({"scene": name, "page export": page * 1000, "Done until in chapter": total * 1000,
                         "longest freeze": freeze.ms, "autosave after": save * 1000})
        RESULTS["inside Excalidraw"] = inside
        RESULTS["Done"] = done

    # -- 3. previews when a chapter opens ----------------------------------------------------------

    def test_3_previews(self):
        self.need_webkit()
        from notterizmus.ui import drawing_web
        rows = []
        for name, content in chapters().items():
            if not any(c.get("kind") == "drawing" for top in content for c in [top, *top.get("children", [])]):
                continue
            path = save_chapter(content, f"Previews {name}")
            datas = [n.data for n in Document.load(path).root.walk() if n.kind == "drawing"]
            for how in ("new preview page", "preview page running", "all cached"):
                if how != "all cached":
                    for d in datas:
                        drawing.preview_path(d).unlink(missing_ok=True)
                if how == "new preview page":
                    drawing_web.shutdown()
                    gc.collect()
                self.win.open_path(self.between())
                ui.settle()
                with Freeze() as freeze:
                    t0 = time.perf_counter()
                    self.win.open_path(path)
                    blocked = time.perf_counter() - t0
                    pending = {id(r): r for r in self.drawing_rows()}
                    times = []
                    end = t0 + 60 * len(pending)
                    while pending and time.perf_counter() < end:
                        drain()
                        for key, r in list(pending.items()):
                            if r.picture.get_visible() or "can't be shown" in r.note.get_text():
                                times.append(time.perf_counter() - t0)
                                del pending[key]
                        time.sleep(0.002)
                self.assertFalse(pending, "some previews never came")
                failed = [r for r in self.drawing_rows() if not r.picture.get_visible()]
                self.assertFalse(failed, "some previews couldn't be made")
                sizes = [png_size(drawing.preview_path(d)) for d in datas]
                rows.append({"chapter": name, "previews": how, "open blocked": blocked * 1000,
                             "first picture": min(times) * 1000, "all pictures": max(times) * 1000,
                             "longest freeze": freeze.ms,
                             "preview pixels": max(sizes, key=lambda s: s[0] * s[1]),
                             "preview MB as textures": sum(w * h * 4 for w, h in sizes) / 2 ** 20,
                             "preview KB on disk": sum(drawing.preview_path(d).stat().st_size for d in datas) / 1024,
                             **memory()})
                ui.settle()
        RESULTS["previews"] = rows

    # -- 4. the chapter: undo, autosave, earlier versions -----------------------------------------

    def test_4_chapters(self):
        from notterizmus.ui import drawing_web
        real = drawing_web.render
        drawing_web.render = lambda _data, _done: None  # previews are measured with Excalidraw above
        self.addCleanup(setattr, drawing_web, "render", real)
        rows = []
        kept = copies_kept()
        for name, content in chapters().items():
            rows.append(self.measure_chapter(name, content, kept))
        RESULTS["chapters"] = rows

    def measure_chapter(self, name, content, kept):
        win, ed = self.win, self.ed
        path = save_chapter(content, f"Chapter {name}")
        r = {"chapter": name, "file KB": path.stat().st_size / 1024,
             "drawings": sum(1 for c in Document.load(path).root.walk() if c.kind == "drawing")}
        loads = []
        for _ in range(5):
            t = time.perf_counter()
            Document.load(path)
            loads.append(time.perf_counter() - t)
        r["load"] = stats(loads)
        opens = [self.open(path) for _ in range(3)]
        r["open blocked"] = stats([o[0] for o in opens])
        r["open settled"] = stats([o[1] for o in opens])
        snaps = []
        for _ in range(7):
            t = time.perf_counter()
            snap = ed._snapshot()
            snaps.append(time.perf_counter() - t)
        r["snapshot"] = stats(snaps)
        r["undo step KB"] = sys.getsizeof(snap[0]) / 1024
        r["500 undo steps MB"] = 500 * sys.getsizeof(snap[0]) / 2 ** 20
        # typing "a " 50 times: every keystroke takes a snapshot, every "a " is an undo step
        bullet = next(n for n in ed.doc.root.walk() if n.kind == "bullet")
        view = ui.focus(bullet, -1).views()[0]
        view.grab_focus()
        buf = view.get_buffer()
        before = memory()["app MB"]
        keys = []
        for ch in "a " * 50:
            t = time.perf_counter()
            buf.insert_interactive_at_cursor(ch, -1, True)
            keys.append(time.perf_counter() - t)
            drain()
        r["keystroke"] = stats(keys)
        r["undo steps held"] = len(ed._undo)
        r["undo history MB"] = sum(sys.getsizeof(s[0]) for s in ed._undo) / 2 ** 20
        r["app MB growth while typing"] = memory()["app MB"] - before
        ui.wait_editor()
        undos, redos = [], []
        for _ in range(5):
            t = time.perf_counter()
            ed.undo()
            undos.append(time.perf_counter() - t)
            ui.wait_editor()
        for _ in range(5):
            t = time.perf_counter()
            ed.redo()
            redos.append(time.perf_counter() - t)
            ui.wait_editor()
        r["undo"], r["redo"] = stats(undos), stats(redos)
        saves = []
        win._flush_save()
        for _ in range(5):
            t = time.perf_counter()
            win.save(quiet=True)
            saves.append(time.perf_counter() - t)
        r["autosave"] = stats(saves)
        folder = Path(tempfile.mkdtemp(dir=ui.scratch()))
        t = time.perf_counter()
        copy = backups.backup(path, folder, force=True)
        r["backup copy"] = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        backups.backup(path, folder, force=True)  # the same again: compared, not copied
        r["backup check"] = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        ed.replace_content(Document.load(copy).root)
        r["restore version"] = (time.perf_counter() - t) * 1000
        ui.wait_editor()
        r["versions kept (30 days, 2 h a day)"] = kept
        r["their size MB"] = kept * path.stat().st_size / 2 ** 20
        return r


# --- the report ------------------------------------------------------------------------------

def _cell(v):
    if isinstance(v, dict) and "median" in v:
        return f"{v['median']:.0f} / {v['max']:.0f}" if v["max"] >= 10 else f"{v['median']:.1f} / {v['max']:.1f}"
    if isinstance(v, float):
        return f"{v:.0f}" if abs(v) >= 10 else f"{v:.1f}"
    if isinstance(v, (list, tuple)):
        return "×".join(str(x) for x in v)
    return str(v)


def _table(rows):
    keys = []
    for r in sorted(rows, key=len, reverse=True):  # the fullest row sets the order
        keys += [k for k in r if k not in keys]
    cells = [[_cell(r.get(k, "")) for k in keys] for r in rows]
    width = [max(len(k), *(len(c[i]) for c in cells)) for i, k in enumerate(keys)]
    lines = ["  ".join(k.ljust(w) for k, w in zip(keys, width))]
    lines += ["  ".join(c.ljust(w) for c, w in zip(row, width)) for row in cells]
    return "\n".join(lines)


def tearDownModule():
    if not RESULTS:
        return
    out = ["", "R29 measurements (ms unless named; \"median / max\" where repeated)", ""]
    for section, rows in RESULTS.items():
        out += [f"== {section}", _table(rows), ""]
    sys.stdout.write("\n".join(out) + "\n")
    sys.stdout.flush()
    dest = os.environ.get("NOTTERIZMUS_MEASURE_OUT")
    if dest:
        Path(dest).write_text(json.dumps({"when": datetime.now().isoformat(timespec="seconds"),
                                          "results": RESULTS}, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    unittest.main()
