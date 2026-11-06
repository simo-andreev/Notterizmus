"""Find and replace: where a query matches in a piece of text (no GTK)."""
from __future__ import annotations

import re


def pattern(query, case=False, whole=False):
    """A compiled pattern for the query, or None for an empty query. Whole words use
    Unicode word characters, so Cyrillic works too."""
    if not query:
        return None
    body = re.escape(query)
    if whole:
        body = rf"(?<!\w){body}(?!\w)"
    return re.compile(body, 0 if case else re.IGNORECASE)


def find_all(text, query, case=False, whole=False):
    """[(start, end)] of non-overlapping matches in text."""
    pat = pattern(query, case, whole)
    return [] if pat is None else [m.span() for m in pat.finditer(text)]


def clean_replacement(text):
    """Items are single paragraphs: line breaks in a replacement become spaces."""
    return " ".join(text.splitlines()) if text else ""
