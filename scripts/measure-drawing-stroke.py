#!/usr/bin/env python3
"""Time a pen stroke in the real drawing window, on your own display.

    scripts/measure-drawing-stroke.py [WIDTH HEIGHT]

tests/ui/measure_drawings.py measures on the UI tests' private display, which draws
without a GPU, so it can't see how fast WebKit draws on the desktop: there a stroke
updated 8 times a second while that display showed nothing wrong (R29f in ROADMAP.md).
This opens the drawing window (default 2000×1300) on a scene of 110 elements, draws a
stroke of 180 pointer moves, one per frame, through Excalidraw's own event handling, and
prints how often the page and the window drew, and how busy the app and WebKit's
processes were. The window shows for a few seconds and closes; nothing is saved, but
the preview cache isn't redirected. Set WebKit's or GTK's variables (WEBKIT_*,
GSK_RENDERER) in front of it to compare.
"""
import json
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib  # noqa: E402

from notterizmus.ui import drawing_web  # noqa: E402
from tests.ui.measure_drawings import scene  # noqa: E402

MOVES = 180
STROKE = r"""
const n = Number(count);
const canvas = document.querySelector("canvas.excalidraw__canvas.interactive");
if (!canvas) throw new Error("Excalidraw's canvas isn't there");
const box = canvas.getBoundingClientRect();
const frame = () => new Promise((r) => requestAnimationFrame(r));
document.querySelector('[data-testid="toolbar-freedraw"]').click();
await frame(); await frame();
const keep = [Element.prototype.setPointerCapture, Element.prototype.releasePointerCapture];
Element.prototype.setPointerCapture = function (id) { try { keep[0].call(this, id); } catch (e) {} };
Element.prototype.releasePointerCapture = function (id) { try { keep[1].call(this, id); } catch (e) {} };
const pointer = (type, x, y, buttons) => new PointerEvent(type, {bubbles: true, cancelable: true, composed: true,
  pointerId: 1, pointerType: "mouse", isPrimary: true, button: type === "pointermove" ? -1 : 0, buttons,
  clientX: box.left + x, clientY: box.top + y});
const at = (i) => [200 + (i * 7) % Math.max(200, box.width - 400), box.height / 2 + 200 * Math.sin(i / 9)];
const out = {canvas: [Math.round(box.width), Math.round(box.height), devicePixelRatio], frames: []};
try {
  canvas.dispatchEvent(pointer("pointerdown", ...at(0), 1));
  let last = await frame();
  for (let i = 1; i <= n; i++) {
    canvas.dispatchEvent(pointer("pointermove", ...at(i), 1));
    const t = await frame();
    out.frames.push(t - last); last = t;
  }
  canvas.dispatchEvent(pointer("pointerup", ...at(n), 0));
} finally {
  Element.prototype.setPointerCapture = keep[0];
  Element.prototype.releasePointerCapture = keep[1];
}
return JSON.stringify(out);
"""


def stat(pid):
    with open(f"/proc/{pid}/stat") as f:
        return f.read().rsplit(")", 1)[1].split()


def cpu_seconds(pid):
    s = stat(pid)
    return (int(s[11]) + int(s[12])) / os.sysconf("SC_CLK_TCK")


def webkit_processes():
    """WebKit's helper processes started since this script did."""
    me = int(stat(os.getpid())[19])
    out = []
    for p in filter(str.isdigit, os.listdir("/proc")):
        try:
            name = Path(f"/proc/{p}/comm").read_text().strip()
            if name.startswith("WebKit") and int(stat(p)[19]) >= me:
                out.append((int(p), name))
        except OSError:
            pass
    return out


def wait(cond, timeout=60):
    ctx, end = GLib.MainContext.default(), time.time() + timeout
    while not cond():
        if time.time() > end:
            sys.exit("timed out")
        ctx.iteration(True)


def pump(seconds):
    ctx, end = GLib.MainContext.default(), time.time() + seconds
    while time.time() < end:
        ctx.iteration(False) or time.sleep(0.005)


def q(xs, f):
    s = sorted(xs)
    return s[min(len(s) - 1, int(f * len(s)))]


def main():
    width, height = (int(a) for a in sys.argv[1:3]) if len(sys.argv) >= 3 else (2000, 1300)
    Adw.init()
    win = drawing_web.DrawingWindow(None, scene(random.Random(1)), lambda _data: None)
    win.set_default_size(width, height)
    win.present()
    wait(win.done_btn.get_sensitive)
    pump(1.0)
    policy = win.view.get_settings().get_hardware_acceleration_policy().value_nick
    renderer = type(win.get_renderer()).__name__
    paints = []
    clock = win.get_frame_clock()
    handler = clock.connect("after-paint", lambda _c: paints.append(time.perf_counter()))
    procs = [(os.getpid(), "app")] + webkit_processes()
    before = {p: cpu_seconds(p) for p, _ in procs}
    t0 = time.perf_counter()
    got = []
    drawing_web._call(win.view, STROKE, lambda text, error: got.append((text, error)), count=str(MOVES))
    wait(lambda: got, 120)
    took = time.perf_counter() - t0
    used = {p: cpu_seconds(p) - before[p] for p, _ in procs}
    clock.disconnect(handler)
    win._closing = True
    win.close()
    text, error = got[0]
    if error is not None:
        sys.exit(f"the page failed: {error}")
    page = json.loads(text)
    frames = page["frames"]
    gaps = [(b - a) * 1000 for a, b in zip(paints, paints[1:])]
    print(f"WebKit acceleration: {policy}; WEBKIT_FORCE_DMABUF_RENDERER="
          f"{os.environ.get('WEBKIT_FORCE_DMABUF_RENDERER', '(unset)')}; "
          f"GTK renderer: {renderer}")
    print(f"canvas {page['canvas'][0]}×{page['canvas'][1]} at {page['canvas'][2]}x; "
          f"{len(frames)} moves in {took:.1f} s")
    print(f"page frames: {1000 * len(frames) / sum(frames):.0f}/s; median {q(frames, .5):.1f} ms, "
          f"90% {q(frames, .9):.1f}, max {max(frames):.1f}")
    if gaps:
        print(f"window drawn: {len(paints) / took:.0f}/s; median gap {q(gaps, .5):.1f} ms, "
              f"90% {q(gaps, .9):.1f}, max {max(gaps):.1f}")
    print("CPU: " + ", ".join(f"{name} {100 * used[p] / took:.0f}%" for p, name in procs if used[p] > 0.01))


if __name__ == "__main__":
    main()
