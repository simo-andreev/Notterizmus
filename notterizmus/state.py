"""What the window remembers between runs: state.json in the config folder (no GTK).

A file that can't be read, or isn't a JSON object, counts as empty, and a setting of the
wrong kind is left out, so that the window's default applies: a broken file used to stop
the app from starting (CR22 in CODE_REVIEW.md). Saving replaces the file in one step."""
from __future__ import annotations

import json
from pathlib import Path

from .files import atomic_write
from .paths import config_dir

KINDS = {"last_file": str, "last_book": str, "spell_lang": str, "spell": bool, "sidebar": bool,
         "sidebar_width": int, "zoom": int}


def path():
    return config_dir() / "state.json"


def _fits(key, value):
    kind = KINDS.get(key)
    if kind is None:
        return True  # a setting from a newer version: kept as it is
    if kind is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, kind)


def load(file=None):
    try:
        data = json.loads(Path(file or path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if _fits(k, v)}


def save(settings, file=None):
    with atomic_write(file or path()) as f:
        json.dump(settings, f, ensure_ascii=False, indent=1)
