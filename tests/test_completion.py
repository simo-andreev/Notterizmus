import tempfile
import unittest
from collections import Counter
from pathlib import Path

from notterizmus.completion import BookWords, complete, count_words, dictionary_words, node_texts
from notterizmus.model import Document, Node, Run


class CompletionTest(unittest.TestCase):
    def test_document_words_rank_by_frequency(self):
        cur = count_words(["scalability scaling scale", "Scaling again"])
        self.assertEqual(complete("sca", cur), ["scaling", "scalability", "scale"])
        self.assertEqual(complete("Sca", cur)[0], "Scaling")

    def test_sentence_start_capital_is_not_kept(self):
        cur = count_words(["Scaling is hard. Replication helps", "used with Kafka and kafka-like tools: Sharding"])
        self.assertIn("scaling", cur)
        self.assertIn("replication", cur)
        self.assertIn("sharding", cur)
        self.assertEqual(cur["Kafka"], 1)  # capital mid-sentence stays
        self.assertEqual(complete("sca", cur), ["scaling"])

    def test_case_follows_prefix_and_excludes_prefix(self):
        cur = Counter({"replication": 3, "replica": 1})
        self.assertEqual(complete("Repl", cur), ["Replication", "Replica"])
        self.assertEqual(complete("replica", cur), ["replication"])
        self.assertEqual(complete("replicatio", cur), [])  # adds only one letter

    def test_cyrillic(self):
        cur = count_words(["репликация репликация реплика"])
        self.assertEqual(complete("репл", cur), ["репликация", "реплика"])

    def test_sources_in_order_and_limit(self):
        got = complete("da", Counter({"database": 1}), Counter({"datacenter": 5}),
                       [("dark", "dark"), ("data", "data"), ("database", "database")], limit=3)
        self.assertEqual(got, ["database", "datacenter", "dark"])

    def test_skips_tiny_gains_and_lowercase_proper_nouns(self):
        words = [("intel", "Intel"), ("intern", "intern"), ("interval", "interval")]
        self.assertEqual(complete("inte", Counter(), None, words), ["intern", "interval"])  # no "Intel"
        self.assertEqual(complete("Inte", Counter(), None, words), ["Intern", "Interval"])

    def test_node_texts_includes_tables(self):
        t = Node("table", data={"rows": [[[Run("throughput")]]]})
        root = Node("root", children=[Node("heading", [Run("latency")], children=[t])])
        self.assertEqual(set(count_words(node_texts(root))), {"latency", "throughput"})

    def test_book_words_skip_current_file(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "01.notz"
            b = Path(d) / "02.notz"
            Document(Node("root", children=[Node("heading", [Run("sharding")])])).save(a)
            Document(Node("root", children=[Node("heading", [Run("consistency")])])).save(b)
            words = BookWords().counts(d, exclude=a)
            self.assertIn("consistency", words)
            self.assertNotIn("sharding", words)

    def test_dictionary_if_installed(self):
        words = dictionary_words("en_US")
        if not words:
            self.skipTest("en_US hunspell dictionary not installed")
        self.assertIn("architecture", complete("architec", Counter(), None, words))


class RankingTest(unittest.TestCase):
    def test_nothing_typed_gives_nothing(self):
        self.assertEqual(complete("", Counter({"abc": 1})), [])

    def test_spellings_that_differ_only_in_case_are_offered_once(self):
        cur = Counter({"kafka": 1, "Kafka": 3, "KAFKA": 1})
        self.assertEqual(complete("ka", cur), ["kafka"])
        self.assertEqual(complete("Ka", cur), ["Kafka"])

    def test_a_word_from_the_chapter_is_not_repeated_from_the_book_or_dictionary(self):
        got = complete("ab", Counter({"abcd": 2}), Counter({"abcd": 5, "abzz": 1}),
                       [("abcd", "abcd"), ("abqq", "abqq"), ("abzz", "abzz")])
        self.assertEqual(got, ["abcd", "abzz", "abqq"])

    def test_at_most_eight_are_offered(self):
        cur = Counter({f"sca{i:02d}x": 1 for i in range(20)})
        self.assertEqual(len(complete("sca", cur)), 8)
        self.assertEqual(len(complete("sca", cur, limit=3)), 3)

    def test_equally_frequent_words_come_in_alphabetical_order(self):
        self.assertEqual(complete("re", Counter({"replica": 1, "reads": 1, "redo": 1})), ["reads", "redo", "replica"])

    def test_the_dictionary_needs_two_letters_typed(self):
        words = [("abacus", "abacus"), ("abbey", "abbey")]
        self.assertEqual(complete("a", Counter(), None, words), [])
        self.assertEqual(complete("ab", Counter(), None, words), ["abbey", "abacus"], "shorter words first")

    def test_the_word_being_typed_is_never_its_own_completion(self):
        self.assertEqual(complete("scale", Counter({"scale": 5, "Scale": 1, "scales": 2, "scaleout": 1})), ["scaleout"])


class CountWordsTest(unittest.TestCase):
    def test_short_words_are_not_counted(self):
        self.assertEqual(set(count_words(["to be or not at all"])), {"not", "all"})

    def test_a_capital_after_a_sentence_end_a_colon_or_an_opening_quote_is_dropped(self):
        got = count_words(['First item. Second sentence! Third? Note: Fourth', '("Quoted start'])
        self.assertEqual(set(got), {"first", "item", "second", "sentence", "third", "note", "fourth", "quoted", "start"})

    def test_names_acronyms_and_mixed_case_keep_their_capitals(self):
        got = count_words(["we use Kafka, HTTP and gRPC with PostgreSQL"])
        self.assertEqual({w for w in got if not w.islower()}, {"Kafka", "HTTP", "gRPC", "PostgreSQL"})

    def test_apostrophes_stay_inside_words(self):
        self.assertEqual(count_words(["the client's don’t"]), Counter({"the": 1, "client's": 1, "don’t": 1}))


class BookWordsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def chapter(self, name, *texts, table=None):
        kids = [Node("heading", [Run(t)]) for t in texts]
        if table:
            kids.append(Node("table", data={"rows": [[[Run(c)] for c in row] for row in table]}))
        path = self.dir / name
        Document(Node("root", children=kids)).save(path)
        return path

    def test_counts_add_up_across_the_other_chapters_tables_included(self):
        self.chapter("01.notz", "sharding sharding")
        self.chapter("02.notz", "sharding replica", table=[["throughput", "latency"]])
        words = BookWords().counts(self.dir)
        self.assertEqual(words, Counter({"sharding": 3, "replica": 1, "throughput": 1, "latency": 1}))

    def test_nested_items_are_read(self):
        path = self.dir / "01.notz"
        Document(Node("root", children=[Node("heading", [Run("outer")], children=[
            Node("bullet", [Run("inner")], children=[Node("bullet", [Run("innermost")])])])])).save(path)
        self.assertEqual(set(BookWords().counts(self.dir)), {"outer", "inner", "innermost"})

    def test_a_changed_chapter_is_read_again_and_an_unchanged_one_is_not(self):
        import os
        path = self.chapter("01.notz", "before")
        book = BookWords()
        self.assertEqual(set(book.counts(self.dir)), {"before"})
        self.chapter("01.notz", "after")
        os.utime(path, (1, 1))  # a different modification time, whatever the clock's resolution
        self.assertEqual(set(book.counts(self.dir)), {"after"})
        path.write_text("{}", encoding="utf-8")
        os.utime(path, (1, 1))  # same time as when it was last read: the cached counts are used
        self.assertEqual(set(book.counts(self.dir)), {"after"})

    def test_files_that_are_not_chapters_are_skipped(self):
        self.chapter("01.notz", "kept")
        (self.dir / "broken.notz").write_text("{not json", encoding="utf-8")
        (self.dir / "list.notz").write_text("[1, 2]", encoding="utf-8")
        (self.dir / "null.notz").write_text("null", encoding="utf-8")
        (self.dir / "odd.notz").write_text('{"content": [{"kind": "heading", "runs": "text"}]}', encoding="utf-8")
        (self.dir / "notes.txt").write_text("ignored words", encoding="utf-8")
        self.assertEqual(set(BookWords().counts(self.dir)), {"kept"})

    def test_no_folder_no_words(self):
        self.assertEqual(BookWords().counts(None), Counter())
        self.assertEqual(BookWords().counts(self.dir / "missing"), Counter())


class DictionaryWordsTest(unittest.TestCase):
    """Reading a Hunspell .dic word list, from a made-up dictionary in a scratch folder."""

    def setUp(self):
        import os
        from notterizmus import completion
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.share = Path(tmp.name) / "share"
        (self.share / "hunspell").mkdir(parents=True)
        saved_env, saved_cache = os.environ.get("XDG_DATA_DIRS"), dict(completion._DICT_CACHE)
        os.environ["XDG_DATA_DIRS"] = f"{tmp.name}/missing::{self.share}"
        completion._DICT_CACHE.clear()

        def restore():
            completion._DICT_CACHE.clear()
            completion._DICT_CACHE.update(saved_cache)
            if saved_env is None:
                del os.environ["XDG_DATA_DIRS"]
            else:
                os.environ["XDG_DATA_DIRS"] = saved_env
        self.addCleanup(restore)

    def dictionary(self, tag, entries, encoding="utf-8", aff=None):
        body = f"{len(entries)}\n" + "\n".join(entries) + "\n" + "# padding so the file isn't taken for a stub\n" * 4
        (self.share / "hunspell" / f"{tag}.dic").write_bytes(body.encode(encoding))
        if aff is not None:
            (self.share / "hunspell" / f"{tag}.aff").write_text(aff, encoding="latin-1")

    def test_stems_are_listed_without_flags_and_sorted_ignoring_case(self):
        self.dictionary("xx_XX", ["zebra/S", "Apple/M", "apple", "banana po:noun", "cherry\ttab"])
        self.assertEqual(dictionary_words("xx_XX"),
                         [("apple", "Apple"), ("apple", "apple"), ("banana", "banana"), ("cherry", "cherry"),
                          ("zebra", "zebra")])

    def test_short_entries_numbers_and_repeats_are_left_out(self):
        self.dictionary("xx_XX", ["ab", "x1y", "3rd", "word/A", "word/B", "", "o'clock"])
        self.assertEqual([w for _k, w in dictionary_words("xx_XX")], ["o'clock", "word"])

    def test_an_aff_file_naming_no_or_an_unknown_encoding_is_skipped_safely(self):
        """A bare SET raised IndexError, and an encoding Python doesn't know LookupError
        (CR27)."""
        self.dictionary("xx_XX", ["word"], aff="SET \n")
        self.assertEqual([w for _k, w in dictionary_words("xx_XX")], ["word"], "taken as UTF-8")
        self.dictionary("yy_YY", ["word"], aff="SET no-such-encoding-9\n")
        self.assertEqual(dictionary_words("yy_YY"), [])

    def test_the_encoding_comes_from_the_aff_file(self):
        self.dictionary("bg_XX", ["котка/AB", "куче", "Кирил/X"], encoding="cp1251",
                        aff="# Bulgarian\nSET microsoft-cp1251\nTRY abc\n")
        words = dictionary_words("bg_XX")
        self.assertEqual([w for _k, w in words], ["Кирил", "котка", "куче"])
        self.assertEqual(complete("ко", Counter(), None, words), ["котка"])
        self.assertEqual(complete("Ки", Counter(), None, words), ["Кирил"])
        self.assertEqual(complete("ки", Counter(), None, words), [], "a name isn't offered for a lowercase start")

    def test_a_missing_or_stub_dictionary_has_no_words(self):
        (self.share / "hunspell" / "tiny.dic").write_text("1\nabc\n", encoding="utf-8")
        self.assertEqual(dictionary_words("tiny"), [])
        self.assertEqual(dictionary_words("zz_ZZ"), [])
        self.assertEqual(dictionary_words(""), [])
        self.assertEqual(dictionary_words(None), [])

    def test_a_word_list_is_read_once(self):
        self.dictionary("xx_XX", ["first", "second"])
        words = dictionary_words("xx_XX")
        self.dictionary("xx_XX", ["changed", "entirely"])
        self.assertIs(dictionary_words("xx_XX"), words)


if __name__ == "__main__":
    unittest.main()
