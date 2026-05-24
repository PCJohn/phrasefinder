"""
phrasefinder/loader.py — file format parsing.

File format (labeled):
    label | phrase
    # comment lines and blank lines are ignored

File format (unlabeled):
    phrase
    phrase
    # comment lines and blank lines are ignored

Mixed files are fine — lines with | are labeled, lines without are unlabeled.
A line starting with # <lang>.txt sets the current language tag (for multi-
language bundle files like ref_phrases.txt) — ignored by the loader, just
acts as a section comment.
"""

from __future__ import annotations

import re
from pathlib import Path


def load_file(path: Path) -> list[tuple[str, str] | str]:
    return parse_lines(path.read_text(encoding="utf-8").splitlines())


def parse_lines(lines: list[str]) -> list[tuple[str, str] | str]:
    results = []
    seen: set = set()

    for raw in lines:
        line = raw.split("#")[0].strip()
        if not line:
            continue

        if "|" in line:
            label, _, phrase = line.partition("|")
            label  = label.strip().lower()
            phrase = phrase.strip()
            if label and phrase:
                key = (label, phrase.lower())
                if key not in seen:
                    seen.add(key)
                    results.append((label, phrase))
        else:
            phrase = line.strip()
            if phrase:
                key = phrase.lower()
                if key not in seen:
                    seen.add(key)
                    results.append(phrase)

    return results
