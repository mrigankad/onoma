"""Text helpers shared by ingest, search and the agents."""

from __future__ import annotations

import re
import unicodedata

_PUNCT = re.compile(r"[^\w%.]+", re.UNICODE)
_SPACES = re.compile(r"\s+")
_INCH = re.compile(r"(\d)\s*[\"”″]")
_NUMERIC_VALUE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?\s*(?:%|[a-zA-Z]{1,8}\.?)?")

TYPE_NAMES = {
    "abbr": "an abbreviation", "label": "the name", "code": "a code", "formula": "the formula",
    "unit": "a size or unit", "subtype": "a subtype", "alias": "a synonym", "grade": "a grade",
    "product": "a product", "certification": "a certification", "exact words": "the exact words",
}


def type_phrase(kind: str) -> str:
    return TYPE_NAMES.get(kind, f"a {kind}")


def is_numeric_value(value: str) -> bool:
    """'33%', '12,000 L', '7.5 yrs' -> True; 'N-1008', 'DN50' -> False."""
    return bool(_NUMERIC_VALUE.fullmatch(str(value).strip()))


def term_in(hay: str, hay_tokens: set[str], term: str) -> bool:
    """Phrase match like the search index sees it.

    Accepts the joined form ("aisi 304" matches "AISI304") and treats dots as separators,
    the same way the full-text index does ("react" matches "React.js").
    """
    if contains_phrase(hay, term):
        return True
    if " " in term and term.replace(" ", "") in hay_tokens:
        return True
    return "." in hay and contains_phrase(hay.replace(".", " "), term.replace(".", " "))

STOPWORDS = frozenset(
    "a an and are as at be by for from has in into is it of on or that the to was were with "
    "all any show find me list get search need needs looking which who what where".split()
)


def norm(text: str) -> str:
    """Lowercase, strip accents and punctuation, collapse spaces.

    "Hydrochloric-Acid " -> "hydrochloric acid", "CAS 7647-01-0" -> "cas 7647 01 0".
    """
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _INCH.sub(r"\1in", text)  # 2" -> 2in
    text = _PUNCT.sub(" ", text.lower())
    text = text.replace(" . ", " ").strip(" .")
    return _SPACES.sub(" ", text).strip()


def tokens(text: str) -> list[str]:
    return [t for t in norm(text).split(" ") if t]


def ngrams(words: list[str], max_n: int = 4) -> list[tuple[int, int, str]]:
    """All n-grams as (start, end, phrase), longest first."""
    out = []
    for n in range(min(max_n, len(words)), 0, -1):
        for i in range(len(words) - n + 1):
            out.append((i, i + n, " ".join(words[i : i + n])))
    return out


def contains_phrase(haystack_norm: str, phrase_norm: str) -> bool:
    """Whole-word phrase match on already-normalised strings."""
    if not phrase_norm:
        return False
    return f" {phrase_norm} " in f" {haystack_norm} "


def fts_phrase(phrase_norm: str) -> str:
    """Quote a normalised phrase for an FTS5 MATCH expression."""
    safe = phrase_norm.replace('"', " ").strip()
    return f'"{safe}"'


def split_multi(value: str) -> list[str]:
    """Split list-like cells: "k8s, Terraform; Go" -> ["k8s", "Terraform", "Go"]."""
    parts = re.split(r"[,;|/]| and ", str(value))
    return [p.strip() for p in parts if p.strip()]


def to_number(value) -> float | None:
    """Parse '33%', '7.5 yrs', '12,000 L' -> float; None if not numeric."""
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(value))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None
