"""The app's log (no GTK): warnings and errors to stderr, which reaches the journal for an
app started from the desktop (`journalctl --user -t notterizmus` or by its command line),
and everything with NOTTERIZMUS_DEBUG=1 (RV7 in PLAN.md). Modules log through
logging.getLogger(__name__)."""
from __future__ import annotations

import logging
import os
import sys

FORMAT = "%(name)s: %(levelname)s: %(message)s"


class _Handler(logging.StreamHandler):
    """The handler setup() adds, so a second call replaces it."""


def setup(env=None, stream=None):
    env = os.environ if env is None else env
    log = logging.getLogger("notterizmus")
    log.setLevel(logging.DEBUG if env.get("NOTTERIZMUS_DEBUG") else logging.WARNING)
    for h in [h for h in log.handlers if isinstance(h, _Handler)]:
        log.removeHandler(h)
    handler = _Handler(stream or sys.stderr)
    handler.setFormatter(logging.Formatter(FORMAT))
    log.addHandler(handler)
    log.propagate = False
