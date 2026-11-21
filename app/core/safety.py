"""PII scanner and safety guardrails module (Phase 3 Task 3.1).

Detects and redacts Personally Identifiable Information (PII) including:
- PAN (standard and spaced representations)
- Aadhaar (12-digit formatted or contextually marked, avoiding false positives on large financial numbers)
- Indian phone numbers (+91, 10 digits starting with 6-9, with or without delimiters)
- Email addresses
- OTPs and verification codes
- Bank account / Folio numbers with context
"""

import re
from typing import Optional, Tuple

# Pre-compiled regex patterns for standard PII tokens (ordered to prioritize specific IDs)
PII_PATTERNS = {
    "Aadhaar": re.compile(
        r"(?:\b[2-9]\d{3}[\s-]\d{4}[\s-]\d{4}\b|(?i:aadhaar|uidai|uid)[\s#:]{0,3}\b[2-9]\d{11}\b)"
    ),
    "PAN": re.compile(
        r"\b[A-Z]{5}\d{4}[A-Z]\b",
        re.IGNORECASE,
    ),
    "Email": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    "OTP": re.compile(
        r"(?:(?:otp|one\s*time\s*password|verification\s*code|pin)[\s#:]*(?:is\s*)?\b\d{4,6}\b|\b\d{4,6}\b\s*(?:is\s*(?:your|the)\s*(?:otp|code)))",
        re.IGNORECASE,
    ),
    "Account_Number": re.compile(
        r"(?:(?:account|acct|a/c|saving|current|folio)(?:\s+(?:number|no|num))?[\s#:]*(?:is\s*)?\b\d{9,18}\b)",
        re.IGNORECASE,
    ),
    "Phone": re.compile(
        r"(?:(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)|(?<!\d)[6-9]\d{4}[\s-]\d{5}(?!\d))"
    ),
}


# Fully spaced PAN, e.g. "A B C D E 1 2 3 4 F" (uppercase, every character separated)
_PAN_FULLY_SPACED = re.compile(
    r"(?<![A-Za-z0-9])[A-Z](?:[\s.\-]+[A-Z]){4}(?:[\s.\-]+\d){4}[\s.\-]+[A-Z](?![A-Za-z0-9])"
)
# Partially separated PAN, e.g. "ABCDE 1234 F" / "abcde-1234-f" — only flagged alongside a PAN keyword
_PAN_LOOSE = re.compile(
    r"(?<![A-Za-z0-9])[A-Z](?:[\s.\-]?[A-Z]){4}[\s.\-]?\d(?:[\s.\-]?\d){3}[\s.\-]?[A-Z](?![A-Za-z0-9])",
    re.IGNORECASE,
)
# "pan", "PAN", "P A N", "P-A-N" as a standalone word (not inside "company", "expand", ...)
_PAN_KEYWORD = re.compile(r"(?<![A-Za-z])p[\s.\-]*a[\s.\-]*n(?![A-Za-z])", re.IGNORECASE)


def check_spaced_pan(text: str) -> bool:
    """
    Detects deliberately or accidentally spaced PAN patterns like 'P A N : A B C D E 1 2 3 4 F'
    or 'A B C D E 1 2 3 4 F'.

    The previous implementation stripped all whitespace and searched for 'pan' anywhere, which
    flagged ordinary questions (e.g. "exit load since 2024 according to the company" ->
    'since2024a' + 'com-pan-y'). Separators are now bounded and the keyword must be a word.
    """
    if _PAN_FULLY_SPACED.search(text):
        return True
    return bool(_PAN_KEYWORD.search(text) and _PAN_LOOSE.search(text))


def scan_pii(text: str) -> Tuple[bool, Optional[str]]:
    """
    Scans input or output text for Personally Identifiable Information (PII).
    Returns (True, pii_type) if found, else (False, None).
    """
    if not text:
        return False, None

    # 1. Check for standard regex patterns
    for pii_type, pattern in PII_PATTERNS.items():
        if pattern.search(text):
            return True, pii_type

    # 2. Check for spaced PAN pattern (Edge case T34)
    if check_spaced_pan(text):
        return True, "PAN"

    return False, None


def contains_pii(text: str) -> bool:
    """Convenience boolean check for PII."""
    has_pii, _ = scan_pii(text)
    return has_pii


def sanitize_pii(text: str) -> str:
    """Redacts any detected PII patterns in text."""
    if not text:
        return text

    sanitized = text
    for pii_type, pattern in PII_PATTERNS.items():
        sanitized = pattern.sub(f"[{pii_type}_REDACTED]", sanitized)

    if check_spaced_pan(sanitized):
        sanitized = re.sub(
            r"(?:P\s*A\s*N\s*[:#\-]?\s*)?[A-Z]\s+[A-Z]\s+[A-Z]\s+[A-Z]\s+[A-Z]\s+\d\s+\d\s+\d\s+\d\s+[A-Z]",
            "[PAN_REDACTED]",
            sanitized,
            flags=re.IGNORECASE,
        )
    return sanitized
