"""Cleaning stage (Phase 7.4): scrape → normalize → **clean** → chunk → embed → store.

Removes Groww site chrome (navigation, footer, cookie and promo text, the "Compare similar
funds" table) and duplicate / empty content, then rejects pages that cannot be trusted:
cleaned text under 200 characters (edge-cases.md §7.2), no Key Facts section, or a
CAPTCHA / bot-block interstitial.
"""

import copy
import re
from typing import Dict, List

from app.ingestion.scraper import BLOCK_MARKERS, ScrapedDocument

MIN_PAGE_CHARS = 200
MIN_CUT_LINE_CHARS = 30
KEY_FACTS_MARKER = "key facts"


class PageRejected(ValueError):
    """The page failed a cleaning check and must not be indexed."""

    def __init__(self, scheme_id: str, reason: str):
        super().__init__(f"{scheme_id}: {reason}")
        self.scheme_id = scheme_id
        self.reason = reason


# Boilerplate *spans* that Groww renders inside the same element as fund data, so the whole
# line cannot be dropped. Each pattern was taken from the indexed pages of 2026-10-25.
BOILERPLATE_SPANS = [
    # Site navigation menu: "Mutual Funds screener Filter funds ... Loan against securities and Personal loan"
    re.compile(r"Mutual Funds screener\b.*?(?:Loan against securities and Personal loan|$)", re.IGNORECASE),
    # Peer comparison table listing other AMCs' funds; it ends with a lone "Compare" button
    re.compile(r"Compare similar funds\b.*?\bCompare\b(?!\s+similar)", re.IGNORECASE),
    # Header mega-menu, stocks half: "Stocks Invest in Stocks ... Trade in F&O using the terminal View charts ..."
    re.compile(r"Stocks Invest in Stocks\b.*?(?=(?:Mutual Funds )?Invest in Mutual Funds\b|$)", re.IGNORECASE),
    # Header mega-menu, mutual-funds half: "Invest in Mutual Funds ... disciplined monthly investing."
    re.compile(r"(?:Mutual Funds )?Invest in Mutual Funds\b.*?Build long-term wealth through disciplined monthly investing\.?",
               re.IGNORECASE),
    re.compile(r"Mutual Fund Houses Know about AMCs.*?Build long-term wealth through disciplined monthly investing\.?",
               re.IGNORECASE),
    re.compile(r"Invest in direct mutual funds at zero charges via lump sump investments or SIPs", re.IGNORECASE),
    re.compile(r"(?:Mutual Fund Houses )?Know about AMCs, funds,? fund managers", re.IGNORECASE),
    # Animated digit rollers: "+ 1 0 1 2 3 4 5 6 7 8 9 5 0 1 2 3 4 5 6 7 8 9. 2 0 1 ... 9%" is unreadable
    re.compile(r"(?:[+\-] )?(?:\d 0 1 2 3 4 5 6 7 8 9[.%]? ?)+"),
    # Promotional banner
    re.compile(r"Looking to invest in mutual funds\?.*?Invest Now", re.IGNORECASE),
    re.compile(r"\bInvest Now\b", re.IGNORECASE),
]

# Lines containing any of these are site chrome, not fund facts.
BOILERPLATE_LINE_PHRASES = [
    "download groww app", "download the app", "cookie", "privacy policy", "terms of use",
    "terms and conditions", "all rights reserved", "help & support", "open a free demat",
    "mutual funds are subject to market risks", "similar funds", "popular funds",
    "advertisement", "sponsored",
]
_BOILERPLATE_LINE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in BOILERPLATE_LINE_PHRASES) + r")"  # prefix: "cookie" ~ "cookies"
    r"|\blog\s?in\b|\bsign\s?up\b",
    re.IGNORECASE,
)


def _is_label_line(line: str) -> bool:
    """A section's intro label such as "Details for HDFC Mid-Cap Opportunities Fund:"."""
    return line.endswith(":") and len(line) < 120


def _clean_line(line: str) -> str:
    original = line
    for pattern in BOILERPLATE_SPANS:
        line = pattern.sub(" ", line)
    line = re.sub(r"\s+", " ", line).strip()
    if line != original.strip() and len(line) < MIN_CUT_LINE_CHARS:
        return ""  # what is left after removing chrome is a fragment
    return line


def clean_section_text(text: str) -> str:
    """Cleans one section's text: boilerplate spans/lines removed, exact duplicate lines dropped."""
    kept: List[str] = []
    seen = set()
    for raw in (text or "").split("\n"):
        line = _clean_line(raw)
        if not line:
            continue
        if _BOILERPLATE_LINE.search(line) and not line.startswith("- "):
            continue  # key-fact bullets ("- Exit Load: ...") are never chrome
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        kept.append(line)
    return "\n".join(kept)


def _has_body(text: str) -> bool:
    return any(line.strip() and not _is_label_line(line.strip()) for line in text.split("\n"))


def clean(doc: ScrapedDocument) -> ScrapedDocument:
    """Returns a cleaned copy of `doc`, or raises PageRejected."""
    text_lower = (doc.full_text or "").lower()
    for marker in BLOCK_MARKERS:
        if marker in text_lower:
            raise PageRejected(doc.scheme_id, f"looks like a CAPTCHA / bot-block page (matched '{marker}')")

    sections: List[Dict[str, str]] = []
    for sec in doc.sections:
        cleaned = clean_section_text(sec.get("text", ""))
        if cleaned and _has_body(cleaned):
            sections.append({**sec, "text": cleaned})

    full_text = "\n\n".join(s["text"] for s in sections)
    if len(full_text) < MIN_PAGE_CHARS:
        raise PageRejected(
            doc.scheme_id,
            f"cleaned text is {len(full_text)} chars (< {MIN_PAGE_CHARS}); page layout may have changed",
        )
    if not any(KEY_FACTS_MARKER in s.get("section", "").lower() for s in sections):
        raise PageRejected(doc.scheme_id, "no Key Facts section found; page layout may have changed")

    out = copy.copy(doc)
    out.sections = sections
    out.full_text = full_text
    return out
