"""Data research script analyzing clean text, structure, and factual density
from the 5 Groww mutual fund scheme pages.
"""

import os
import re
import json
from collections import Counter
from bs4 import BeautifulSoup

RAW_DIR = "data/raw"
CORPUS_PATH = "data/vectorstore/corpus.json"

def analyze_raw_html_and_clean_text():
    print("=" * 70)
    print("1. RAW HTML vs CLEANED TEXT EXTRACTION ANALYSIS")
    print("=" * 70)

    summary_stats = []

    for fname in sorted(os.listdir(RAW_DIR)):
        if not fname.endswith(".html"):
            continue
        path = os.path.join(RAW_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        soup = BeautifulSoup(html, "html.parser")

        # Headings before stripping
        h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]
        h2_tags = [h.get_text(strip=True) for h in soup.find_all("h2")]
        h3_tags = [h.get_text(strip=True) for h in soup.find_all("h3")]
        tables = soup.find_all("table")

        # Strip non-content elements
        for tag in soup(["script", "style", "nav", "header", "footer", "form", "noscript", "svg"]):
            tag.decompose()

        cleaned_text = soup.get_text(separator=" ", strip=True)
        # Normalize whitespace
        cleaned_text_normalized = re.sub(r"\s+", " ", cleaned_text)
        words = cleaned_text_normalized.split()

        # Find key mutual fund terms presence
        facts = {
            "NAV": bool(re.search(r"\bNAV\b", cleaned_text_normalized, re.I)),
            "Expense Ratio": bool(re.search(r"Expense\s*ratio", cleaned_text_normalized, re.I)),
            "Exit Load": bool(re.search(r"Exit\s*load", cleaned_text_normalized, re.I)),
            "Min SIP": bool(re.search(r"Min\.?\s*(?:for\s*)?SIP", cleaned_text_normalized, re.I)),
            "Fund Size / AUM": bool(re.search(r"Fund\s*size|AUM", cleaned_text_normalized, re.I)),
            "Lock-in": bool(re.search(r"Lock-in", cleaned_text_normalized, re.I)),
            "Benchmark": bool(re.search(r"Benchmark", cleaned_text_normalized, re.I)),
            "Riskometer": bool(re.search(r"Riskometer|Risk", cleaned_text_normalized, re.I)),
            "Fund Manager": bool(re.search(r"Fund\s*manager", cleaned_text_normalized, re.I)),
            "Holdings": bool(re.search(r"Holdings", cleaned_text_normalized, re.I)),
        }

        stat = {
            "file": fname,
            "raw_bytes": len(html),
            "clean_chars": len(cleaned_text_normalized),
            "clean_words": len(words),
            "clean_tokens_est": int(len(words) * 1.3),
            "compression_ratio": f"{len(cleaned_text_normalized) / len(html) * 100:.2f}%",
            "h1": h1_tags,
            "h2_count": len(h2_tags),
            "h2_samples": h2_tags[:5],
            "h3_count": len(h3_tags),
            "tables_count": len(tables),
            "facts_detected": facts,
        }
        summary_stats.append(stat)

        print(f"\n📄 Scheme File: {fname}")
        print(f"  • Raw HTML size: {stat['raw_bytes']:,} bytes ({stat['raw_bytes']/1024:.1f} KB)")
        print(f"  • Clean text: {stat['clean_chars']:,} chars | {stat['clean_words']:,} words (~{stat['clean_tokens_est']:,} tokens)")
        print(f"  • Clean content payload ratio: {stat['compression_ratio']}")
        print(f"  • H1: {h1_tags}")
        print(f"  • Headings: {stat['h2_count']} H2 tags | {stat['h3_count']} H3 tags | {stat['tables_count']} HTML tables")
        print(f"  • H2 Sample Sections: {stat['h2_samples']}")
        print(f"  • Core Facts Found: {', '.join([k for k, v in facts.items() if v])}")

    return summary_stats


def analyze_current_chunks():
    print("\n" + "=" * 70)
    print("2. CURRENT CHUNKING DISTRIBUTION & CORPUS METRICS")
    print("=" * 70)

    if not os.path.exists(CORPUS_PATH):
        print("No corpus.json found.")
        return

    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    total_chunks = len(chunks)
    char_lengths = [len(c["text"]) for c in chunks]
    word_lengths = [len(c["text"].split()) for c in chunks]

    sections_counter = Counter(c.get("section_heading", "Unknown") for c in chunks)
    schemes_counter = Counter(c.get("scheme_name", "Unknown") for c in chunks)

    print(f"Total Chunks in Corpus: {total_chunks}")
    print(f"Average Chunk Length: {sum(char_lengths)/total_chunks:.1f} chars ({sum(word_lengths)/total_chunks:.1f} words)")
    print(f"Min Chunk Length: {min(char_lengths)} chars | Max Chunk Length: {max(char_lengths)} chars")

    # Length distribution histogram buckets
    buckets = {"< 100": 0, "100-300": 0, "300-500": 0, "500-700": 0, "> 700": 0}
    for l in char_lengths:
        if l < 100:
            buckets["< 100"] += 1
        elif l < 300:
            buckets["100-300"] += 1
        elif l < 500:
            buckets["300-500"] += 1
        elif l <= 700:
            buckets["500-700"] += 1
        else:
            buckets["> 700"] += 1

    print("\nChunk Size Distribution (Characters):")
    for bucket, count in buckets.items():
        pct = (count / total_chunks) * 100
        print(f"  • {bucket.ljust(10)}: {count:3d} chunks ({pct:5.1f}%) {'█' * int(pct // 3)}")

    print("\nChunks by Scheme:")
    for scheme, count in schemes_counter.items():
        print(f"  • {scheme.ljust(40)}: {count:3d} chunks")

    print("\nTop Section Headings in Chunks:")
    for section, count in sections_counter.most_common(10):
        print(f"  • {section.ljust(40)}: {count:3d} chunks")


if __name__ == "__main__":
    analyze_raw_html_and_clean_text()
    analyze_current_chunks()

