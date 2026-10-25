"""PII scanner and safety guardrails module."""

import re
from typing import Optional, Tuple

PII_PATTERNS = {
    "PAN": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE),
    "Aadhaar": re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b"),
    "Email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "Phone": re.compile(r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b"),
    "OTP": re.compile(
        r"(?:(?:otp|one\s*time\s*password|verification\s*code)[:\s-]*\b\d{4,6}\b|\b\d{4,6}\b\s*(?:is\s*(?:your|the)\s*otp))",
        re.IGNORECASE,
    ),
    "Account_Number": re.compile(
        r"(?:(?:account|acct|a/c|saving|current)[\s#:]*\b\d{9,18}\b|\b\d{12,18}\b)",
        re.IGNORECASE,
    ),
}


def scan_pii(text: str) -> Tuple[bool, Optional[str]]:
    """
    Scans input or output text for Personally Identifiable Information (PII).
    Returns (True, pii_type) if found, else (False, None).
    """
    if not text:
        return False, None

    for pii_type, pattern in PII_PATTERNS.items():
        if pattern.search(text):
            return True, pii_type

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
    return sanitized
