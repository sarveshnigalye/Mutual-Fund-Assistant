"""Unit tests for the response formatter."""

from app.core.formatter import format_response, split_sentences, clean_llm_output


def test_clean_llm_output():
    raw = "<think>The user is asking about expense ratio.</think>The expense ratio is 0.60%."
    cleaned = clean_llm_output(raw)
    assert cleaned == "The expense ratio is 0.60%."
    assert "<think>" not in cleaned


def test_split_sentences_with_decimals_and_abbr():
    text = "HDFC Asset Management Co. Ltd. manages the fund. The expense ratio is 0.60%. The minimum SIP is ₹100. It is rated 4 stars."
    sentences = split_sentences(text)
    assert len(sentences) == 4
    assert sentences[0] == "HDFC Asset Management Co. Ltd. manages the fund."
    assert "0.60%" in sentences[1]


def test_format_response_caps_at_three_sentences():
    raw = (
        "Sentence one. Sentence two. Sentence three. "
        "Sentence four should be omitted. Sentence five also omitted."
    )
    formatted = format_response(
        raw_response=raw,
        source_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        scrape_date="2026-10-25",
    )
    assert "Sentence one." in formatted
    assert "Sentence two." in formatted
    assert "Sentence three." in formatted
    assert "Sentence four" not in formatted
    assert "📎 Source: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth" in formatted
    assert "_Last updated from sources: 2026-10-25_" in formatted


def test_format_response_pii_safety_net():
    raw_with_pii = "Your account number is 123456789012. The expense ratio is 0.60%."
    formatted = format_response(
        raw_response=raw_with_pii,
        source_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
    )
    assert "⚠️ Please do not share personal information" in formatted
    assert "123456789012" not in formatted
