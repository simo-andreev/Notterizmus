"""The UI tests wait for a condition, never for a time (CR50 in CODE_REVIEW.md): a fixed
pause passes on an idle machine and fails on a busy one, and pads the suite everywhere."""
import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parent / "ui"
# The helpers' own short waits, the input client's frame pacing and the measurements' polling.
ALLOWED = {"support.py", "broadway_input.py", "measure_drawings.py"}
FIXED_WAIT = re.compile(r"\bui\.pump\(|\btime\.sleep\(")


class FixedWaitsTest(unittest.TestCase):
    def test_no_ui_test_waits_for_a_fixed_time(self):
        found = [f"{path.name}:{n}: {line.strip()}"
                 for path in sorted(UI.glob("*.py")) if path.name not in ALLOWED
                 for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if FIXED_WAIT.search(line)]
        self.assertEqual(found, [], "wait with ui.wait_for(), ui.settle() or ui.frames() instead")


if __name__ == "__main__":
    unittest.main()
