"""The GPU setup for drawings on NVIDIA's driver (R29f): what it sets, and that the app sets
it before GTK or WebKit starts."""
from __future__ import annotations

import ast
import os
import tempfile
import unittest
from pathlib import Path

from notterizmus import gpu

PACKAGE = Path(gpu.__file__).resolve().parent


def calls_at_import(tree):
    """Positions of a module's top-level statements that call prefer_gpu()."""
    return [i for i, s in enumerate(tree.body)
            if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
            and getattr(s.value.func, "attr", getattr(s.value.func, "id", "")).endswith("prefer_gpu")]


def loads_gtk(statement):
    """An import that loads GTK: from gi.repository, or from another UI module."""
    return isinstance(statement, ast.ImportFrom) and (statement.module == "gi.repository" or statement.level == 1)


class PreferGpuTest(unittest.TestCase):
    """With NVIDIA's driver, Ubuntu's WebKitGTK draws pages on the CPU unless asked not to:
    a stroke in the drawing window then updated 8 times a second instead of 60. Once it
    uses the GPU, GTK's Vulkan renderer copies each of its frames through the CPU, and its
    GL renderer doesn't."""

    def prefer(self, environ, driver_loaded=True):
        with tempfile.TemporaryDirectory() as tmp:
            driver = os.path.join(tmp, "version")
            if driver_loaded:
                open(driver, "w").close()
            gpu.prefer_gpu(environ, driver)
        return environ

    def test_nvidias_driver_asks_webkit_for_the_gpu_and_gtk_for_gl(self):
        self.assertEqual(self.prefer({}), {"WEBKIT_FORCE_DMABUF_RENDERER": "1", "GSK_RENDERER": "gl"})

    def test_other_drivers_are_left_to_webkit_and_gtk(self):
        self.assertEqual(self.prefer({}, driver_loaded=False), {})

    def test_webkits_own_switches_set_by_the_user_win(self):
        for var in ("WEBKIT_FORCE_DMABUF_RENDERER", "WEBKIT_DISABLE_DMABUF_RENDERER",
                    "WEBKIT_DISABLE_COMPOSITING_MODE"):
            self.assertEqual(self.prefer({var: "0"}), {var: "0"})
        self.assertEqual(self.prefer({"WEBKIT_FORCE_DMABUF_RENDERER": "1"}),
                         {"WEBKIT_FORCE_DMABUF_RENDERER": "1", "GSK_RENDERER": "gl"})

    def test_a_renderer_chosen_by_the_user_is_kept(self):
        self.assertEqual(self.prefer({"GSK_RENDERER": "vulkan"}),
                         {"WEBKIT_FORCE_DMABUF_RENDERER": "1", "GSK_RENDERER": "vulkan"})


class WhenItIsSetTest(unittest.TestCase):
    """WebKit reads its switch at the first page and GTK reads GSK_RENDERER at the first
    window. The app sets both at the top of ui/app.py, before it loads GTK, and no other
    module changes the environment when it is imported (CR41 in CODE_REVIEW.md)."""

    def test_the_app_sets_it_before_it_loads_gtk(self):
        tree = ast.parse((PACKAGE / "ui" / "app.py").read_text(encoding="utf-8"))
        calls = calls_at_import(tree)
        self.assertEqual(len(calls), 1, "ui/app.py should call prefer_gpu() once, at its top")
        first_gtk = min(i for i, s in enumerate(tree.body) if loads_gtk(s))
        self.assertLess(calls[0], first_gtk, "ui/app.py loads GTK before it calls prefer_gpu()")

    def test_no_other_module_calls_it_when_imported(self):
        for path in sorted(PACKAGE.rglob("*.py")):
            if path != PACKAGE / "ui" / "app.py":
                self.assertEqual(calls_at_import(ast.parse(path.read_text(encoding="utf-8"))), [],
                                 f"{path.relative_to(PACKAGE.parent)} calls prefer_gpu() when it is imported")


if __name__ == "__main__":
    unittest.main()
