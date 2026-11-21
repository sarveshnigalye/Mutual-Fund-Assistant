"""Query pre-processing (edge-cases.md §1.1–1.8).

Runs before classification:
1. Empty / too short (≤ 2 meaningful chars)  -> INVALID (friendly prompt, never hits classifier/LLM)
2. Strip HTML/script tags, control chars, emoji and noisy symbol runs
3. Detect non-English (Devanagari or other non-Latin scripts)  -> NON_ENGLISH
4. Truncate to MAX_QUERY_CHARS (500) and flag `truncated`
"""

import html
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("core.preprocess")

MAX_QUERY_CHARS = 500
MIN_QUERY_CHARS = 3
NON_LATIN_RATIO_THRESHOLD = 0.30

_TAG_RE = re.compile(r"<[^>]{0,200}>")
_SCRIPT_BLOCK_RE = re.compile(r"<\s*(script|style)[^>]*>.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL)
# Keep letters/digits (any script, so language detection still works), whitespace and finance punctuation
_DISALLOWED_RE = re.compile(r"[^\w\sऀ-ॿ.,?!%₹/&()'\-:+]", re.UNICODE)
_REPEAT_PUNCT_RE = re.compile(r"([?.!,\-])\1+")
_WS_RE = re.compile(r"\s+")


@dataclass
class PreprocessResult:
    original: str
    clean: str
    status: str  # "OK" | "INVALID" | "NON_ENGLISH"
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "OK"


def _non_latin_letter_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    non_latin = sum(1 for ch in letters if not ("a" <= ch.lower() <= "z"))
    return non_latin / len(letters)


def preprocess_query(raw: str) -> PreprocessResult:
    original = raw or ""
    text = html.unescape(original)
    text = _SCRIPT_BLOCK_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = _DISALLOWED_RE.sub(" ", text)
    text = _REPEAT_PUNCT_RE.sub(r"\1", text)
    text = _WS_RE.sub(" ", text).strip()

    meaningful = re.sub(r"[\W_]", "", text, flags=re.UNICODE)
    if len(meaningful) < MIN_QUERY_CHARS:
        return PreprocessResult(original=original, clean=text, status="INVALID")

    if _non_latin_letter_ratio(text) > NON_LATIN_RATIO_THRESHOLD:
        return PreprocessResult(original=original, clean=text, status="NON_ENGLISH")

    truncated = False
    if len(text) > MAX_QUERY_CHARS:
        logger.warning("Query of %d chars truncated to %d.", len(text), MAX_QUERY_CHARS)
        text = text[:MAX_QUERY_CHARS].rsplit(" ", 1)[0].strip() or text[:MAX_QUERY_CHARS]
        truncated = True

    return PreprocessResult(original=original, clean=text, status="OK", truncated=truncated)
