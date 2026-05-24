# phrasefinder

Fast multi-phrase search over text streams. Built on [Aho-Corasick](https://en.wikipedia.org/wiki/Aho%E2%80%93Corasick_algorithm) — finds all matching phrases in a single O(n) pass, regardless of how many phrases you have.

Useful anywhere you need to detect keywords or phrases in a stream of text: real-time transcripts, content moderation, reference detection, named entity triggering, and similar.

```python
from phrasefinder import PhraseFinder

finder = PhraseFinder.from_file("examples/ref_phrases.txt")
hits = finder.find("she published a book called dune")
# → [Hit(label='book', phrase='a book called', context='...')]
```

---

## Install

```bash
pip install phrasefinder
```

Or install from source:

```bash
git clone https://github.com/yourusername/phrasefinder
cd phrasefinder
pip install -e ".[dev]"
```

**Requires Python 3.10+.**

---

## Quick start

### Labeled mode

Each phrase has a label. `find()` returns a list of `Hit` objects.

```python
from phrasefinder import PhraseFinder

finder = PhraseFinder([
    ("book",  "a book called"),
    ("book",  "a novel titled"),
    ("movie", "a film called"),
    ("movie", "directed by"),
])

hits = finder.find("there's a film called oppenheimer directed by nolan")
for hit in hits:
    print(hit.label, hit.phrase)
# movie  a film called
# movie  directed by   ← only one hit per label per chunk by default
```

### Unlabeled mode

Pass a plain list of strings. `find()` returns hits with `label=None`.

```python
finder = PhraseFinder(["damn", "hell", "crap"])
hits = finder.find("what the hell is going on")
# → [Hit(label=None, phrase='hell', context='...')]
```

### Load from file

```python
finder = PhraseFinder.from_file("examples/ref_phrases.txt")
```

File format — labeled:
```
# comment lines are ignored
book   | a book called
book   | a novel titled
movie  | a film called
```

File format — unlabeled:
```
damn
hell
crap
```

Mixed files are fine. Lines with `|` are labeled; lines without are unlabeled.

### Load from multiple files or a directory

```python
finder = PhraseFinder.from_files("en.txt", "fr.txt", "de.txt")
finder = PhraseFinder.from_dir("phrases/")   # loads all *.txt in the directory
```

### Load from a string

```python
finder = PhraseFinder.from_string("""
    book  | a book called
    paper | a paper on
""")
```

---

## Streaming use

`find()` is stateful — call it repeatedly with successive text chunks. Word count accumulates across calls, which drives cooldown (see below).

```python
finder = PhraseFinder.from_file("examples/ref_phrases.txt", cooldown=30)

for chunk in transcript_stream:
    hits = finder.find(chunk)
    for hit in hits:
        print(f"[{hit.label}] '{hit.phrase}' — {hit.context}")

finder.reset()   # clear state between sessions
```

---

## Cooldown

By default (`cooldown=0`) every occurrence fires. Set `cooldown=N` to suppress re-firing the same `(label, phrase)` pair until N more words have been seen — useful for deduplicating repeated references in a long transcript.

```python
# won't re-fire "book" for 30 words after the first hit
finder = PhraseFinder.from_file("ref_phrases.txt", cooldown=30)
```

---

## Save and load compiled automaton

Compilation is fast (~30ms for 1300 phrases) but you can save the compiled automaton to disk for instant loading:

```python
finder = PhraseFinder.from_file("examples/ref_phrases.txt")
finder.save("ref_phrases.pf")

# later / in your app
finder = PhraseFinder.load("ref_phrases.pf")
```

---

## Included example: reference finder

`examples/ref_phrases.txt` contains ~1300 phrases across 29 languages for detecting references to books, papers, movies, TV shows, songs, podcasts, and maps in conversational speech. It covers:

- **European languages** — English, French, Spanish, Portuguese, German, Italian, Dutch, Polish, Russian, Ukrainian
- **Middle Eastern** — Arabic, Persian, Turkish
- **South Asian** — Hindi (Devanagari + Roman), Bengali, Marathi, Gujarati, Punjabi, Tamil, Telugu, Kannada, Malayalam
- **East/Southeast Asian** — Chinese (Simplified + Traditional), Japanese, Korean, Thai, Vietnamese, Indonesian
- **African** — Swahili

All Indian languages include both native script and Roman transliteration variants for STT output that code-switches.

---

## API reference

### `PhraseFinder(source, cooldown=0)`

| Parameter  | Type | Description |
|------------|------|-------------|
| `source`   | `list[str]` or `list[tuple[str, str]]` | Unlabeled strings or `(label, phrase)` tuples |
| `cooldown` | `int` | Words between re-firing the same match. `0` = always fire |

### Constructors

| Method | Description |
|--------|-------------|
| `PhraseFinder.from_file(path, cooldown=0)` | Load from a phrase file |
| `PhraseFinder.from_files(*paths, cooldown=0)` | Load and merge multiple files |
| `PhraseFinder.from_dir(directory, cooldown=0)` | Load all `*.txt` files in a directory |
| `PhraseFinder.from_string(text, cooldown=0)` | Load from a string |
| `PhraseFinder.load(path)` | Load a compiled `.pf` automaton |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `find(text)` | `list[Hit]` | Search text, returns all hits (empty list = no match) |
| `reset()` | `None` | Clear streaming state (word counter + cooldown) |
| `save(path)` | `None` | Save compiled automaton to disk |

### Properties

| Property | Description |
|----------|-------------|
| `phrase_count` | Total number of phrases loaded |
| `labels` | Set of all labels (labeled mode only) |

### `Hit`

| Field | Type | Description |
|-------|------|-------------|
| `label` | `str \| None` | Label, or `None` in unlabeled mode |
| `phrase` | `str` | The phrase that matched |
| `context` | `str` | Surrounding text at time of match |

---

## Run tests

```bash
# install with dev dependencies
pip install -e ".[dev]"

# run all tests
pytest tests/ -v

# run with latency report printed
pytest tests/ -v -s

# run only multilingual tests
pytest tests/ -v -k "multilingual"

# run only latency tests
pytest tests/ -v -s -k "latency"
```

---

## Add your own phrases

Create a `*.txt` file:

```
# my_phrases.txt
profanity | damn
profanity | hell
brand     | coca-cola
brand     | pepsi
```

```python
finder = PhraseFinder.from_file("my_phrases.txt")
```

To extend the reference finder, add lines to `examples/ref_phrases.txt` or create a new file and merge:

```python
finder = PhraseFinder.from_files(
    "examples/ref_phrases.txt",
    "my_extra_phrases.txt",
)
```

---

## Performance

Single-pass Aho-Corasick: O(n + m) where n = text length, m = total pattern length. Pattern count has negligible effect on search speed.

Typical latency for `find()` on a sentence-length input with 1300 phrases loaded across 29 languages: **5–20 µs**.

---

## License

MIT
