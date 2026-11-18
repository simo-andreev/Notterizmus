"""The unit tests pass without PyGObject, as in the package build (CR1 in CODE_REVIEW.md).

Launchpad builds the package with only its Build-Depends installed, which leave out
PyGObject and GTK, and runs these tests. A test module that imports GTK at its top, or a
plain TestCase that loads a UI module, then fails there, and so does the build: 1.4.2 and
1.5.0 were never built. So the whole unit discovery runs again here, in a separate
process in which PyGObject can't be imported."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSIDE = "NOTTERIZMUS_TESTS_WITHOUT_GI"  # set in that process, where this test skips itself

RUN_WITHOUT_GI = """
import sys
import unittest
sys.modules["gi"] = None  # "import gi" now raises ImportError, as where PyGObject isn't installed
unittest.main(module=None, argv=["unittest", "discover", "-s", "tests", "-t", "."])
"""


@unittest.skipIf(os.environ.get(INSIDE) == "1", "this is the run without PyGObject")
class WithoutPyGObjectTest(unittest.TestCase):
    def test_the_unit_tests_pass_without_pygobject(self):
        run = subprocess.run([sys.executable, "-c", RUN_WITHOUT_GI], cwd=ROOT, env={**os.environ, INSIDE: "1"},
                             capture_output=True, text=True, timeout=600)
        self.assertEqual(run.returncode, 0, "the unit tests without PyGObject:\n" + run.stderr[-6000:])


if __name__ == "__main__":
    unittest.main()
