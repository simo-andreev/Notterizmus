"""Spell checking: which words are checked and with which dictionary. The Speller is run
against a stand-in for libenchant, so these don't depend on the dictionaries installed."""
import ctypes
import types
import unittest
from unittest import mock

from notterizmus import spell
from notterizmus.spell import (WORD_RE, Speller, guess_language, pick_language, script_of_lang, script_of_word,
                               should_check)


def words(text):
    return [m.group() for m in WORD_RE.finditer(text)]


class WordsTest(unittest.TestCase):
    def test_words_are_runs_of_letters_in_any_alphabet(self):
        self.assertEqual(words("Scaling the база данни, naïve café!"), ["Scaling", "the", "база", "данни", "naïve", "café"])

    def test_digits_and_underscores_split_words(self):
        self.assertEqual(words("x86_64 v2 3D utf8"), ["x", "v", "D", "utf"])

    def test_an_apostrophe_inside_a_word_belongs_to_it(self):
        self.assertEqual(words("don't it’s o'clock 'quoted' rock'"), ["don't", "it’s", "o'clock", "quoted", "rock"])

    def test_single_letters_and_all_capitals_are_not_checked(self):
        self.assertEqual([should_check(w) for w in ("a", "I", "SDI", "HTTP", "Sdi", "ok", "Я", "ДА", "да")],
                         [False, False, False, False, True, True, False, False, True])

    def test_the_alphabet_of_a_word_and_of_a_language(self):
        self.assertEqual([script_of_word(w) for w in ("scale", "мащаб", "mix и")], ["latin", "cyrillic", "cyrillic"])
        self.assertEqual([script_of_lang(t) for t in ("bg_BG", "bg", "ru_RU", "uk_UA", "en_US", "de_DE", "", None)],
                         ["cyrillic", "cyrillic", "cyrillic", "cyrillic", "latin", "latin", "latin", "latin"])


class GuessLanguageTest(unittest.TestCase):
    LANGS = ["bg_BG", "de_DE", "en_GB", "en_US", "ru_RU"]

    def test_the_dominant_alphabet_decides(self):
        self.assertEqual(guess_language("Scaling is hard", self.LANGS), "en_US")
        self.assertEqual(guess_language("Мащабирането е трудно", self.LANGS), "bg_BG")
        self.assertEqual(guess_language("Kafka е брокер на съобщения", self.LANGS), "bg_BG")
        self.assertEqual(guess_language("The term мащаб means scale in Bulgarian", self.LANGS), "en_US")

    def test_text_without_letters_counts_as_latin(self):
        self.assertEqual(guess_language("", self.LANGS), "en_US")
        self.assertEqual(guess_language("123 → 456", self.LANGS), "en_US")

    def test_preferred_dictionaries_come_first_then_any_of_the_same_alphabet(self):
        self.assertEqual(guess_language("text", ["de_DE", "en_GB"]), "en_GB")
        self.assertEqual(guess_language("text", ["bg_BG", "de_DE", "fr_FR"]), "de_DE")
        self.assertEqual(guess_language("текст", ["en_US", "uk_UA", "ru_RU"]), "ru_RU")
        self.assertEqual(guess_language("текст", ["en_US", "sr", "de_DE"]), "sr")

    def test_no_dictionary_for_the_alphabet(self):
        self.assertIsNone(guess_language("текст", ["en_US", "de_DE"]))
        self.assertIsNone(guess_language("text", []))


class PickLanguageTest(unittest.TestCase):
    """A chapter's dictionary, for its notes and for the answers to its assessment (R35a)."""
    LANGS = ["bg_BG", "de_DE", "en_GB", "en_US"]

    def test_the_chapters_own_choice_comes_first(self):
        self.assertEqual(pick_language("de_DE", "Мащабирането е трудно", self.LANGS, "en_GB"), "de_DE")

    def test_a_choice_whose_dictionary_is_gone_falls_back_to_the_text(self):
        self.assertEqual(pick_language("fr_FR", "Мащабирането е трудно", self.LANGS), "bg_BG")

    def test_without_text_the_last_choice_then_english_then_any(self):
        self.assertEqual(pick_language(None, "", self.LANGS, "en_GB"), "en_GB")
        self.assertEqual(pick_language(None, "123", self.LANGS, "fr_FR"), "en_US")
        self.assertEqual(pick_language(None, "", ["de_DE", "fr_FR"]), "de_DE")
        self.assertIsNone(pick_language("en_US", "text", []))


class FakeEnchant:
    """What Speller uses of libenchant-2: a broker with dictionaries, each a set of words."""

    def __init__(self, dicts):
        self.dicts = {tag: set(known) for tag, known in dicts.items()}
        self.handles = {}       # handle -> tag
        self.session = {}       # tag -> words ignored for the session
        self.personal = {}      # tag -> words added to the personal list
        self.checked = []       # (tag, word) of every lookup that reached the library
        self.freed = 0
        lib = types.SimpleNamespace()

        def known(handle, raw):
            tag = self.handles[handle]
            word = raw.decode()
            return word in self.dicts[tag] or word in self.session.get(tag, ()) or word in self.personal.get(tag, ())

        def request(_broker, tag):
            tag = tag.decode()
            if tag not in self.dicts:
                return None
            handle = 1000 + len(self.handles)
            self.handles[handle] = tag
            return handle

        def check(handle, raw, length):
            assert length == len(raw), "the length is in bytes"
            self.checked.append((self.handles[handle], raw.decode()))
            return 0 if known(handle, raw) else 1

        def suggest(handle, raw, _length, count):
            found = sorted(w for w in self.dicts[self.handles[handle]] if w[:2] == raw.decode()[:2])
            count._obj.value = len(found)
            return [w.encode() for w in found] or None

        def free_list(_handle, _array):
            self.freed += 1

        lib.enchant_broker_init = lambda: 1
        lib.enchant_broker_request_dict = request
        lib.enchant_broker_free_dict = lambda *_: None
        lib.enchant_broker_list_dicts = lambda _b, cb, _d: [cb(t.encode(), b"", b"", b"", None) for t in self.listed()]
        lib.enchant_dict_check = check
        lib.enchant_dict_suggest = suggest
        lib.enchant_dict_free_string_list = free_list
        lib.enchant_dict_add = lambda h, raw, _n: self.personal.setdefault(self.handles[h], set()).add(raw.decode())
        lib.enchant_dict_add_to_session = lambda h, raw, _n: self.session.setdefault(self.handles[h], set()).add(raw.decode())
        self.lib = lib

    def listed(self):
        # Enchant also lists variants of a dictionary; the app hides those
        return [*self.dicts, "en_US-variant_0", "en_GB-ize", "sr@latin"]


def speller(dicts):
    fake = FakeEnchant(dicts)
    with mock.patch.object(ctypes, "CDLL", return_value=fake.lib):
        return Speller(), fake


EN = {"scale", "the", "don't", "hello"}
BG = {"мащаб", "здравей"}


class SpellerTest(unittest.TestCase):
    def test_lists_whole_languages_only(self):
        sp, _fake = speller({"en_US": EN, "bg_BG": BG, "de_DE": set()})
        self.assertTrue(sp.available)
        self.assertEqual(sp.languages(), ["bg_BG", "de_DE", "en_US"])

    def test_language_names(self):
        self.assertEqual(Speller.language_name("bg_BG"), "Bulgarian")
        self.assertEqual(Speller.language_name("en_US"), "English (US)")
        self.assertEqual(Speller.language_name("xx_YY"), "xx_YY", "an unknown tag is shown as it is")
        for tag, name in spell.LANG_NAMES.items():
            self.assertTrue(name and name != tag)

    def test_checks_words_in_the_chosen_language(self):
        sp, _fake = speller({"en_US": EN})
        self.assertTrue(sp.set_language("en_US"))
        self.assertEqual(sp.lang, "en_US")
        self.assertTrue(sp.check("scale"))
        self.assertFalse(sp.check("scael"))

    def test_words_in_the_other_alphabet_use_a_matching_dictionary(self):
        sp, fake = speller({"en_US": EN, "bg_BG": BG})
        sp.set_language("en_US")
        self.assertEqual((sp.tag_for("scale"), sp.tag_for("мащаб")), ("en_US", "bg_BG"))
        self.assertTrue(sp.check("мащаб"))
        self.assertFalse(sp.check("мащап"))
        self.assertIn(("bg_BG", "мащаб"), fake.checked)
        sp.set_language("bg_BG")
        self.assertEqual((sp.tag_for("scale"), sp.tag_for("мащаб")), ("en_US", "bg_BG"))
        self.assertFalse(sp.check("scael"), "Latin words still go to the English dictionary")

    def test_with_one_dictionary_installed_it_checks_its_own_alphabet(self):
        sp, fake = speller({"bg_BG": BG})
        self.assertTrue(sp.set_language("bg_BG"))
        self.assertTrue(sp.check("мащаб"))
        self.assertFalse(sp.check("мащап"))
        self.assertEqual({tag for tag, _w in fake.checked}, {"bg_BG"})

    def test_a_curly_apostrophe_is_checked_as_a_straight_one(self):
        sp, fake = speller({"en_US": EN})
        sp.set_language("en_US")
        self.assertTrue(sp.check("don’t"))
        self.assertEqual(fake.checked, [("en_US", "don't")])

    def test_each_word_is_looked_up_once(self):
        sp, fake = speller({"en_US": EN})
        sp.set_language("en_US")
        for _ in range(3):
            sp.check("scale")
            sp.check("scael")
        self.assertEqual(len(fake.checked), 2)

    def test_changing_the_language_forgets_earlier_answers(self):
        sp, _fake = speller({"en_US": EN, "en_GB": EN | {"colour"}})
        sp.set_language("en_US")
        self.assertFalse(sp.check("colour"))
        sp.set_language("en_GB")
        self.assertTrue(sp.check("colour"))

    def test_an_unknown_language_turns_checking_off(self):
        sp, _fake = speller({"en_US": EN})
        self.assertFalse(sp.set_language("xx_XX"))
        self.assertIsNone(sp.lang)
        self.assertTrue(sp.check("scael"), "nothing is marked without a dictionary")
        self.assertEqual(sp.suggest("scael"), [])
        self.assertFalse(sp.set_language(None))

    def test_suggestions_are_limited_and_the_list_is_given_back(self):
        sp, fake = speller({"en_US": {"scab", "scale", "scald", "scalp", "scam", "scan", "scar", "scat"}})
        sp.set_language("en_US")
        self.assertEqual(sp.suggest("scxx"), ["scab", "scald", "scale", "scalp", "scam", "scan"])
        self.assertEqual(sp.suggest("scxx", limit=2), ["scab", "scald"])
        self.assertEqual(fake.freed, 2, "Enchant's list is freed each time")
        self.assertEqual(sp.suggest("zzzz"), [])

    def test_ignoring_a_word_lasts_for_the_session_and_adding_goes_to_the_personal_list(self):
        sp, fake = speller({"en_US": EN, "bg_BG": BG})
        sp.set_language("en_US")
        self.assertFalse(sp.check("Notterizmus"))
        sp.ignore("Notterizmus")
        self.assertTrue(sp.check("Notterizmus"))
        self.assertEqual(fake.session, {"en_US": {"Notterizmus"}})
        self.assertFalse(sp.check("шардинг"))
        sp.add("шардинг")
        self.assertTrue(sp.check("шардинг"))
        self.assertEqual(fake.personal, {"bg_BG": {"шардинг"}}, "added to the dictionary of the word's alphabet")

    def test_without_enchant_everything_passes_quietly(self):
        with mock.patch.object(ctypes, "CDLL", side_effect=OSError("no libenchant")):
            sp = Speller()
        self.assertFalse(sp.available)
        self.assertEqual(sp.languages(), [])
        self.assertFalse(sp.set_language("en_US"))
        self.assertTrue(sp.check("anything"))
        self.assertEqual(sp.suggest("anything"), [])
        sp.add("word")
        sp.ignore("word")
        self.assertIsNone(sp.tag_for("word"))


class RealEnchantTest(unittest.TestCase):
    """The same through the real library, if it and an English dictionary are installed."""

    def setUp(self):
        self.sp = Speller()
        if not self.sp.available or "en_US" not in self.sp.languages():
            self.skipTest("no en_US dictionary")
        self.sp.set_language("en_US")

    def test_checks_and_suggests(self):
        self.assertTrue(self.sp.check("architecture"))
        self.assertTrue(self.sp.check("don’t"))
        self.assertFalse(self.sp.check("architecure"))
        self.assertIn("architecture", self.sp.suggest("architecure", limit=10))
        self.assertLessEqual(len(self.sp.suggest("architecure", limit=3)), 3)

    def test_ignoring_a_word_for_the_session(self):
        word = "zzyzxqword"
        self.assertFalse(self.sp.check(word))
        self.sp.ignore(word)  # session only: nothing is written to your word list
        self.assertTrue(self.sp.check(word))


if __name__ == "__main__":
    unittest.main()
