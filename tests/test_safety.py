"""Unit tests for Phase 3 Task 3.1: PII Scanner and Safety Guardrails."""

import pytest
from app.core.safety import (
    check_spaced_pan,
    contains_pii,
    sanitize_pii,
    scan_pii,
)


class TestPIIScanner:
    """Tests comprehensive PII pattern matching and false positive avoidance."""

    def test_pan_detection_standard(self):
        queries = [
            "My PAN is ABCDE1234F, check my folio",
            "pan number: zyxwv9876k",
            "Here is the card: ABCDE1234F",
        ]
        for q in queries:
            has_pii, pii_type = scan_pii(q)
            assert has_pii is True, f"Failed to detect PAN in: {q}"
            assert pii_type == "PAN"

    def test_pan_detection_spaced(self):
        spaced_queries = [
            "P A N : A B C D E 1 2 3 4 F",
            "My pan is A B C D E 1 2 3 4 F please verify",
            "P-A-N: ABCDE1234F",
        ]
        for q in spaced_queries:
            assert check_spaced_pan(q) is True, f"Failed check_spaced_pan for: {q}"
            has_pii, pii_type = scan_pii(q)
            assert has_pii is True, f"Failed to detect spaced PAN in: {q}"
            assert pii_type == "PAN"

    def test_aadhaar_detection(self):
        valid_aadhaar = [
            "My Aadhaar is 2345 6789 0123",
            "Linked Aadhaar: 2345-6789-0123",
            "uid: 234567890123",
            "Aadhaar# 987654321012",
        ]
        for q in valid_aadhaar:
            has_pii, pii_type = scan_pii(q)
            assert has_pii is True, f"Failed to detect Aadhaar in: {q}"
            assert pii_type == "Aadhaar"

    def test_aadhaar_no_false_positive_on_financial_numbers(self):
        """Ensure large financial figures (AUM, NAV, turnover) are not flagged as Aadhaar."""
        financial_numbers = [
            "Fund AUM is 450000000000 rupees",
            "The total assets under management is ₹101856060000.",
            "NAV is 1132.50 with 150000000 units outstanding",
            "Expense ratio is 0.60% on 5000000000 investment",
        ]
        for text in financial_numbers:
            has_pii, pii_type = scan_pii(text)
            assert not has_pii, f"False positive PII ({pii_type}) detected in financial text: {text}"

    def test_phone_number_detection(self):
        phone_queries = [
            "Contact me at +91 9876543210 for KYC",
            "My mobile is +91-9876543210",
            "Call 9876543210 directly",
            "Call me at 98765 43210",
        ]
        for q in phone_queries:
            has_pii, pii_type = scan_pii(q)
            assert has_pii is True, f"Failed to detect Phone in: {q}"
            assert pii_type == "Phone"

    def test_email_detection(self):
        email_queries = [
            "Send statement to investor.help@hdfcfund.com",
            "Reach out to test.user+finance@sub.example.org please",
        ]
        for q in email_queries:
            has_pii, pii_type = scan_pii(q)
            assert has_pii is True, f"Failed to detect Email in: {q}"
            assert pii_type == "Email"

    def test_otp_detection(self):
        otp_queries = [
            "Your OTP is 492019",
            "Verification code: 1234",
            "One time password: 987654",
            "492019 is the otp",
        ]
        for q in otp_queries:
            has_pii, pii_type = scan_pii(q)
            assert has_pii is True, f"Failed to detect OTP in: {q}"
            assert pii_type == "OTP"

    def test_account_and_folio_detection(self):
        acc_queries = [
            "My bank account number is 123456789012",
            "Saving a/c: 987654321098",
            "Folio: 123456789",
        ]
        for q in acc_queries:
            has_pii, pii_type = scan_pii(q)
            assert has_pii is True, f"Failed to detect Account Number in: {q}"
            assert pii_type == "Account_Number"

    def test_clean_financial_queries_have_no_pii(self):
        clean_queries = [
            "What is the expense ratio of HDFC Mid Cap?",
            "What is the exit load for HDFC Small Cap Fund?",
            "Who is the fund manager of HDFC Multi Cap Fund?",
            "What is the benchmark index of HDFC Silver ETF FoF?",
            "Tell me about minimum SIP of 100 rupees.",
        ]
        for q in clean_queries:
            assert contains_pii(q) is False, f"Unexpected PII flag in clean query: {q}"

    def test_sanitize_pii(self):
        raw_text = "User PAN ABCDE1234F and email test@example.com requested info on +91 9876543210."
        sanitized = sanitize_pii(raw_text)
        assert "ABCDE1234F" not in sanitized
        assert "test@example.com" not in sanitized
        assert "9876543210" not in sanitized
        assert "[PAN_REDACTED]" in sanitized
        assert "[Email_REDACTED]" in sanitized
        assert "[Phone_REDACTED]" in sanitized

    def test_sanitize_spaced_pan(self):
        raw_text = "Verification with P A N : A B C D E 1 2 3 4 F."
        sanitized = sanitize_pii(raw_text)
        assert "A B C D E 1 2 3 4 F" not in sanitized
        assert "[PAN_REDACTED]" in sanitized
