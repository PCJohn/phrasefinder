"""
phrasefinder/core.py — PhraseFinder class.
"""

from __future__ import annotations

import re
import pickle
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import ahocorasick


@dataclass
class Hit:
    label: str | None   # None in unlabeled mode
    phrase: str         # matched phrase
    context: str        # surrounding text at time of match


class PhraseFinder:
    """
    Fast multi-phrase searcher over a stream of text chunks.

    Labeled mode (default):
        finder = PhraseFinder.from_file("phrases.txt")
        hits = finder.find("she published a book called dune")
        # → [Hit(label="book", phrase="a book called", context="...")]

    Unlabeled mode:
        finder = PhraseFinder(["damn", "hell"])
        found = finder.find("what the hell")
        # → [Hit(label=None, phrase="hell", context="...")]

    Args:
        source:   list of strings (unlabeled) or list of (label, phrase) tuples
        cooldown: words between re-firing the same (label, phrase). 0 = always fire.
    """

    def __init__(
        self,
        source: list[str] | list[tuple[str, str]],
        cooldown: int = 0,
    ):
        self._labeled = bool(source) and isinstance(source[0], tuple)
        self._cooldown = cooldown
        self._automaton = self._build(source)
        self._total_words = 0
        self._last_fired: dict[tuple, int] = {}

    # ── constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, path: str | Path, cooldown: int = 0) -> "PhraseFinder":
        """Load from a phrase file. See examples/ref_phrases.txt for format."""
        from .loader import load_file
        return cls(load_file(Path(path)), cooldown=cooldown)

    @classmethod
    def from_files(cls, *paths: str | Path, cooldown: int = 0) -> "PhraseFinder":
        """Load and merge multiple phrase files into one searcher."""
        from .loader import load_file
        phrases = []
        for p in paths:
            phrases.extend(load_file(Path(p)))
        return cls(phrases, cooldown=cooldown)

    @classmethod
    def from_dir(cls, directory: str | Path, cooldown: int = 0) -> "PhraseFinder":
        """Load all *.txt files from a directory."""
        from .loader import load_file
        phrases = []
        for p in sorted(Path(directory).glob("*.txt")):
            phrases.extend(load_file(p))
        return cls(phrases, cooldown=cooldown)

    @classmethod
    def from_string(cls, text: str, cooldown: int = 0) -> "PhraseFinder":
        """Load phrases from a string (same format as file)."""
        from .loader import parse_lines
        return cls(parse_lines(text.splitlines()), cooldown=cooldown)

    # ── serialization ─────────────────────────────────────────────────────────

    def save(self, path: str | Path):
        """Save compiled automaton to disk for fast loading."""
        with open(path, "wb") as f:
            pickle.dump({
                "automaton": self._automaton,
                "labeled":   self._labeled,
                "cooldown":  self._cooldown,
            }, f)

    @classmethod
    def load(cls, path: str | Path) -> "PhraseFinder":
        """Load a previously saved compiled automaton."""
        with open(path, "rb") as f:
            data = pickle.load(f)
        obj = cls.__new__(cls)
        obj._automaton   = data["automaton"]
        obj._labeled     = data["labeled"]
        obj._cooldown    = data["cooldown"]
        obj._total_words = 0
        obj._last_fired  = {}
        return obj

    # ── main API ──────────────────────────────────────────────────────────────

    def find(self, text: str) -> list[Hit]:
        """
        Search text for phrase matches. Call repeatedly with successive chunks
        for streaming use. Returns a list of Hit objects (empty if no match).
        """
        if not text or not text.strip():
            return []

        normalized = _normalize(text)
        self._total_words += len(normalized.split())

        hits: list[Hit] = []
        seen_labels: set = set()

        for end_idx, (label, phrase) in self._automaton.iter(normalized):
            if label in seen_labels:
                continue

            if self._cooldown > 0:
                key = (label, phrase)
                last = self._last_fired.get(key, -(self._cooldown + 1))
                if self._total_words - last <= self._cooldown:
                    continue
                self._last_fired[key] = self._total_words

            seen_labels.add(label)

            start_idx = end_idx - len(phrase) + 1
            context = normalized[max(0, start_idx - 20): end_idx + 50].strip()
            hits.append(Hit(
                label=label if self._labeled else None,
                phrase=phrase,
                context=context,
            ))

        return hits

    def reset(self):
        """Reset streaming state (word counter and cooldown tracking)."""
        self._total_words = 0
        self._last_fired.clear()

    # ── stats ─────────────────────────────────────────────────────────────────

    @property
    def phrase_count(self) -> int:
        return len(self._automaton)

    @property
    def labels(self) -> set[str]:
        return {v[0] for _, v in self._automaton.items()} if self._labeled else set()

    # ── internal ──────────────────────────────────────────────────────────────

    def _build(self, source) -> ahocorasick.Automaton:
        A = ahocorasick.Automaton()
        for item in source:
            if isinstance(item, tuple):
                label, phrase = item
            else:
                label, phrase = item, item   # unlabeled: phrase is its own key
            phrase = _normalize(phrase)
            if phrase:
                A.add_word(phrase, (label, phrase))
        A.make_automaton()
        return A


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()
