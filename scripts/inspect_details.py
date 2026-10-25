"""Detailed inspection of FAQs, tables, and structured cards in raw Groww HTML."""

import os
import re
from bs4 import BeautifulSoup

RAW_DIR = "data/raw"

def inspect_faqs_and_tables():
    for fname in sorted(os.listdir(RAW_DIR)):
        if not fname.endswith(".html"):
            continue
        path = os.path.join(RAW_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        soup = BeautifulSoup(html, "html.parser")

        # 1. Inspect FAQ accordion items
        faq_questions = []
        for tag in soup.find_all(["h3", "div", "span", "p"]):
            t = tag.get_text(strip=True)
            if t.endswith("?") and len(t) > 15 and len(t) < 120:
                if t not in faq_questions:
                    faq_questions.append(t)

        # 2. Inspect holdings tables
        holdings = []
        for tr in soup.find_all("tr"):
            tds = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(tds) >= 3 and any("%" in cell for cell in tds):
                holdings.append(" | ".join(tds))

        # 3. Inspect Fund Manager mentions
        managers = []
        for div in soup.find_all(["div", "p"]):
            text = div.get_text(strip=True)
            if "manages this scheme" in text.lower() or "fund manager" in text.lower():
                if len(text) < 150 and text not in managers:
                    managers.append(text)

        print(f"\n==================== {fname} ====================")
        print(f"Total FAQs detected ({len(faq_questions)}):")
        for q in faq_questions[:6]:
            print(f"  ? {q}")
        print(f"Total Table Rows with %: {len(holdings)}")
        if holdings:
            print(f"  Sample row: {holdings[0]}")
        print(f"Fund Manager references ({len(managers)}):")
        for m in managers[:3]:
            print(f"  👤 {m}")

if __name__ == "__main__":
    inspect_faqs_and_tables()

