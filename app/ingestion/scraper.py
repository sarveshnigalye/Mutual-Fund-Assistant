"""Web scraper for Groww mutual fund scheme pages using Selenium."""

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from selenium import webdriver

from app.config import settings

logger = logging.getLogger("ingestion.scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


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
    ):
        self.scheme_id = scheme_id
        self.scheme_name = scheme_name
        self.category = category
        self.url = url
        self.amc = amc
        self.scrape_date = scrape_date
        self.full_text = full_text
        self.sections = sections

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
        }


class GrowwScraper:
    """Automates headless browser scraping of Groww mutual fund scheme pages."""

    def __init__(self, raw_cache_dir: str = "data/raw"):
        self.raw_cache_dir = raw_cache_dir
        os.makedirs(self.raw_cache_dir, exist_ok=True)

    def _create_driver(self) -> webdriver.Remote:
        """Instantiates a headless Chromium or Edge driver based on configuration."""
        browser_type = settings.browser_type.lower()

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
            options.add_argument(
                "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
            )
            service = EdgeService(EdgeChromiumDriverManager().install())
            return webdriver.Edge(service=service, options=options)
        else:
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.chrome.service import Service as ChromeService
            from webdriver_manager.chrome import ChromeDriverManager

            options = ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            service = ChromeService(ChromeDriverManager().install())
            return webdriver.Chrome(service=service, options=options)

    def scrape_url(self, target: Dict[str, str], max_retries: int = 3) -> ScrapedDocument:
        """
        Scrapes a single Groww mutual fund scheme page.
        Retries up to max_retries with exponential backoff on transient errors.
        """
        url = target["url"]
        scheme_id = target.get("id", url.rstrip("/").split("/")[-1])
        scheme_name = target.get("scheme_name", scheme_id)
        category = target.get("category", "Mutual Fund")
        amc = target.get("amc", "HDFC Mutual Fund")
        scrape_date = datetime.now().strftime("%Y-%m-%d")

        raw_cache_path = os.path.join(self.raw_cache_dir, f"{scheme_id}.html")

        # Check for cached HTML or fetch via Selenium
        html = None
        for attempt in range(1, max_retries + 1):
            driver = None
            try:
                logger.info(f"[{attempt}/{max_retries}] Scraping '{scheme_name}' from: {url}")
                driver = self._create_driver()
                driver.get(url)
                time.sleep(settings.scrape_delay_seconds + 3)  # Wait for dynamic JS content
                html = driver.page_source

                # Validate content length
                if len(html) < 2000:
                    raise ValueError(f"Extracted HTML too short ({len(html)} bytes), page may not have rendered")

                # Cache raw HTML
                with open(raw_cache_path, "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info(f"Cached raw HTML to {raw_cache_path} ({len(html)} bytes)")
                break
            except Exception as e:
                logger.warning(f"Attempt {attempt} failed for {url}: {e}")
                if attempt == max_retries:
                    # Fallback to cached HTML if available
                    if os.path.exists(raw_cache_path):
                        logger.info(f"Using previously cached HTML from {raw_cache_path}")
                        with open(raw_cache_path, "r", encoding="utf-8") as f:
                            html = f.read()
                    else:
                        raise e
                time.sleep(attempt * 2)
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass

        # Parse and extract clean factual sections
        return self._parse_html(html, scheme_id, scheme_name, category, url, amc, scrape_date)

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
        """Scrapes all scheme URLs defined in urls_file."""
        with open(urls_file, "r", encoding="utf-8") as f:
            targets = json.load(f)

        logger.info(f"Starting scraping pipeline for {len(targets)} URLs...")
        documents = []
        for target in targets:
            doc = self.scrape_url(target)
            documents.append(doc)
            time.sleep(settings.scrape_delay_seconds)

        logger.info(f"Scraping complete. Successfully scraped {len(documents)}/{len(targets)} documents.")
        return documents
