"""GTK's libraries load at the versions the app is written for (CR42 in CODE_REVIEW.md).

notterizmus/ui/__init__.py declares them once, before any UI module is imported, so each
module can be imported on its own, by a test or a script, without PyGObject warning that
it picked a version itself."""
from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "notterizmus" / "ui"
NEED_NO_VERSION = {"GLib", "GObject", "Gio"}  # PyGObject's own: it never warns about them

try:
    import gi
except ImportError:  # the package build has no PyGObject
    gi = None


def declared(tree):
    """The libraries a module passes to gi.require_version()."""
    return {n.args[0].value for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "require_version"
            and n.args and isinstance(n.args[0], ast.Constant)}


def imported(tree):
    """The libraries a module imports from gi.repository."""
    return {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "gi.repository"
            for a in n.names}


def parse(path):
    return ast.parse(path.read_text(encoding="utf-8"))


class GiVersionsTest(unittest.TestCase):
    def test_every_library_a_ui_module_imports_has_a_declared_version(self):
        package = UI / "__init__.py"
        for_all = declared(parse(package)) if package.exists() else set()
        for path in sorted(UI.glob("*.py")):
            tree = parse(path)
            missing = imported(tree) - NEED_NO_VERSION - for_all - declared(tree)
            self.assertFalse(missing, f"{path.name} imports {', '.join(sorted(missing))} with no version "
                                      "declared (add it to notterizmus/ui/__init__.py)")

    @unittest.skipIf(gi is None, "PyGObject isn't installed")
    def test_each_ui_module_imports_on_its_own_without_a_warning(self):
        code = ("import importlib, sys, warnings, gi\n"
                "warnings.simplefilter('error', gi.PyGIWarning)\n"
                "importlib.import_module(sys.argv[1])\n")
        modules = [f"notterizmus.ui.{p.stem}" for p in sorted(UI.glob("*.py")) if p.stem != "__init__"]
        runs = {m: subprocess.Popen([sys.executable, "-c", code, m], cwd=ROOT, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True) for m in modules}
        failed = []
        for module, run in runs.items():
            out = run.communicate(timeout=120)[0]
            if run.returncode:
                failed.append(f"{module}: {out.strip().splitlines()[-1]}")
        self.assertFalse(failed, "\n" + "\n".join(failed))


if __name__ == "__main__":
    unittest.main()
