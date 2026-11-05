"""Word completion for Ctrl+Space (no GTK).

Candidates come, in this order, from the open chapter, the other chapters of the
same book (book-specific terms recur), and the Hunspell dictionary's word list.
"""
from __future__ import annotations

import bisect
import json
import os
from collections import Counter
from pathlib import Path

from .spell import WORD_RE

MIN_WORD = 3        # shorter words aren't worth completing
MIN_DICT_PREFIX = 2  # dictionary completions only after this many letters
MIN_GAIN = 2         # a completion must add at least this many letters


def node_texts(root):
    """All text in an outline tree: items and table cells."""
    for n in root.walk():
        if n.runs:
            yield "".join(r.text for r in n.runs)
        for row in n.data.get("rows", []) if n.kind == "table" else []:
            for cell in row:
                yield "".join(r.text for r in cell)


def _json_texts(items):
    for it in items:
        for key in ("runs",):
            if it.get(key):
                yield "".join(r.get("t", "") for r in it[key])
        for row in (it.get("data") or {}).get("rows", []):
            for cell in row:
                yield "".join(r.get("t", "") for r in cell)
        yield from _json_texts(it.get("children", []))


def count_words(texts):
    """Word counts. A capital that's only there because the word starts the item or
    a sentence ("Scaling is…") is dropped; capitals elsewhere ("…with Kafka") stay."""
    c = Counter()
    for t in texts:
        for m in WORD_RE.finditer(t):
            w = m.group()
            if len(w) < MIN_WORD:
                continue
            before = t[:m.start()].rstrip(" \t\u00a0\"'“‘(")
            if w[:1].isupper() and w[1:].islower() and (not before or before[-1] in ".!?:"):
                w = w.lower()
            c[w] += 1
    return c


class BookWords:
    """Word counts of the other .notz files in a book folder, cached by mtime."""

    def __init__(self):
        self._files = {}

    def counts(self, folder, exclude=None):
        total = Counter()
        if not folder or not Path(folder).is_dir():
            return total
        for p in Path(folder).glob("*.notz"):
            if exclude is not None and p.resolve() == Path(exclude).resolve():
                continue
            try:
                mtime = p.stat().st_mtime
                hit = self._files.get(p)
                if hit is None or hit[0] != mtime:
                    with open(p, encoding="utf-8") as f:
                        content = json.load(f).get("content", [])
                    hit = self._files[p] = (mtime, count_words(_json_texts(content)))
                total.update(hit[1])
            except (OSError, ValueError):
                continue
        return total


_DICT_CACHE = {}


def _dic_dirs():
    dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    return [Path(d) / "hunspell" for d in dirs + ["/usr/share"] if d]


def dictionary_words(tag):
    """Sorted, lower-cased-key list of (key, word) from <tag>.dic stems; cached."""
    if not tag:
        return []
    if tag in _DICT_CACHE:
        return _DICT_CACHE[tag]
    words = []
    for d in _dic_dirs():
        dic = d / f"{tag}.dic"
        if not dic.is_file() or dic.stat().st_size < 100:
            continue
        enc = "utf-8"
        try:
            for line in open(d / f"{tag}.aff", encoding="latin-1"):
                if line.startswith("SET "):
                    enc = line.split()[1].replace("microsoft-", "")
                    break
        except OSError:
            pass
        seen = set()
        with open(dic, encoding=enc, errors="replace") as f:
            next(f, None)  # entry count
            for line in f:
                w = line.split("/", 1)[0].split(None, 1)[0] if line.strip() else ""
                if len(w) >= MIN_WORD and WORD_RE.fullmatch(w) and w not in seen:
                    seen.add(w)
                    words.append((w.casefold(), w))
        break
    words.sort()
    _DICT_CACHE[tag] = words
    return words


def _ranked(prefix, key, counts):
    """Matching words, most frequent first; spellings that differ only in case are
    merged, preferring the lowercase form unless the prefix is capitalised."""
    groups = {}
    for w, n in counts.items():
        k = w.casefold()
        if k.startswith(key):
            g = groups.setdefault(k, [0, []])
            g[0] += n
            g[1].append(w)
    lower_first = not prefix[:1].isupper()
    ranked = []
    for k, (n, forms) in groups.items():
        forms.sort(key=lambda w: (not w[:1].islower(), -counts[w]) if lower_first else -counts[w])
        ranked.append((-n, k, forms[0]))
    return [w for _, _, w in sorted(ranked)]


def _match_case(prefix, word):
    if prefix[:1].isupper() and word[:1].islower():
        return word[:1].upper() + word[1:]
    return word


def complete(prefix, current, book=None, dict_words=None, limit=8):
    """Completions for `prefix`, best first, without repeats or the prefix itself.

    current/book: Counters of words; dict_words: output of dictionary_words().
    """
    key = prefix.casefold()
    if not key:
        return []
    out, seen = [], {key}

    def take(words, proper_ok=True):
        for w in words:
            k = w.casefold()
            if not proper_ok and w[:1].isupper():
                continue  # dictionary proper nouns only for a capitalised prefix
            if k.startswith(key) and k not in seen and len(w) >= len(prefix) + MIN_GAIN:
                seen.add(k)
                out.append(_match_case(prefix, w))
                if len(out) >= limit:
                    return True
        return False

    for counts in (current, book):
        if counts:
            if take(_ranked(prefix, key, counts)):
                return out
    if dict_words and len(prefix) >= MIN_DICT_PREFIX:
        i = bisect.bisect_left(dict_words, (key, ""))
        cands = []
        while i < len(dict_words) and dict_words[i][0].startswith(key) and len(cands) < 2000:
            cands.append(dict_words[i][1])
            i += 1
        cands.sort(key=lambda w: (len(w), w.casefold()))  # shorter, more common forms first
        take(cands, proper_ok=prefix[:1].isupper())
    return out
