from __future__ import annotations

import hashlib
import re
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

SCANSION_DOCUMENT_VERSION = 1
MAX_POEM_LENGTH = 100_000
CMUDICT_PATH = Path(__file__).resolve().parent.parent / "third_party" / "cmudict" / "cmudict.dict"

_ALTERNATE_SUFFIX = re.compile(r"\(\d+\)$")
_STRESS_DIGIT = re.compile(r"([012])$")
_WORD = re.compile(r"[^\W\d_]+(?:[\u2019'][^\W\d_]+)*", re.UNICODE)

# These words are normally weak in connected English. Poetry can promote any of
# them, so the editor always permits per-occurrence corrections.
FUNCTION_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "him",
        "his",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "may",
        "me",
        "might",
        "must",
        "my",
        "nor",
        "not",
        "of",
        "on",
        "or",
        "our",
        "shall",
        "she",
        "should",
        "so",
        "than",
        "that",
        "the",
        "their",
        "them",
        "they",
        "this",
        "to",
        "us",
        "was",
        "we",
        "were",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
)


def normalize_word(word: str) -> str:
    normalized = unicodedata.normalize("NFKC", word).replace("\u2019", "'").casefold()
    return normalized.strip("'")


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Pronunciation:
    stresses: tuple[bool, ...]

    def as_dict(self) -> dict[str, list[bool]]:
        return {"stresses": list(self.stresses)}


class PronunciationProvider(Protocol):
    def pronunciations_for_word(self, word: str) -> tuple[Pronunciation, ...]: ...

    def analyze(self, text: str, *, mode: str = "general") -> dict: ...


class CmuPronunciationProvider:
    """A dependency-free, stress-only reader for the vendored CMU dictionary."""

    def __init__(self, dictionary_path: Path = CMUDICT_PATH):
        self.dictionary_path = Path(dictionary_path)
        self._index: dict[str, tuple[tuple[bool, ...], ...]] | None = None
        self._index_lock = threading.Lock()

    def _get_index(self) -> dict[str, tuple[tuple[bool, ...], ...]]:
        if self._index is None:
            with self._index_lock:
                if self._index is None:
                    self._index = self._load_index()
        return self._index

    def _load_index(self) -> dict[str, tuple[tuple[bool, ...], ...]]:
        mutable: dict[str, list[tuple[bool, ...]]] = {}
        with self.dictionary_path.open(encoding="utf-8") as dictionary:
            for raw_line in dictionary:
                line = raw_line.strip()
                if not line or line.startswith(";;;"):
                    continue
                headword, *phones = line.split()
                word = _ALTERNATE_SUFFIX.sub("", headword).casefold()
                stress_digits = tuple(
                    match.group(1) != "0"
                    for phone in phones
                    if (match := _STRESS_DIGIT.search(phone))
                )
                if not stress_digits:
                    continue
                pronunciations = mutable.setdefault(word, [])
                if stress_digits not in pronunciations:
                    pronunciations.append(stress_digits)
        return {word: tuple(pronunciations) for word, pronunciations in mutable.items()}

    def pronunciations_for_word(self, word: str) -> tuple[Pronunciation, ...]:
        normalized = normalize_word(word)
        raw_candidates = self._get_index().get(normalized, ())
        if not raw_candidates and normalized.endswith("'s"):
            raw_candidates = self._get_index().get(normalized[:-2], ())
        candidates = tuple(Pronunciation(stresses) for stresses in raw_candidates)
        if normalized in FUNCTION_WORDS:
            destressed = tuple(
                Pronunciation(tuple(False for _ in pronunciation.stresses))
                for pronunciation in candidates
            )
            return tuple(dict.fromkeys(destressed))
        return candidates

    def analyze(self, text: str, *, mode: str = "general") -> dict:
        if mode not in {"general", "iambic_pentameter"}:
            raise ValueError("Unsupported scansion mode")
        if len(text) > MAX_POEM_LENGTH:
            raise ValueError(f"Poem text cannot exceed {MAX_POEM_LENGTH:,} characters")

        document_lines = []
        unknown_words = 0
        for line_index, line_text in enumerate(text.splitlines()):
            words = []
            for word_index, match in enumerate(_WORD.finditer(line_text)):
                text_word = match.group(0)
                normalized = normalize_word(text_word)
                pronunciations = self.pronunciations_for_word(text_word)
                if not pronunciations:
                    unknown_words += 1
                words.append(
                    {
                        "id": f"l{line_index}:w{word_index}:{normalized}",
                        "text": text_word,
                        "normalized": normalized,
                        "source": "cmudict" if pronunciations else "unknown",
                        "pronunciations": [item.as_dict() for item in pronunciations],
                        "selected_pronunciation": 0 if pronunciations else None,
                        "stresses": list(pronunciations[0].stresses) if pronunciations else [],
                    }
                )
            document_lines.append(
                {
                    "index": line_index,
                    "text": line_text,
                    "words": words,
                }
            )

        return {
            "version": SCANSION_DOCUMENT_VERSION,
            "source_hash": source_hash(text),
            "mode": mode,
            "lines": document_lines,
            "unknown_words": unknown_words,
        }


provider = CmuPronunciationProvider()
