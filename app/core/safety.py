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


def check_spaced_pan(text: str) -> bool:
    """
    Detects deliberately or accidentally spaced PAN patterns like 'P A N : A B C D E 1 2 3 4 F'
    or 'A B C D E 1 2 3 4 F'.
    """
    # Remove all whitespace, hyphens, and dots
    condensed = re.sub(r"[\s\.\-]", "", text)
    # Check for 5 uppercase letters, 4 digits, 1 uppercase letter
    if re.search(r"(?:PAN:?)?[A-Z]{5}\d{4}[A-Z]", condensed, re.IGNORECASE):
        # Verify it wasn't just a false positive from normal sentences by requiring
        # either 'pan' keyword or distinct letter/digit transition pattern
        if "pan" in condensed.lower() or re.search(r"\b(?:[A-Z]\s+){4}[A-Z]\s+(?:\d\s+){3}\d\s+[A-Z]\b", text, re.IGNORECASE):
            return True
    return False


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
