"""
tests/test_phrasefinder.py
"""

import time
import pickle
import tempfile
import statistics
from pathlib import Path

import pytest
from phrasefinder import PhraseFinder, Hit

EXAMPLES = Path(__file__).parent.parent / "examples"
REF_FILE = EXAMPLES / "ref_phrases.txt"

# ── helpers ───────────────────────────────────────────────────────────────────

def latency(fn, n=500) -> dict:
    times = sorted((time.perf_counter(), fn(), time.perf_counter())[2] - (time.perf_counter(), fn(), time.perf_counter())[0] for _ in range(n))
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1_000_000)
    times.sort()
    def p(pct): return times[int(len(times) * pct / 100)]
    return dict(min=times[0], mean=statistics.mean(times), p50=p(50),
                p95=p(95), p99=p(99), max=times[-1], n=n)

# ── labeled mode ──────────────────────────────────────────────────────────────

class TestLabeledMode:

    def test_basic_hit(self):
        f = PhraseFinder([("book", "a book called"), ("paper", "a study on")])
        hits = f.find("she wrote a book called dune")
        assert len(hits) == 1
        assert hits[0].label == "book"
        assert hits[0].phrase == "a book called"

    def test_multiple_labels_same_chunk(self):
        f = PhraseFinder([("book", "a book called"), ("paper", "a paper on")])
        hits = f.find("a book called dune and a paper on climate")
        labels = {h.label for h in hits}
        assert "book" in labels
        assert "paper" in labels

    def test_no_hit(self):
        f = PhraseFinder([("book", "a book called")])
        assert f.find("the weather is nice today") == []

    def test_case_insensitive(self):
        f = PhraseFinder([("book", "a book called")])
        assert f.find("A BOOK CALLED Dune") != []

    def test_partial_word_no_match(self):
        f = PhraseFinder([("book", "a book called")])
        # "booking" should not match "book"
        assert f.find("the booking was confirmed") == []

    def test_context_captured(self):
        f = PhraseFinder([("book", "a book called")])
        hits = f.find("she wrote a book called dune last year")
        assert "a book called" in hits[0].context

    def test_one_hit_per_label_per_chunk(self):
        f = PhraseFinder([
            ("book", "a book called"),
            ("book", "a novel called"),
        ])
        hits = f.find("a book called dune and a novel called foundation")
        book_hits = [h for h in hits if h.label == "book"]
        assert len(book_hits) == 1   # only one per label per chunk

    def test_from_string(self):
        f = PhraseFinder.from_string("book | a book called\npaper | a paper on")
        hits = f.find("there was a paper on climate")
        assert hits[0].label == "paper"

    def test_from_file(self):
        f = PhraseFinder.from_file(REF_FILE)
        hits = f.find("a film called oppenheimer")
        assert any(h.label == "movie" for h in hits)

    def test_comments_ignored(self):
        f = PhraseFinder.from_string("# this is a comment\nbook | a book called\n# another comment")
        assert f.phrase_count == 1

    def test_blank_lines_ignored(self):
        f = PhraseFinder.from_string("\n\nbook | a book called\n\n")
        assert f.phrase_count == 1

    def test_labels_property(self):
        f = PhraseFinder([("book", "a book called"), ("paper", "a paper on")])
        assert f.labels == {"book", "paper"}

    def test_phrase_count(self):
        f = PhraseFinder([("book", "a book called"), ("book", "a novel called")])
        assert f.phrase_count == 2

# ── unlabeled mode ────────────────────────────────────────────────────────────

class TestUnlabeledMode:

    def test_basic_found(self):
        f = PhraseFinder(["damn", "hell", "crap"])
        hits = f.find("what the hell is going on")
        assert len(hits) == 1
        assert hits[0].label is None
        assert hits[0].phrase == "hell"

    def test_not_found(self):
        f = PhraseFinder(["damn", "hell"])
        assert f.find("the weather is nice") == []

    def test_multiple_matches(self):
        f = PhraseFinder(["damn", "hell"])
        hits = f.find("damn it all to hell")
        assert len(hits) == 2

    def test_from_string_unlabeled(self):
        f = PhraseFinder.from_string("damn\nhell\ncrap")
        assert f.phrase_count == 3
        hits = f.find("that was damn good")
        assert hits[0].label is None

# ── cooldown ──────────────────────────────────────────────────────────────────

class TestCooldown:

    def test_no_cooldown_refires(self):
        f = PhraseFinder([("book", "a book called")], cooldown=0)
        f.find("a book called dune")
        hits = f.find("a book called foundation")
        assert len(hits) == 1

    def test_cooldown_suppresses(self):
        f = PhraseFinder([("book", "a book called")], cooldown=100)
        f.find("a book called dune")
        hits = f.find("a book called foundation")
        assert len(hits) == 0

    def test_cooldown_expires(self):
        f = PhraseFinder([("book", "a book called")], cooldown=3)
        f.find("a book called dune")
        # feed enough words to exhaust cooldown
        for _ in range(5):
            f.find("word word word")
        hits = f.find("a book called foundation")
        assert len(hits) == 1

    def test_reset_clears_cooldown(self):
        f = PhraseFinder([("book", "a book called")], cooldown=100)
        f.find("a book called dune")
        f.reset()
        hits = f.find("a book called foundation")
        assert len(hits) == 1

# ── serialization ─────────────────────────────────────────────────────────────

class TestSerialization:

    def test_save_load_roundtrip(self, tmp_path):
        f = PhraseFinder([("book", "a book called"), ("paper", "a paper on")])
        p = tmp_path / "test.pf"
        f.save(p)
        f2 = PhraseFinder.load(p)
        hits = f2.find("a book called dune")
        assert hits[0].label == "book"

    def test_load_preserves_cooldown(self, tmp_path):
        f = PhraseFinder([("book", "a book called")], cooldown=50)
        p = tmp_path / "test.pf"
        f.save(p)
        f2 = PhraseFinder.load(p)
        assert f2._cooldown == 50

    def test_load_preserves_labeled_mode(self, tmp_path):
        f = PhraseFinder(["word1", "word2"])
        p = tmp_path / "test.pf"
        f.save(p)
        f2 = PhraseFinder.load(p)
        assert not f2._labeled

# ── multilingual (ref_phrases.txt) ───────────────────────────────────────────

class TestMultilingual:
    """Positive and negative tests across languages using ref_phrases.txt."""

    @pytest.fixture(scope="class")
    def finder(self):
        return PhraseFinder.from_file(REF_FILE)

    POSITIVE = [
        # (lang, input, expected_label)
        ("en",    "a book called dune",                          "book"),
        ("en",    "a film called oppenheimer",                   "movie"),
        ("en",    "a song called bohemian rhapsody",             "song"),
        ("en",    "a podcast called lex fridman",                "podcast"),
        ("en",    "published a paper on climate change",         "paper"),
        ("en",    "a map of india",                              "map"),
        ("fr",    "un livre intitulé le petit prince",           "book"),
        ("fr",    "un film intitulé amélie",                     "movie"),
        ("es",    "un libro llamado cien años de soledad",       "book"),
        ("es",    "una película titulada roma",                  "movie"),
        ("de",    "ein buch namens der prozess",                 "book"),
        ("it",    "un libro chiamato il nome della rosa",        "book"),
        ("pt",    "um livro chamado o alquimista",               "book"),
        ("ja",    "千と千尋の神隠しという映画",                    "movie"),
        ("zh",    "一部电影叫做寄生虫",                           "movie"),
        ("zh",    "一本书叫做百年孤独",                           "book"),
        ("ko",    "기생충이라는 영화",                             "movie"),
        ("hi",    "देवदास एक उपन्यास जिसका नाम है",              "book"),
        ("hi",    "ek film release ki jiska naam hai",           "movie"),
        ("ta",    "ரோஜா என்ற ஒரு திரைப்படம்",                   "movie"),
        ("ar",    "كتاب بعنوان ألف شمس مشرقة",                  "book"),
        ("tr",    "kar adlı bir kitap",                          "book"),
        ("id",    "sebuah buku berjudul laskar pelangi",         "book"),
        ("sw",    "kitabu kinachoitwa nguvu ya imani",           "book"),
        ("vi",    "một cuốn sách có tên dế mèn phiêu lưu ký",  "book"),
        ("th",    "หนังสือชื่อสี่แผ่นดิน",                      "book"),
    ]

    NEGATIVE = [
        ("en", "the weather is nice today"),
        ("en", "i read the book last night"),          # no "called/titled"
        ("en", "we watched a film at home"),           # no qualifier
        ("en", "i need to study for my exam"),         # "study" not a trigger
        ("en", "the booking was confirmed"),           # partial match
        ("en", "the podcast landscape has changed"),   # no trigger phrase
        ("fr", "il fait beau aujourd hui"),
        ("de", "das wetter ist heute schön"),
        ("ja", "今日は天気がいいですね"),
        ("zh", "今天天气很好"),
        ("hi", "आज मौसम अच्छा है"),
    ]

    def test_positive(self, finder):
        for lang, text, expected_label in self.POSITIVE:
            hits = finder.find(text)
            labels = {h.label for h in hits}
            assert expected_label in labels, (
                f"[{lang}] expected '{expected_label}' in {text!r}, got {labels}"
            )

    def test_negative(self, finder):
        for lang, text in self.NEGATIVE:
            hits = finder.find(text)
            assert hits == [], (
                f"[{lang}] expected no hits for {text!r}, got {hits}"
            )

# ── latency ───────────────────────────────────────────────────────────────────

class TestLatency:
    """
    Latency stats for find() across input lengths.
    Prints a summary table — not a pass/fail test.
    """

    CASES = [
        ("short",   "a film called dune"),
        ("medium",  "she recently published a paper on climate change and its effects"),
        ("long",    "the professor mentioned a book called the structure of scientific revolutions during his lecture on paradigm shifts in science"),
        ("no_hit",  "the weather today is quite pleasant and there is nothing to report"),
        ("unicode", "千と千尋の神隠しという映画を見ました"),
        ("arabic",  "قرأت كتاب بعنوان ألف شمس مشرقة وكان رائعاً"),
    ]

    N = 1000

    @pytest.fixture(scope="class")
    def finder(self):
        return PhraseFinder.from_file(REF_FILE)

    def test_latency_report(self, finder, capsys):
        print(f"\n── Latency report (n={self.N} per case) ─────────────────────────────")
        print(f"  {'case':<12} {'chars':>6} {'min':>8} {'mean':>8} {'p50':>8} {'p95':>8} {'p99':>8} {'max':>8}  (µs)")
        print(f"  {'-'*76}")

        all_means = []
        all_lens  = []

        for name, text in self.CASES:
            stats = latency(lambda t=text: finder.find(t), self.N)
            all_means.append(stats["mean"])
            all_lens.append(len(text))
            print(
                f"  {name:<12} {len(text):>6} "
                f"{stats['min']:>8.1f} {stats['mean']:>8.1f} "
                f"{stats['p50']:>8.1f} {stats['p95']:>8.1f} "
                f"{stats['p99']:>8.1f} {stats['max']:>8.1f}"
            )

        # correlation: input length vs mean latency
        if len(all_means) > 1:
            mean_lat = statistics.mean(all_means)
            mean_len = statistics.mean(all_lens)
            cov  = sum((l - mean_len) * (m - mean_lat) for l, m in zip(all_lens, all_means))
            var  = sum((l - mean_len) ** 2 for l in all_lens)
            corr = cov / (var ** 0.5 * statistics.stdev(all_means) * (len(all_means) - 1) ** 0.5) if var > 0 else 0
            print(f"\n  correlation (input_len vs mean_latency): {corr:.3f}")

        with capsys.disabled():
            pass   # allow print output even when pytest captures
