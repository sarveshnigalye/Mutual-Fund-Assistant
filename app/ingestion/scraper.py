"""Web scraper for Groww mutual fund scheme pages using Selenium.

Phase 7: pages are always fetched live. `data/raw/*.html` is written as an audit copy of
what was indexed and is never read back as a cache, so a failed fetch fails that URL
instead of silently re-indexing stale HTML. CAPTCHA / bot-block pages are rejected.
"""

import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from selenium import webdriver

from app.config import settings
from app.ingestion.snapshot import ist_today

logger = logging.getLogger("ingestion.scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

USER_AGENTS = {
    "edge": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    ),
    # Headless Chrome otherwise advertises "HeadlessChrome", which bot filters block on sight.
    "chrome": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Phrases that only appear on anti-bot / error interstitials. None of them occur in the
# visible text of a genuine Groww scheme page (checked against the 2026-10-25 audit copies).
BLOCK_MARKERS = (
    "captcha",
    "are you a robot",
    "are you human",
    "verify you are human",
    "unusual traffic",
    "access denied",
    "request blocked",
    "attention required",
    "too many requests",
    "checking your browser",
    "just a moment...",
    "enable javascript and cookies",
    "403 forbidden",
)

# Text the page shows once fund data has rendered (edge-cases.md §7.4 explicit wait).
READY_MARKER = "expense ratio"
PAGE_READY_TIMEOUT_SECONDS = 20


class BlockedPageError(RuntimeError):
    """The fetched page is a CAPTCHA / bot-block / error page, not fund data."""


def visible_text(html: str) -> str:
    """Text a user would see: scripts, styles and noscript blocks removed, whitespace collapsed."""
    soup = BeautifulSoup(html or "", "html.parser")
    for element in soup(["script", "style", "noscript", "template"]):
        element.decompose()
    return re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()


def detect_block_page(html: str) -> Optional[str]:
    """Returns the matched marker if `html` is a CAPTCHA / bot-block page, else None."""
    text = visible_text(html).lower()
    for marker in BLOCK_MARKERS:
        if marker in text:
            return marker
    return None


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class ScrapedDocument:
    """Represents a fully scraped scheme document with extracted sections and metadata."""

    def __init__(
        self,
        scheme_id: str,
        scheme_name: str,
        category: str,
        url: str,
        amc: str,
        scrape_date: str,
        full_text: str,
        sections: List[Dict[str, str]],
        page_sha256: str = "",
    ):
        self.scheme_id = scheme_id
        self.scheme_name = scheme_name
        self.category = category
        self.url = url
        self.amc = amc
        self.scrape_date = scrape_date
        self.full_text = full_text
        self.sections = sections
        # sha256 of the page's visible text as fetched (before parsing), for the run metadata
        self.page_sha256 = page_sha256

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scheme_id": self.scheme_id,
            "scheme_name": self.scheme_name,
            "category": self.category,
            "url": self.url,
            "amc": self.amc,
            "scrape_date": self.scrape_date,
            "full_text": self.full_text,
            "sections": self.sections,
            "page_sha256": self.page_sha256,
        }


class GrowwScraper:
    """Automates headless browser scraping of Groww mutual fund scheme pages."""

    def __init__(self, raw_cache_dir: str = "data/raw", run_date: Optional[str] = None):
        # Audit copies only — never read back (Phase 7.2).
        self.raw_cache_dir = raw_cache_dir
        # One date for the whole run, so a run that crosses midnight IST is not split across two days
        self.run_date = run_date or ist_today()
        os.makedirs(self.raw_cache_dir, exist_ok=True)
        self.failures: List[Dict[str, str]] = []

    def _create_driver(self) -> webdriver.Remote:
        """Instantiates a headless Chromium or Edge driver based on configuration."""
        browser_type = settings.browser_type.lower()
        driver_path = (settings.chrome_driver_path or "auto").strip()

        if browser_type == "edge":
            from selenium.webdriver.edge.options import Options as EdgeOptions
            from selenium.webdriver.edge.service import Service as EdgeService
            from webdriver_manager.microsoft import EdgeChromiumDriverManager

            options = EdgeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument(f"user-agent={USER_AGENTS['edge']}")
            service = EdgeService(EdgeChromiumDriverManager().install())
            return webdriver.Edge(service=service, options=options)
        else:
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.chrome.service import Service as ChromeService

            options = ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument(f"user-agent={USER_AGENTS['chrome']}")
            if driver_path.lower() != "auto" and os.path.exists(driver_path):
                # e.g. the chromedriver preinstalled on GitHub's ubuntu-latest image
                service = ChromeService(executable_path=driver_path)
            else:
                from webdriver_manager.chrome import ChromeDriverManager

                service = ChromeService(ChromeDriverManager().install())
            return webdriver.Chrome(service=service, options=options)

    def _wait_for_fund_data(self, driver) -> None:
        """Waits for fund data to render; on timeout, carries on and lets validation decide."""
        try:
            from selenium.webdriver.support.ui import WebDriverWait

            # innerText is what has actually rendered; page_source would also match markup or
            # JSON state shipped in the server HTML before the widgets are drawn.
            WebDriverWait(driver, PAGE_READY_TIMEOUT_SECONDS).until(
                lambda d: READY_MARKER in (d.execute_script("return document.body ? document.body.innerText : ''") or "").lower()
            )
        except Exception as e:  # TimeoutException or a driver hiccup
            logger.warning(f"Fund data marker not seen within {PAGE_READY_TIMEOUT_SECONDS}s: {e}")

    def scrape_url(self, target: Dict[str, str], max_retries: int = 3) -> ScrapedDocument:
        """
        Scrapes a single Groww mutual fund scheme page.
        Retries up to max_retries with exponential backoff on transient errors.
        Raises the last error if every attempt fails (no cached-HTML fallback).
        """
        url = target["url"]
        scheme_id = target.get("id", url.rstrip("/").split("/")[-1])
        scheme_name = target.get("scheme_name", scheme_id)
        category = target.get("category", "Mutual Fund")
        amc = target.get("amc", "HDFC Mutual Fund")
        scrape_date = self.run_date

        raw_audit_path = os.path.join(self.raw_cache_dir, f"{scheme_id}.html")

        html = None
        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            driver = None
            try:
                logger.info(f"[{attempt}/{max_retries}] Scraping '{scheme_name}' from: {url}")
                driver = self._create_driver()
                driver.set_page_load_timeout(30)
                driver.get(url)
                self._wait_for_fund_data(driver)
                time.sleep(settings.scrape_delay_seconds + 3)  # let late JS widgets settle (as before Phase 7)
                html = driver.page_source

                if len(html) < 2000:
                    raise ValueError(f"Extracted HTML too short ({len(html)} bytes), page may not have rendered")

                marker = detect_block_page(html)
                if marker:
                    raise BlockedPageError(f"Bot-block / CAPTCHA page detected (matched '{marker}')")

                # Audit copy of exactly what is being indexed
                with open(raw_audit_path, "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info(f"Wrote audit copy {raw_audit_path} ({len(html)} bytes)")
                last_error = None
                break
            except Exception as e:
                last_error = e
                html = None
                logger.warning(f"Attempt {attempt} failed for {url}: {e}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)  # 2s, 4s backoff
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass

        if last_error is not None or html is None:
            raise last_error or RuntimeError(f"No HTML fetched for {url}")

        doc = self._parse_html(html, scheme_id, scheme_name, category, url, amc, scrape_date)
        doc.page_sha256 = sha256_text(visible_text(html))
        return doc

    def _parse_html(
        self,
        html: str,
        scheme_id: str,
        scheme_name: str,
        category: str,
        url: str,
        amc: str,
        scrape_date: str,
    ) -> ScrapedDocument:
        """Parses raw Groww HTML into structured, factual text blocks."""
        soup = BeautifulSoup(html, "html.parser")

        # Remove scripts, styles, forms, navigation bars, banners
        for element in soup(["script", "style", "nav", "header", "footer", "form", "noscript", "svg"]):
            element.decompose()

        sections: List[Dict[str, str]] = []

        # 1. Scheme Title & Basic Tagline
        title = soup.title.string.strip() if soup.title else scheme_name
        sections.append({
            "section": "Scheme Overview",
            "text": f"Scheme Name: {scheme_name}. Category: {category}. AMC: {amc}. Web Page Title: {title}. Source Link: {url}.",
        })

        # 2. Extract structured key-value pairs from tables and cards
        key_value_pairs = []
        for row in soup.find_all(["tr", "div"]):
            text = row.get_text(separator=" ", strip=True)
            if not text:
                continue

            # Look for common mutual fund factual markers
            patterns = [
                r"(Expense ratio|Expense Ratio|TER)[\s:]+([\d\.]+\s*%)",
                r"(Exit load|Exit Load)[\s:]+([^\.]+?\.)",
                r"(Min(?:imum)?\s*(?:for\s*)?SIP|Min SIP)[\s:]+(?:₹\s*)?([\d,]+)",
                r"(Min(?:imum)?\s*(?:for\s*)?Lumpsum|Min Investment)[\s:]+(?:₹\s*)?([\d,]+)",
                r"(Lock-in|Lock in\s*period)[\s:]+([^\.]+)",
                r"(Risk|Riskometer)[\s:]+([A-Za-z\s]+Risk)",
                r"(Benchmark|Benchmark Index)[\s:]+([^\.]+)",
                r"(Fund size|AUM)[\s:]+(?:₹\s*)?([\d,\.]+\s*(?:Cr|Crore)?)",
                r"(NAV)[\s:]+(?:₹\s*)?([\d\.]+)",
                r"(Stamp duty)[\s:]+([\d\.]+\s*%)",
            ]
            for pat in patterns:
                match = re.search(pat, text, re.IGNORECASE)
                if match:
                    key_value_pairs.append(f"{match.group(1).title()}: {match.group(2).strip()}")

        # Deduplicate factual key-value pairs
        deduped_kv = list(dict.fromkeys(key_value_pairs))
        if deduped_kv:
            kv_summary = f"{scheme_name} Key Facts:\n" + "\n".join(f"- {kv}" for kv in deduped_kv)
            sections.append({
                "section": "Key Facts & Fund Parameters",
                "text": kv_summary,
            })

        # 3. Extract text paragraphs and relevant divs
        content_lines = []
        for p in soup.find_all(["p", "div", "li"]):
            p_text = p.get_text(separator=" ", strip=True)
            # Filter out boilerplate phrases
            if not p_text or len(p_text) < 30:
                continue
            if any(bp in p_text.lower() for bp in [
                "download groww app", "cookie", "privacy policy", "terms of use",
                "all rights reserved", "login", "sign up", "help & support",
                "open a free demat", "mutual funds are subject to market risks",
            ]):
                continue

            # Check if line contains relevant mutual fund facts
            if any(term in p_text.lower() for term in [
                "expense ratio", "exit load", "sip", "lumpsum", "lock-in", "benchmark",
                "riskometer", "stamp duty", "tax", "capital gains", "amc", "fund manager",
                "portfolio", "equity", "debt", "large cap", "mid cap", "small cap", "silver",
                "asset allocation", "turnover", "redemption", "nav", "objective"
            ]):
                content_lines.append(p_text)

        # Deduplicate content lines
        deduped_lines = list(dict.fromkeys(content_lines))

        # Group lines into thematic blocks
        expense_exit_lines = [l for l in deduped_lines if any(k in l.lower() for k in ["expense", "exit load", "stamp duty", "tax"])]
        if expense_exit_lines:
            sections.append({
                "section": "Expense Ratio, Exit Load and Taxes",
                "text": f"Details for {scheme_name}:\n" + "\n".join(expense_exit_lines[:6]),
            })

        investment_lines = [l for l in deduped_lines if any(k in l.lower() for k in ["sip", "minimum", "lumpsum", "lock-in", "benchmark", "risk"])]
        if investment_lines:
            sections.append({
                "section": "Investment Limits, Benchmark and Risk",
                "text": f"Investment details for {scheme_name}:\n" + "\n".join(investment_lines[:6]),
            })

        about_lines = [l for l in deduped_lines if any(k in l.lower() for k in ["objective", "fund manager", "portfolio", "allocation", "turnover"])]
        if about_lines:
            sections.append({
                "section": "Fund Management & Objective",
                "text": f"About {scheme_name}:\n" + "\n".join(about_lines[:6]),
            })

        # Full concatenated text for indexing
        full_text_blocks = [s["text"] for s in sections]
        full_text = "\n\n".join(full_text_blocks)

        logger.info(f"Successfully processed '{scheme_name}': {len(sections)} sections, {len(full_text)} chars.")
        return ScrapedDocument(
            scheme_id=scheme_id,
            scheme_name=scheme_name,
            category=category,
            url=url,
            amc=amc,
            scrape_date=scrape_date,
            full_text=full_text,
            sections=sections,
        )

    def scrape_all(self, urls_file: str = "data/urls.json") -> List[ScrapedDocument]:
        """Scrapes all scheme URLs defined in urls_file.

        A URL that fails after all retries is skipped and recorded in `self.failures`
        (edge-cases.md §7.1/§7.9); the remaining URLs are still scraped.
        """
        with open(urls_file, "r", encoding="utf-8") as f:
            targets = json.load(f)

        logger.info(f"Starting scraping pipeline for {len(targets)} URLs...")
        self.failures = []
        documents = []
        for i, target in enumerate(targets):
            try:
                documents.append(self.scrape_url(target))
            except Exception as e:
                logger.error(f"Giving up on {target.get('url')}: {e}")
                self.failures.append({
                    "scheme_id": target.get("id", ""),
                    "url": target.get("url", ""),
                    "stage": "scrape",
                    "error": f"{type(e).__name__}: {e}",
                })
            if i < len(targets) - 1:
                time.sleep(settings.scrape_delay_seconds)

        logger.info(f"Scraping complete. Successfully scraped {len(documents)}/{len(targets)} documents.")
        return documents

    def parse_saved_pages(self, html_dir: str, urls_file: str = "data/urls.json") -> List[ScrapedDocument]:
        """Development / manual-fallback only: parse saved `<scheme_id>.html` files instead of fetching.

        The scheduled refresh never calls this; it always fetches live pages.
        """
        with open(urls_file, "r", encoding="utf-8") as f:
            targets = json.load(f)
        self.failures = []
        documents = []
        for target in targets:
            scheme_id = target.get("id", target["url"].rstrip("/").split("/")[-1])
            path = os.path.join(html_dir, f"{scheme_id}.html")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    html = f.read()
                marker = detect_block_page(html)
                if marker:
                    raise BlockedPageError(f"Bot-block / CAPTCHA page detected (matched '{marker}')")
                doc = self._parse_html(
                    html, scheme_id, target.get("scheme_name", scheme_id), target.get("category", "Mutual Fund"),
                    target["url"], target.get("amc", "HDFC Mutual Fund"), self.run_date,
                )
                doc.page_sha256 = sha256_text(visible_text(html))
                documents.append(doc)
            except Exception as e:
                self.failures.append({"scheme_id": scheme_id, "url": target.get("url", ""), "stage": "scrape",
                                      "error": f"{type(e).__name__}: {e}"})
        return documents
