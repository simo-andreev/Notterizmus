"""Command search (Ctrl+Shift+P): matching typed text against command names (no GTK).

Each word typed must appear in the command's title or keywords (any order, any case);
matches at the start of the title or of a word rank first.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Command:
    title: str
    run: object = None              # callable, run after the search closes
    accel: str = ""                 # GTK accelerator to show, e.g. "<Control>n"
    keywords: str = ""              # other words it can be found by
    section: str = ""               # shown dimmed: Chapter, Item, Text, …
    order: int = field(default=0)   # position when nothing is typed


def _words(text):
    return text.casefold().replace("…", " ").replace("/", " ").split()


def score(query, cmd):
    """Lower is better; None if cmd doesn't match."""
    q = _words(query)
    if not q:
        return cmd.order
    title = cmd.title.casefold()
    title_words = _words(cmd.title)
    other = _words(cmd.keywords) + _words(cmd.section)
    total = 0
    for w in q:
        if any(t.startswith(w) for t in title_words):
            total += 0 if title.startswith(w) else 1
        elif w in title:
            total += 3
        elif any(t.startswith(w) for t in other):
            total += 4
        else:
            return None
    return total * 1000 + len(cmd.title)


def search(query, commands):
    """Matching commands, best first."""
    ranked = [(s, i, c) for i, c in enumerate(commands) if (s := score(query, c)) is not None]
    ranked.sort(key=lambda t: (t[0], t[1]))
    return [c for _s, _i, c in ranked]
