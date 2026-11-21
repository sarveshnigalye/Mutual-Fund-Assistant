"""Phase 7.4 — cleaning stage: boilerplate removal and page rejection."""

import pytest

from app.ingestion.cleaner import PageRejected, clean, clean_section_text
from app.ingestion.scraper import ScrapedDocument, detect_block_page

# Boilerplate as it appears in the indexed Groww pages
NAV_MENU = (
    "Mutual Funds screener Filter funds based on risk, fund size and more Track Funds Import funds and "
    "track all investments in a single place Compare Funds More SIP calculator Estimate returns on a SIP "
    "Pricing Brokerage and charges on Groww Blog Credit Loan against securities and Personal loan"
)
PEER_TABLE = (
    "Check past data Compare similar funds Name 1Y 3Y Fund Size(Cr) Invesco India Mid Cap Fund Direct Growth "
    "-4.01% +20.34% 15,748.83 Nippon India Growth Mid Cap Fund Direct Growth -3.33% +15.63% 50,176.01 Compare "
    "Fund management CS Chirag Setalvad Jan 2013 - Present View details"
)
PROMO = (
    "The PB ratio is evaluated by dividing the stock price per share by its book value per share (BVPS). "
    "Looking to invest in mutual funds? Explore diversified funds designed for every investor Invest Now"
)
KEY_FACTS = (
    "HDFC Test Fund Key Facts:\n- Expense Ratio: 0.60%\n- Exit Load: 1% if redeemed within 1 year\n"
    "- Benchmark: NIFTY Midcap 150 Total Return Index"
)


def make_doc(sections, scheme_id="hdfc-test"):
    return ScrapedDocument(
        scheme_id=scheme_id, scheme_name="HDFC Test Fund", category="Mid Cap", url="https://groww.in/x",
        amc="HDFC Mutual Fund", scrape_date="2026-11-21",
        full_text="\n\n".join(s["text"] for s in sections), sections=sections,
    )


def good_doc():
    return make_doc([
        {"section": "Scheme Overview", "text": "Scheme Name: HDFC Test Fund. Category: Mid Cap. AMC: HDFC Mutual Fund."},
        {"section": "Key Facts & Fund Parameters", "text": KEY_FACTS},
        {"section": "Expense Ratio, Exit Load and Taxes", "text": "\n".join([
            "Details for HDFC Test Fund:",
            "Exit load of 1% if redeemed within 1 year. Stamp duty on investment: 0.005% (from July 1st, 2020).",
            "Exit load of 1% if redeemed within 1 year. Stamp duty on investment: 0.005% (from July 1st, 2020).",
            PEER_TABLE,
            PROMO,
            "We use cookies to improve your experience on this website and for analytics purposes.",
            "Login to continue and track your SIP portfolio performance in the app.",
        ])},
        {"section": "Investment Limits, Benchmark and Risk", "text": "Investment details for HDFC Test Fund:\n" + NAV_MENU},
    ])


def test_removes_boilerplate_spans_but_keeps_facts():
    out = clean(good_doc())
    text = out.full_text
    for chrome in ("Mutual Funds screener", "Compare similar funds", "Invesco", "Nippon", "Invest Now",
                   "Looking to invest", "cookies", "Login"):
        assert chrome not in text, chrome
    assert "Fund management CS Chirag Setalvad" in text  # text after the peer table survives
    assert "book value per share (BVPS)." in text  # text before the promo survives
    assert "- Expense Ratio: 0.60%" in text
    assert "Stamp duty on investment" in text


def test_drops_duplicate_lines():
    out = clean(good_doc())
    assert out.full_text.count("Exit load of 1% if redeemed within 1 year. Stamp duty") == 1


def test_drops_sections_left_empty():
    out = clean(good_doc())
    # the nav menu was the only content of this section, only its label line remained
    assert "Investment Limits, Benchmark and Risk" not in [s["section"] for s in out.sections]


def test_clean_is_pure_and_idempotent():
    doc = good_doc()
    out = clean(doc)
    assert NAV_MENU in doc.full_text  # input untouched
    assert clean(out).sections == out.sections


def test_key_fact_bullets_are_never_dropped_as_chrome():
    assert clean_section_text("- Exit Load: Nil (sign up not required)") == "- Exit Load: Nil (sign up not required)"


def test_rejects_short_page():
    doc = make_doc([{"section": "Key Facts & Fund Parameters", "text": "Key Facts:\n- Expense Ratio: 0.60%"}])
    with pytest.raises(PageRejected, match="200"):
        clean(doc)


def test_rejects_page_without_key_facts():
    doc = good_doc()
    doc.sections = [s for s in doc.sections if "Key Facts" not in s["section"]]
    doc.full_text = "\n\n".join(s["text"] for s in doc.sections) + " filler " * 40
    with pytest.raises(PageRejected, match="Key Facts"):
        clean(doc)


def test_rejects_captcha_page():
    doc = good_doc()
    doc.full_text += "\nPlease verify you are human to continue."
    with pytest.raises(PageRejected, match="CAPTCHA"):
        clean(doc)


def test_detect_block_page():
    blocked = "<html><body><h1>Attention Required!</h1><p>Please complete the CAPTCHA.</p></body></html>"
    assert detect_block_page(blocked) is not None
    genuine = (
        "<html><head><script>window.recaptchaKey='x'</script></head><body>"
        "<div>Expense ratio 0.60%</div><div>Exit load 1%</div></body></html>"
    )
    assert detect_block_page(genuine) is None  # markers inside <script> are not visible text


def test_removes_header_mega_menu_and_digit_rollers():
    menu = (
        "Stocks Invest in Stocks Invest in stocks, ETFs, IPOs with fast orders. Intraday Monitor top intraday "
        "performers in real time ETF Screener Get the best of Mutual Funds Demat Account Begin your stock market "
        "journey Mutual Funds Invest in Mutual Funds Invest in direct mutual funds at zero charges via lump sump "
        "investments or SIPs Mutual Fund Houses Know about AMCs, funds, fund managers Start SIP Build long-term "
        "wealth through disciplined monthly investing."
    )
    assert clean_section_text(menu) == ""
    ticker = "+ 1 0 1 2 3 4 5 6 7 8 9 5 0 1 2 3 4 5 6 7 8 9. 2 0 1 2 3 4 5 6 7 8 9 6 0 1 2 3 4 5 6 7 8 9% 3Y annualised -1.42% 1D"
    assert clean_section_text(ticker) == ""  # what is left ("3Y annualised -1.42% 1D") is a fragment
    line = ticker + " The fund aims to generate long-term capital appreciation from mid cap companies."
    assert clean_section_text(line) == "3Y annualised -1.42% 1D The fund aims to generate long-term capital appreciation from mid cap companies."
