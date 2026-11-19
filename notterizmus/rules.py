"""Formatting rules: built-in defaults, overridable by ~/.config/notterizmus/rules.toml."""
from __future__ import annotations

import copy
import json
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
        "important": {"symbol": "!", "trigger": "!", "label": "Important"},
        "question": {"symbol": "?", "trigger": "?", "label": "Question"},
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


_KINDS = {str: "text in quotes", bool: "true or false", int: "a whole number", list: "a list"}


def _toml(value):
    """A value as it's written in TOML (true, "text", [1, 2]); JSON spells these the same."""
    return json.dumps(value, ensure_ascii=False)


def _problem(data):
    """What makes these rules unusable (a user's file with the wrong kind of value), or
    None. Settings this version doesn't know are left alone."""
    for section, defaults in DEFAULTS.items():
        got = data.get(section)
        if not isinstance(got, dict):
            return f"[{section}] must be a table of settings"
        if section == "markers":
            for name, spec in got.items():
                if not isinstance(spec, dict) or not isinstance(spec.get("symbol"), str) or not spec["symbol"]:
                    return f'[markers.{name}] needs a symbol, such as symbol = "?"'
                for key in ("trigger", "label"):
                    if not isinstance(spec.get(key, ""), str):
                        return f"markers.{name}.{key} must be {_KINDS[str]}"
            continue
        for key, default in defaults.items():
            if type(got.get(key)) is not type(default):
                return f"{section}.{key} must be {_KINDS[type(default)]}, such as {_toml(default)}"
    levels = data["numbering"]["levels"]
    if not levels or not all(isinstance(name, str) for name in levels):
        return "numbering.levels must name at least one format"
    unknown = [name for name in levels if name not in FORMATS]
    if unknown:  # (it used to become Arabic numbers silently: CR23)
        return f'numbering.levels: "{unknown[0]}" isn\'t a format; the formats are {", ".join(FORMATS)}'
    numbered, seen = data["heading"]["trigger"], {}
    for name, spec in data["markers"].items():
        trigger = spec.get("trigger", "")
        if not trigger:
            continue
        if trigger == numbered:
            return f'markers.{name}.trigger "{trigger}" is the numbered item\'s (heading.trigger)'
        if trigger in seen:
            return f'markers.{seen[trigger]} and markers.{name} have the same trigger "{trigger}"'
        seen[trigger] = name
    return None


class Rules:
    def __init__(self, data=None):
        self.data = data or copy.deepcopy(DEFAULTS)
        self.error = None

    @classmethod
    def load(cls, path=None):
        """The defaults with the user's file on top. A file that can't be used (not TOML,
        or a value of the wrong kind) is reported in .error and left out entirely."""
        data = copy.deepcopy(DEFAULTS)
        r = cls(data)
        p = Path(path) if path else user_rules_path()
        if p.exists():
            try:
                with open(p, "rb") as f:
                    _merge(data, tomllib.load(f))
                problem = _problem(data)
            except (OSError, ValueError, TypeError, AttributeError) as e:  # ValueError: not TOML
                problem = str(e)
            if problem:
                r.error = f"{p}: {problem}"
                r.data = copy.deepcopy(DEFAULTS)
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
