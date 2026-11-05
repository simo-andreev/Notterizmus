import json
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


if __name__ == "__main__":
    unittest.main()
