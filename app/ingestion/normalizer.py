"""Normalization stage (Phase 7.3): scrape → **normalize** → clean → chunk → embed → store.

`normalize(doc)` is a pure, deterministic function: the same page always produces the same
text, and `normalize(normalize(x)) == normalize(x)`. That keeps chunk text — and therefore
chunk IDs, TF-IDF vectors and retrieval scores — stable between daily runs when a page's
facts have not changed, even if Groww's formatting drifts (`0.74 %` vs `0.74%`, `Rs.` vs `₹`).
"""

import copy
import re
import unicodedata
from datetime import date
from typing import Optional

from app.ingestion.scraper import ScrapedDocument

_ZERO_WIDTH = re.compile(r"[​‌‍⁠﻿�]")
_INLINE_SPACE = re.compile(r"[ \t\f\v]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")

# ₹: "Rs. 500", "Rs500", "INR 1,000", "₹ 100" -> "₹500" / "₹1,000" / "₹100" (only before a number)
_CURRENCY = re.compile(r"(?<![A-Za-z])(?:Rs\.?|RS\.?|INR)\s*(?=\d)")
_RUPEE_SPACE = re.compile(r"₹\s+(?=\d)")
# %: "0.74 %" -> "0.74%"
_PERCENT_SPACE = re.compile(r"(?<=\d)\s+%")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH = (
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
)
# "01 Jan 2013", "1st January, 2013", "01-Jan-2013"
_DATE_DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-]+" + _MONTH + r",?[\s\-]+(\d{4})\b", re.IGNORECASE)
# "Jan 01, 2013", "January 1 2013"
_DATE_MDY = re.compile(r"\b" + _MONTH + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.IGNORECASE)
# "01/01/2013", "1-1-2013" (Indian day-first order)
_DATE_NUMERIC = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b")

# Field labels
_TER_PAREN = re.compile(r"\bExpense\s+Ratio\s*\(\s*TER\s*\)", re.IGNORECASE)
_TOTAL_EXPENSE_RATIO = re.compile(r"\bTotal\s+Expense\s+Ratio\b", re.IGNORECASE)
_TER = re.compile(r"\bTER\b")  # case-sensitive: the acronym only
_EXPENSE_LABEL = re.compile(r"\bexpense\s+ratio(?=\s*:)", re.IGNORECASE)
_EXIT_LABEL = re.compile(r"\bexit\s+load(?=\s*:)", re.IGNORECASE)

# Exit load "Nil". "Exit load: Nil/None/Zero" is a label, so it is always rewritten; "No exit load"
# and "Exit load: 0%" only when nothing follows, so "No exit load after 1 year" keeps its meaning.
_END = r"(?=\s*(?:[.;,)\n]|$))"
_EXIT_NIL_LABEL = re.compile(r"\bexit\s+load\s*(?::\s*|-\s*|\s+is\s+)(?:nil|none|zero)\b", re.IGNORECASE)
_EXIT_ZERO = re.compile(r"\bexit\s+load\s*(?::\s*|-\s*|\s+is\s+)0(?:\.0+)?%" + _END, re.IGNORECASE)
_NO_EXIT_LOAD = re.compile(r"\bno\s+exit\s+load\b" + _END, re.IGNORECASE)

_THOUSANDS = re.compile(r"(?<=\d),(?=\d)")


def _iso(year: int, month: int, day: int) -> Optional[str]:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _dmy(m: re.Match) -> str:
    return _iso(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1))) or m.group(0)


def _mdy(m: re.Match) -> str:
    return _iso(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2))) or m.group(0)


def _numeric(m: re.Match) -> str:
    return _iso(int(m.group(3)), int(m.group(2)), int(m.group(1))) or m.group(0)


def _collapse_whitespace(text: str) -> str:
    lines = [_INLINE_SPACE.sub(" ", line).strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return _MANY_NEWLINES.sub("\n\n", "\n".join(lines)).strip()


def normalize_text(text: str) -> str:
    """Applies every normalization rule to a block of text. Idempotent."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text)
    text = _collapse_whitespace(text)

    text = _CURRENCY.sub("₹", text)
    text = _RUPEE_SPACE.sub("₹", text)
    text = _PERCENT_SPACE.sub("%", text)

    text = _DATE_DMY.sub(_dmy, text)
    text = _DATE_MDY.sub(_mdy, text)
    text = _DATE_NUMERIC.sub(_numeric, text)

    text = _TER_PAREN.sub("Expense Ratio", text)
    text = _TOTAL_EXPENSE_RATIO.sub("Expense Ratio", text)
    text = _TER.sub("Expense Ratio", text)
    text = _EXPENSE_LABEL.sub("Expense Ratio", text)
    text = _EXIT_LABEL.sub("Exit Load", text)

    text = _EXIT_NIL_LABEL.sub("Exit Load: Nil", text)
    text = _EXIT_ZERO.sub("Exit Load: Nil", text)
    text = _NO_EXIT_LOAD.sub("Exit Load: Nil", text)

    return _collapse_whitespace(text)


def numeric_key(text: str) -> str:
    """Matching key for numbers: drops thousands separators ("₹1,01,856" -> "₹101856").

    Used only to compare values (e.g. the validation diff); display text keeps its separators.
    """
    return _THOUSANDS.sub("", text or "")


def normalize(doc: ScrapedDocument) -> ScrapedDocument:
    """Returns a normalized copy of `doc`; the input is not modified."""
    out = copy.copy(doc)
    out.sections = [
        {**sec, "section": normalize_text(sec.get("section", "")), "text": normalize_text(sec.get("text", ""))}
        for sec in doc.sections
    ]
    out.full_text = "\n\n".join(s["text"] for s in out.sections)
    return out
