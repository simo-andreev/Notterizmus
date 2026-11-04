"""Spell checking through Enchant (the engine GNOME apps use; Hunspell dictionaries).

Talks to libenchant-2 via ctypes so no extra Python packages are needed.
"Add to dictionary" writes to Enchant's personal word list, shared with other apps.
"""
from __future__ import annotations

import ctypes
import re

WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")

LANG_NAMES = {
    "en_US": "English (US)", "en_GB": "English (UK)", "en_AU": "English (Australia)",
    "en_CA": "English (Canada)", "bg_BG": "Bulgarian", "bg": "Bulgarian", "de_DE": "German",
    "fr": "French", "fr_FR": "French (France)", "fr_BE": "French (Belgium)", "fr_CA": "French (Canada)",
    "fr_CH": "French (Switzerland)", "fr_LU": "French (Luxembourg)", "fr_MC": "French (Monaco)",
    "es_ES": "Spanish", "it_IT": "Italian", "ru_RU": "Russian", "pt_PT": "Portuguese",
    "pt_BR": "Portuguese (Brazil)", "nl_NL": "Dutch", "pl_PL": "Polish", "uk_UA": "Ukrainian",
}

_DESCRIBE = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                             ctypes.c_char_p, ctypes.c_void_p)


_CYRILLIC_LANGS = ("bg", "ru", "uk", "sr", "mk", "be")


def should_check(word):
    return len(word) > 1 and not word.isupper()


def script_of_word(word):
    return "cyrillic" if any("\u0400" <= c <= "\u04ff" for c in word) else "latin"


def script_of_lang(tag):
    return "cyrillic" if tag and tag.split("_")[0] in _CYRILLIC_LANGS else "latin"


def guess_language(text, languages):
    """Pick a dictionary for a text by which alphabet dominates."""
    cyr = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    lat = sum(1 for c in text if c.isascii() and c.isalpha())
    want = "cyrillic" if cyr > lat else "latin"
    prefs = ("bg_BG", "bg", "ru_RU", "uk_UA") if want == "cyrillic" else ("en_US", "en_GB", "en")
    for p in prefs:
        if p in languages:
            return p
    return next((t for t in languages if script_of_lang(t) == want), None)


class Speller:
    def __init__(self):
        self.lib = None
        self.broker = None
        self.dict = None
        self.lang = None
        self._dicts = {}   # tag -> EnchantDict*
        self._alt = {}     # script -> tag used for words in the other alphabet
        self._cache = {}
        try:
            lib = ctypes.CDLL("libenchant-2.so.2")
        except OSError:
            return
        vp, cp, ss = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_ssize_t
        lib.enchant_broker_init.restype = vp
        lib.enchant_broker_request_dict.argtypes = [vp, cp]
        lib.enchant_broker_request_dict.restype = vp
        lib.enchant_broker_free_dict.argtypes = [vp, vp]
        lib.enchant_broker_list_dicts.argtypes = [vp, _DESCRIBE, vp]
        lib.enchant_dict_check.argtypes = [vp, cp, ss]
        lib.enchant_dict_check.restype = ctypes.c_int
        lib.enchant_dict_suggest.argtypes = [vp, cp, ss, ctypes.POINTER(ctypes.c_size_t)]
        lib.enchant_dict_suggest.restype = ctypes.POINTER(cp)
        lib.enchant_dict_free_string_list.argtypes = [vp, ctypes.POINTER(cp)]
        lib.enchant_dict_add.argtypes = [vp, cp, ss]
        lib.enchant_dict_add_to_session.argtypes = [vp, cp, ss]
        self.lib = lib
        self.broker = lib.enchant_broker_init()

    @property
    def available(self):
        return bool(self.broker)

    def languages(self):
        if not self.broker:
            return []
        tags = []
        cb = _DESCRIBE(lambda tag, *_: tags.append(tag.decode()))
        self.lib.enchant_broker_list_dicts(self.broker, cb, None)
        # hide dictionary sub-variants such as en_US-variant_0 / en_GB-ize
        return sorted({t for t in tags if re.fullmatch(r"[a-z]{2,3}(_[A-Z]{2})?", t)})

    @staticmethod
    def language_name(tag):
        return LANG_NAMES.get(tag, tag)

    def _get(self, tag):
        if tag not in self._dicts:
            self._dicts[tag] = self.lib.enchant_broker_request_dict(self.broker, tag.encode()) or None
        return self._dicts[tag]

    def set_language(self, tag):
        """Primary language. Words in the other alphabet (Latin/Cyrillic) are checked
        with a matching installed dictionary, so mixed notes are not all red."""
        if not self.broker:
            return False
        self._cache.clear()
        self.lang, self.dict = None, None
        if tag and self._get(tag):
            self.lang, self.dict = tag, self._get(tag)
        langs = self.languages()
        self._alt = {}
        for script in ("latin", "cyrillic"):
            if self.lang and script_of_lang(self.lang) == script:
                self._alt[script] = self.lang
            else:
                self._alt[script] = guess_language("а" if script == "cyrillic" else "a", langs)
        return self.dict is not None

    def _dict_for(self, word):
        tag = self._alt.get(script_of_word(word)) or self.lang
        return self._get(tag) if tag else None

    @staticmethod
    def _b(word):
        return word.replace("’", "'").encode()

    def check(self, word):
        if not self.dict:
            return True
        hit = self._cache.get(word)
        if hit is None:
            d = self._dict_for(word)
            b = self._b(word)
            hit = self._cache[word] = (d is None) or self.lib.enchant_dict_check(d, b, len(b)) == 0
        return hit

    def suggest(self, word, limit=6):
        d = self._dict_for(word) if self.dict else None
        if not d:
            return []
        b = self._b(word)
        n = ctypes.c_size_t()
        arr = self.lib.enchant_dict_suggest(d, b, len(b), ctypes.byref(n))
        if not arr:
            return []
        out = [arr[i].decode() for i in range(min(n.value, limit))]
        self.lib.enchant_dict_free_string_list(d, arr)
        return out

    def add(self, word):
        d = self._dict_for(word) if self.dict else None
        if d:
            b = self._b(word)
            self.lib.enchant_dict_add(d, b, len(b))
            self._cache[word] = True

    def ignore(self, word):
        d = self._dict_for(word) if self.dict else None
        if d:
            b = self._b(word)
            self.lib.enchant_dict_add_to_session(d, b, len(b))
            self._cache[word] = True
