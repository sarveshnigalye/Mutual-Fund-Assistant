"""Comprehensive data research script on clean data from the 5 Groww HDFC mutual fund URLs.
Generates full statistical metrics, content categorization, and architecture benchmarks.
"""

import os
import re
import json
from bs4 import BeautifulSoup

RAW_DIR = "data/raw"
URLS_FILE = "data/urls.json"

def run_deep_research():
    with open(URLS_FILE, "r", encoding="utf-8") as f:
        urls_meta = json.load(f)

    results = {}
    total_raw_bytes = 0
    total_clean_chars = 0
    total_clean_words = 0

    all_faqs = []
    all_key_facts = {}

    for item in urls_meta:
        scheme_id = item["id"]
        scheme_name = item["scheme_name"]
        file_name = f"{scheme_id}.html"
        file_path = os.path.join(RAW_DIR, file_name)

        if not os.path.exists(file_path):
            continue

        raw_size = os.path.getsize(file_path)
        total_raw_bytes += raw_size

        with open(file_path, "r", encoding="utf-8") as f:
            html = f.read()

        soup = BeautifulSoup(html, "html.parser")

        # Extract structured data before stripping
        # 1. Page title & H1
        title = soup.title.get_text(strip=True) if soup.title else ""
        h1 = [h.get_text(strip=True) for h in soup.find_all("h1")]

        # 2. Extract FAQs
        scheme_faqs = []
        for tag in soup.find_all(["h3", "div", "p"]):
            text = tag.get_text(strip=True)
            if text.endswith("?") and 15 < len(text) < 120:
                if text not in scheme_faqs and "IPO" not in text and "Grey" not in text:
                    scheme_faqs.append(text)
        all_faqs.extend(scheme_faqs)

        # 3. Clean DOM
        for tag in soup(["script", "style", "nav", "header", "footer", "form", "noscript", "svg", "button"]):
            tag.decompose()

        cleaned_text = soup.get_text(separator=" ", strip=True)
        cleaned_text = re.sub(r"\s+", " ", cleaned_text)

        clean_chars = len(cleaned_text)
        clean_words = len(cleaned_text.split())
        clean_tokens = int(clean_words * 1.33)  # standard English words to BPE tokens ratio

        total_clean_chars += clean_chars
        total_clean_words += clean_words

        # Specific Factual Value Extraction
        facts = {}
        # TER
        m = re.search(r"Expense\s*ratio[\s:]+([\d\.]+%)", cleaned_text, re.I)
        facts["expense_ratio"] = m.group(1) if m else "N/A"
        # AUM
        m = re.search(r"Fund\s*size\s*\(AUM\)[\s:]+(₹?[\d,\.]+\s*(?:Cr|Crore)?)", cleaned_text, re.I)
        facts["aum"] = m.group(1) if m else "N/A"
        # Min SIP
        m = re.search(r"Min\.?\s*for\s*SIP[\s:]+(₹?[\d,]+)", cleaned_text, re.I)
        facts["min_sip"] = m.group(1) if m else "N/A"
        # NAV
        m = re.search(r"NAV[:\s]+(?:[\d\w\s']+)?(₹?[\d\.]+)", cleaned_text, re.I)
        facts["nav"] = m.group(1) if m else "N/A"
        # Benchmark
        m = re.search(r"Benchmark[\s:]+([^\.]+?TRI|NIFTY[^\.]+?Index|BSE[^\.]+?Index|Domestic Price of Silver[^\.]+)", cleaned_text, re.I)
        facts["benchmark"] = m.group(1).strip() if m else "N/A"
        # Exit load
        m = re.search(r"Exit\s*load[:\s]+([^\.]+?\.)", cleaned_text, re.I)
        facts["exit_load"] = m.group(1).strip() if m else "N/A"

        all_key_facts[scheme_id] = facts

        results[scheme_id] = {
            "scheme_name": scheme_name,
            "raw_bytes": raw_size,
            "clean_chars": clean_chars,
            "clean_words": clean_words,
            "clean_tokens": clean_tokens,
            "signal_ratio": round(clean_chars / raw_size * 100, 2),
            "faqs_count": len(scheme_faqs),
            "facts": facts,
        }

    output = {
        "summary": {
            "total_schemes": len(results),
            "total_raw_bytes": total_raw_bytes,
            "total_raw_kb": round(total_raw_bytes / 1024, 1),
            "total_clean_chars": total_clean_chars,
            "total_clean_words": total_clean_words,
            "total_clean_tokens_est": int(total_clean_words * 1.33),
            "overall_signal_ratio": f"{total_clean_chars / total_raw_bytes * 100:.2f}%",
            "overall_noise_ratio": f"{(1 - total_clean_chars / total_raw_bytes) * 100:.2f}%",
        },
        "schemes": results,
        "unique_faqs": sorted(list(dict.fromkeys(all_faqs))),
        "key_facts_matrix": all_key_facts,
    }

    print(json.dumps(output, indent=2))
    with open("data/clean_data_research.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

if __name__ == "__main__":
    run_deep_research()
