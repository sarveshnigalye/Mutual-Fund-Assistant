"""Phase 7.3 — normalization stage rules and idempotence."""

import pytest

from app.ingestion.normalizer import normalize, normalize_text, numeric_key
from app.ingestion.scraper import ScrapedDocument


@pytest.mark.parametrize("raw, expected", [
    ("Min SIP Rs. 500", "Min SIP ₹500"),
    ("Min SIP Rs500", "Min SIP ₹500"),
    ("Lumpsum INR 1,000", "Lumpsum ₹1,000"),
    ("AUM ₹ 9,34,075 Cr", "AUM ₹9,34,075 Cr"),
    ("Rs and paise", "Rs and paise"),  # only before a number
    ("Mrs 500 Smith", "Mrs 500 Smith"),  # not inside a word
])
def test_currency(raw, expected):
    assert normalize_text(raw) == expected


def test_percent_spacing():
    assert normalize_text("Expense Ratio: 0.74 %") == "Expense Ratio: 0.74%"
    assert normalize_text("returns +20.34%") == "returns +20.34%"


@pytest.mark.parametrize("raw, expected", [
    ("Launched 01 Jan 2013 with", "Launched 2013-01-01 with"),
    ("since 1st January, 2013.", "since 2013-01-01."),
    ("on 18-Dec-2014", "on 2014-12-18"),
    ("as of Jan 5, 2024", "as of 2024-01-05"),
    ("dated 18/12/2014", "dated 2014-12-18"),
    ("Jan 2013 - Present", "Jan 2013 - Present"),  # month-year only: untouched
    ("on 31 Feb 2020", "on 31 Feb 2020"),  # invalid date: untouched
    ("already 2026-11-21", "already 2026-11-21"),
])
def test_dates_to_iso(raw, expected):
    assert normalize_text(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("TER: 0.74%", "Expense Ratio: 0.74%"),
    ("Total Expense Ratio 0.6%", "Expense Ratio 0.6%"),
    ("Expense Ratio (TER): 1%", "Expense Ratio: 1%"),
    ("expense ratio: 1%", "Expense Ratio: 1%"),
    ("exit load: 1% if redeemed within 1 year", "Exit Load: 1% if redeemed within 1 year"),
    ("TERM deposits", "TERM deposits"),
])
def test_field_labels(raw, expected):
    assert normalize_text(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Exit load: Nil", "Exit Load: Nil"),
    ("Exit load: none", "Exit Load: Nil"),
    ("Exit Load: 0%", "Exit Load: Nil"),
    ("Exit load is 0.00 %.", "Exit Load: Nil."),
    ("No exit load.", "Exit Load: Nil."),
    ("No exit load after 1 year", "No exit load after 1 year"),  # conditional: keep meaning
    ("Exit load of 1% if redeemed within 1 year", "Exit load of 1% if redeemed within 1 year"),
    ("Exit Load: 0.5%", "Exit Load: 0.5%"),
])
def test_exit_load_nil(raw, expected):
    assert normalize_text(raw) == expected


def test_unicode_and_whitespace():
    raw = "Expense Ratio:​ ０.５ ％\t\tand   more\n\n\n\nnext\r\nline  "
    assert normalize_text(raw) == "Expense Ratio: 0.5% and more\n\nnext\nline"


def test_numeric_key_is_for_matching_only():
    assert numeric_key("₹1,01,856 Cr") == "₹101856 Cr"
    assert normalize_text("AUM ₹1,01,856 Cr") == "AUM ₹1,01,856 Cr"  # display keeps separators


SAMPLES = [
    "HDFC Mid-Cap Opportunities Fund Key Facts:\n- TER: 0.60 %\n- Exit load: 0 %\n- Min SIP: Rs. 100",
    "Exit Load: 01 Jan 2013 Exit load of 1% if redeemed within 1 year.",
    "No exit load.  Total Expense Ratio (TER) 0.74 % as of Jan 5, 2024",
    "Fund size (AUM) INR 37,293 Cr   Benchmark: NIFTY 100 Total Return Index",
    "",
]


@pytest.mark.parametrize("raw", SAMPLES)
def test_idempotent(raw):
    once = normalize_text(raw)
    assert normalize_text(once) == once


def test_normalize_document_is_pure():
    doc = ScrapedDocument(
        scheme_id="hdfc-test", scheme_name="HDFC Test Fund", category="Test", url="https://groww.in/x",
        amc="HDFC Mutual Fund", scrape_date="2026-11-21", full_text="TER: 0.60 %",
        sections=[{"section": "Key Facts", "text": "TER: 0.60 %"}, {"section": "Other", "text": "Rs. 100"}],
    )
    out = normalize(doc)
    assert out is not doc
    assert doc.sections[0]["text"] == "TER: 0.60 %"  # input untouched
    assert [s["text"] for s in out.sections] == ["Expense Ratio: 0.60%", "₹100"]
    assert out.full_text == "Expense Ratio: 0.60%\n\n₹100"
    assert normalize(out).sections == out.sections
