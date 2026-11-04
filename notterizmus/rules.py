"""Formatting rules: built-in defaults, overridable by ~/.config/notterizmus/rules.toml."""
from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path

DEFAULTS = {
    "numbering": {
        # One entry per depth; the last one repeats for deeper levels.
        "levels": ["roman_upper", "arabic", "alpha_lower", "roman_lower"],
        "separator": ".",
        "suffix": ")",
        "bold_label": False,
    },
    "tree": {
        "branch": "├ ",
        "last": "└ ",
        "pipe": "│ ",
        "space": "  ",
        "trunk": "│",
        "spacer_lines": True,       # "│ │" line before each numbered sub-item...
        "spacer_after_leaf": False,  # ...except right after a bullet
        "blank_between_top_level": True,
        "bold_connectors": False,
    },
    "bullets": {
        "indent": 5,         # marker column = heading label column + indent
        "nested_indent": 4,  # extra columns per nested bullet level
    },
    "heading": {"trigger": "#"},
    "export": {
        # Wrap tree prefixes in <code>: TopCoding then shows them monospace (aligned)
        # but with an inline-code background. font-family styles are stripped on paste.
        "code_prefix": False,
    },
    # name -> symbol shown, trigger typed at line start (followed by a space)
    "markers": {
        "dot": {"symbol": "•", "trigger": "*", "label": "Bullet"},
        "plus": {"symbol": "+", "trigger": "+", "label": "Pro"},
        "minus": {"symbol": "-", "trigger": "-", "label": "Con"},
    },
}

# --- numbering formats (add new ones here and name them in numbering.levels) --

_ROMAN_UP = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ"
_ROMAN_LO = "ⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹⅺⅻ"
_ROMAN_PARTS = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
_UP_MAP = dict(zip("IVXLCDM", "ⅠⅤⅩⅬⅭⅮⅯ"))
_LO_MAP = dict(zip("IVXLCDM", "ⅰⅴⅹⅼⅽⅾⅿ"))


def _ascii_roman(n):
    s = ""
    for v, r in _ROMAN_PARTS:
        while n >= v:
            s += r
            n -= v
    return s


def _roman(n, singles, letter_map):
    if 1 <= n <= 12:
        return singles[n - 1]
    units = n % 10
    tens = "".join(letter_map[c] for c in _ascii_roman(n - units))
    return tens + (singles[units - 1] if units else "")


def _alpha(n, base):
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(ord(base) + r) + s
    return s


FORMATS = {
    "roman_upper": lambda n: _roman(n, _ROMAN_UP, _UP_MAP),
    "roman_lower": lambda n: _roman(n, _ROMAN_LO, _LO_MAP),
    "arabic": str,
    "alpha_lower": lambda n: _alpha(n, "a"),
    "alpha_upper": lambda n: _alpha(n, "A"),
}


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "notterizmus"


def user_rules_path():
    return config_dir() / "rules.toml"


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict) and k != "markers":
            _merge(base[k], v)
        elif k == "markers" and isinstance(v, dict):
            for name, spec in v.items():
                base["markers"].setdefault(name, {}).update(spec)
        else:
            base[k] = v
    return base


class Rules:
    def __init__(self, data=None):
        self.data = data or copy.deepcopy(DEFAULTS)
        self.error = None

    @classmethod
    def load(cls, path=None):
        data = copy.deepcopy(DEFAULTS)
        r = cls(data)
        p = Path(path) if path else user_rules_path()
        if p.exists():
            try:
                with open(p, "rb") as f:
                    _merge(data, tomllib.load(f))
            except (OSError, tomllib.TOMLDecodeError) as e:
                r.error = f"{p}: {e}"
        return r

    def __getitem__(self, k):
        return self.data[k]

    def label(self, numbers):
        """numbers: 1-based index at each depth, e.g. [2, 1, 1] -> 'Ⅱ.1.a)'"""
        n = self.data["numbering"]
        levels = n["levels"]
        parts = []
        for depth, num in enumerate(numbers):
            fmt = levels[min(depth, len(levels) - 1)]
            parts.append(FORMATS.get(fmt, str)(num))
        return n["separator"].join(parts) + n["suffix"]

    def marker_symbol(self, name):
        m = self.data["markers"].get(name)
        return m["symbol"] if m else "•"

    def triggers(self):
        """trigger text -> (kind, marker)"""
        t = {self.data["heading"]["trigger"]: ("heading", None)}
        for name, m in self.data["markers"].items():
            if m.get("trigger"):
                t[m["trigger"]] = ("bullet", name)
        return t
