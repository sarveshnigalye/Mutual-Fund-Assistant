"""Response formatter enforcing 3-sentence maximum, citation link, and footer."""

import json
import os
import re
from typing import Optional

from app.core.safety import contains_pii

# Load refusal templates for fallback/PII leak safety
REFUSAL_FILE = os.path.join(os.path.dirname(__file__), "..", "prompts", "refusal_templates.json")
try:
    with open(REFUSAL_FILE, "r", encoding="utf-8") as f:
        REFUSAL_TEMPLATES = json.load(f)
except Exception:
    REFUSAL_TEMPLATES = {
        "PII_DETECTED": "⚠️ Please do not share personal information. I do not collect or process personal data.",
        "FALLBACK": "I don't have verified information on this. Please check the official HDFC AMC website.",
    }

FALLBACK_TEXT = REFUSAL_TEMPLATES.get(
    "FALLBACK", "I don't have verified information on this. Please check the official HDFC AMC website."
)
FALLBACK_SOURCE_URL = "https://www.hdfcfund.com"
DEFAULT_SCRAPE_DATE = "2026-10-25"


def clean_llm_output(raw_text: str) -> str:
    """Removes thinking tags, markdown citation artifacts, or excessive whitespace."""
    if not raw_text:
        return ""

    # Strip <think>...</think> reasoning tags
    text = re.sub(r"<think>[\s\S]*?</think>", "", raw_text, flags=re.IGNORECASE)

    # Remove markdown link formatting if LLM hallucinated its own citation line
    text = re.sub(r"(?i)\n*(?:source(?:\s+link)?|citation|reference|url):\s*https?://\S+", "", text)
    text = re.sub(r"(?i)\n*📎\s*source:\s*https?://\S+", "", text)

    # Exactly one citation is appended by the system (edge-cases.md §5.9): drop any other URLs
    text = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", text)  # markdown links -> label
    text = re.sub(r"\(?https?://[^\s)]+\)?", "", text)
    # Tidy phrases orphaned by URL removal ("See  for details.", "visit: .")
    text = re.sub(
        r"(?i)\b(?:see|visit|refer\s+to|check(?:\s+out)?)\s*:?\s*(?:for\s+(?:more\s+)?(?:details|information))?\s*[.:]",
        "",
        text,
    )
    text = re.sub(r"(?i)\b(?:available\s+)?(?:at|here)\s*:\s*(?=[.\s]|$)", "", text)

    # Strip LLM-authored disclaimers; the system footer is the only disclaimer (edge-cases.md §5.5)
    text = re.sub(
        r"(?i)[^.!?\n]*\b(?:not\s+(?:a\s+)?financial\s+advi[cs]e|not\s+a\s+financial\s+advisor|"
        r"consult\s+(?:a|your)\s+financial\s+advisor|mutual\s+fund\s+investments\s+are\s+subject\s+to\s+market\s+risks?)"
        r"[^.!?\n]*[.!?]?",
        "",
        text,
    )

    # Normalize multiple newlines and spaces
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    cleaned = " ".join(lines)
    return cleaned.strip()


def split_sentences(text: str) -> list[str]:
    """
    Splits text into sentences, protecting decimals (e.g. 0.60%),
    abbreviations (Pvt., Ltd., etc.), and bullet points.
    """
    if not text:
        return []

    # Temporary mask for common abbreviations
    protected = text
    abbreviations = {
        r"\bPvt\.\s+": "Pvt_DOT_ ",
        r"\bLtd\.\s+": "Ltd_DOT_ ",
        r"\bCo\.\s+": "Co_DOT_ ",
        r"\bInc\.\s+": "Inc_DOT_ ",
        r"\be\.g\.\s+": "eg_DOT_ ",
        r"\bi\.e\.\s+": "ie_DOT_ ",
        r"\bMr\.\s+": "Mr_DOT_ ",
        r"\bMs\.\s+": "Ms_DOT_ ",
        r"\bDr\.\s+": "Dr_DOT_ ",
        r"\bvs\.\s+": "vs_DOT_ ",
    }
    for pattern, replacement in abbreviations.items():
        protected = re.sub(pattern, replacement, protected, flags=re.IGNORECASE)

    # Split on sentence ending punctuation followed by space and uppercase/quote/end
    raw_sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'₹]|$)", protected)

    restored = []
    for s in raw_sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        # Restore abbreviations
        s_restored = (
            s_clean.replace("Pvt_DOT_ ", "Pvt. ")
            .replace("Ltd_DOT_ ", "Ltd. ")
            .replace("Co_DOT_ ", "Co. ")
            .replace("Inc_DOT_ ", "Inc. ")
            .replace("eg_DOT_ ", "e.g. ")
            .replace("ie_DOT_ ", "i.e. ")
            .replace("Mr_DOT_ ", "Mr. ")
            .replace("Ms_DOT_ ", "Ms. ")
            .replace("Dr_DOT_ ", "Dr. ")
            .replace("vs_DOT_ ", "vs. ")
        )
        restored.append(s_restored)

    return restored


def format_response(
    raw_response: str,
    source_url: str,
    scrape_date: Optional[str] = None,
) -> str:
    """
    Formats the raw LLM response enforcing strict constraints:
    1. Maximum 3 sentences.
    2. Exactly one source citation URL.
    3. Last updated footer with scrape date.
    4. Safety check to ensure no leaked PII.
    """
    # 1. Clean LLM generation
    cleaned = clean_llm_output(raw_response)

    if not cleaned:
        # No answer -> the scheme page citation would be misleading; cite the AMC site instead
        cleaned = FALLBACK_TEXT
        source_url = FALLBACK_SOURCE_URL

    # 2. Split and cap to at most 3 sentences
    sentences = split_sentences(cleaned)
    if sentences:
        capped = " ".join(sentences[:3])
        # Ensure ending punctuation
        if not capped.endswith((".", "!", "?")):
            capped += "."
    else:
        capped = cleaned

    # 3. Check for leaked PII in the output
    if contains_pii(capped):
        return REFUSAL_TEMPLATES.get(
            "PII_DETECTED",
            "⚠️ Please do not share personal information. I do not collect or process personal data.",
        )

    # 4. Construct citation and footer (missing metadata falls back per edge-cases.md §6.5/§6.6)
    parts = [capped]

    citation = (source_url or "").strip() or FALLBACK_SOURCE_URL
    parts.append(f"📎 Source: {citation}")

    date_str = scrape_date or DEFAULT_SCRAPE_DATE
    parts.append(f"_Last updated from sources: {date_str}_")

    return "\n\n".join(parts)
