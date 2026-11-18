"""How drawings reach the screen with NVIDIA's own driver (R29f): set in the environment
before GTK and WebKit start (no GTK, so the unit tests and the package build run it)."""
from __future__ import annotations

import os

_NVIDIA_DRIVER = "/proc/driver/nvidia/version"  # there while NVIDIA's own driver is loaded
# WebKit's switches for how pages reach the screen: if any is set, the user has chosen.
_WEBKIT_RENDERER_VARS = ("WEBKIT_FORCE_DMABUF_RENDERER", "WEBKIT_DISABLE_DMABUF_RENDERER",
                         "WEBKIT_DISABLE_COMPOSITING_MODE")


def prefer_gpu(environ=os.environ, driver=_NVIDIA_DRIVER):
    """Have WebKit draw pages with the GPU when NVIDIA's own driver is loaded. Ubuntu and
    Debian build WebKitGTK with a patch that turns the GPU off for that driver (it showed
    blank pages with older ones), so the page is drawn on the CPU and every frame is
    copied: a pen stroke in a 2000×1300 drawing window updated 8 times a second instead
    of 60 (driver 595, GNOME 50 on Wayland, 2026-11-18). WEBKIT_FORCE_DMABUF_RENDERER
    skips only that check. A user who has set any of WebKit's own switches keeps them,
    so WEBKIT_DISABLE_DMABUF_RENDERER=1 turns this off.

    The page's frames then reach GTK as GPU buffers in a compressed format of NVIDIA's,
    which GTK's default Vulkan renderer can't use, so it copied each one through the CPU
    (the app at 120–190% CPU while drawing). Its GL renderer takes them as they are (10%),
    so it is used for the whole app, unless GSK_RENDERER is set.

    WebKit reads its switch at the first page and GTK reads GSK_RENDERER at the first
    window, so ui/app.py calls this at its top, before it loads GTK (tests/test_gpu.py
    checks), and so does scripts/measure-drawing-stroke.py."""
    if not os.path.exists(driver):
        return
    if not any(k in environ for k in _WEBKIT_RENDERER_VARS):
        environ["WEBKIT_FORCE_DMABUF_RENDERER"] = "1"
    if environ.get("WEBKIT_FORCE_DMABUF_RENDERER", "0") != "0" and "GSK_RENDERER" not in environ:
        environ["GSK_RENDERER"] = "gl"
