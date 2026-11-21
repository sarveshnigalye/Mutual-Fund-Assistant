"""Quality checks for a built index (Phase 7.7 validation gate).

Pure functions over the corpus (`corpus.json` rows) and run metadata, so the gate's rules
can be unit-tested without a browser or a vector store. `scripts/validate_index.py` adds
the ChromaDB count check and the Phase 6 regression tests on top.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.ingestion.normalizer import numeric_key

MIN_CHUNKS_PER_SCHEME = 5
CHUNK_COUNT_WARN_RATIO = 0.30
KEY_FACTS_MARKER = "key facts"

# Fields every scheme must expose; extraction patterns were checked against the live corpus.
CORE_FIELDS: Dict[str, Tuple[str, List[re.Pattern]]] = {
    "expense_ratio": ("Expense ratio", [re.compile(r"expense ratio[^0-9\n]{0,40}?(\d+(?:\.\d+)?%)", re.IGNORECASE)]),
    "exit_load": ("Exit load", [re.compile(
        r"exit load\s*(?::\s*|-\s*|of\s+|is\s+)?"
        r"(nil|\d+(?:\.\d+)?%(?:\s+if\s+redeemed\s+within\s+\d+\s+(?:years?|months?|days?))?)",
        re.IGNORECASE,
    )]),
    "min_sip": ("Minimum SIP", [
        re.compile(r"min(?:imum)?\.?\s*(?:for\s*)?sip\b[^₹\d\n]{0,30}₹?\s?(\d[\d,]*)", re.IGNORECASE),
        re.compile(r"\bsip\s+₹\s?(\d[\d,]*)", re.IGNORECASE),
    ]),
    "benchmark": ("Benchmark", [re.compile(
        r"[Bb]enchmark(?:\s+[Ii]ndex)?\s*:?\s+([A-Z][^\n]{3,80}?)(?=\s+Scheme Information|\s+-\s|\s*\n|$)"
    )]),
    "riskometer": ("Riskometer", [re.compile(
        r"\b(very high|moderately high|moderately low|low to moderate|high|moderate|low)\s+risk\b", re.IGNORECASE
    )]),
}

# Facts that are expected to move daily: shown in the diff, never warned on.
INFO_FIELDS: Dict[str, Tuple[str, List[re.Pattern]]] = {
    "aum": ("Fund size (AUM)", [re.compile(r"Fund size\s*\(AUM\)\s*₹\s?(\d[\d,]*(?:\.\d+)?(?:\s*Cr)?)", re.IGNORECASE)]),
}


@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors


def load_expected_schemes(urls_path: str = "data/urls.json") -> Dict[str, str]:
    """{scheme_id: url} for every scheme the corpus must contain."""
    with open(urls_path, "r", encoding="utf-8") as f:
        return {u["id"]: u["url"] for u in json.load(f)}


def _scheme_text(chunks: Iterable[Dict[str, Any]]) -> str:
    """Key Facts chunks first, so a fact is read from the structured block when present."""
    chunks = list(chunks)
    key_facts = [c for c in chunks if KEY_FACTS_MARKER in str(c.get("section_heading", "")).lower()]
    rest = [c for c in chunks if c not in key_facts]
    return "\n".join(str(c.get("text", "")) for c in key_facts + rest)


def _extract(text: str, patterns: List[re.Pattern]) -> Optional[str]:
    for pattern in patterns:
        m = pattern.search(text)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


def group_by_scheme(corpus: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for c in corpus:
        grouped.setdefault(str(c.get("scheme_id", "")), []).append(c)
    return grouped


def extract_facts(corpus: List[Dict[str, Any]], include_info: bool = True) -> Dict[str, Dict[str, Optional[str]]]:
    """{scheme_id: {field: value or None}} for the core (and optionally info) fields."""
    fields = {**CORE_FIELDS, **(INFO_FIELDS if include_info else {})}
    facts = {}
    for scheme_id, chunks in sorted(group_by_scheme(corpus).items()):
        text = _scheme_text(chunks)
        facts[scheme_id] = {name: _extract(text, patterns) for name, (_, patterns) in fields.items()}
    return facts


def _fact_key(value: Optional[str]) -> Optional[str]:
    return numeric_key(value).lower() if value else None


def validate_corpus(
    corpus: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]],
    expected_schemes: Dict[str, str],
    expected_date: Optional[str] = None,
    expected_run_id: Optional[str] = None,
    min_chunks: int = MIN_CHUNKS_PER_SCHEME,
) -> ValidationResult:
    """Blocking checks on a freshly built corpus. Any error means: do not publish."""
    result = ValidationResult()

    if metadata is None:
        result.errors.append("Run metadata is missing or unreadable.")
        metadata = {}
    for failure in metadata.get("failures") or []:
        result.errors.append(
            f"Page `{failure.get('scheme_id')}` failed at {failure.get('stage')}: {failure.get('error')}"
        )

    if not corpus:
        result.errors.append("Corpus is empty.")
        return result

    if metadata and metadata.get("total_chunks") not in (None, len(corpus)):
        result.errors.append(
            f"Metadata says {metadata.get('total_chunks')} chunks but corpus has {len(corpus)}."
        )

    ids = [c.get("chunk_id") for c in corpus]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        result.errors.append(f"{len(duplicates)} duplicate chunk IDs (e.g. `{duplicates[0]}`).")

    missing_url = [c.get("chunk_id") for c in corpus if not c.get("source_url")]
    if missing_url:
        result.errors.append(f"{len(missing_url)} chunks have no source_url (e.g. `{missing_url[0]}`).")
    missing_date = [c.get("chunk_id") for c in corpus if not c.get("scrape_date")]
    if missing_date:
        result.errors.append(f"{len(missing_date)} chunks have no scrape_date (e.g. `{missing_date[0]}`).")

    run_date = expected_date or metadata.get("scrape_date")
    if run_date:
        stale = [c for c in corpus if c.get("scrape_date") and c.get("scrape_date") != run_date]
        if stale:
            result.errors.append(
                f"{len(stale)} chunks have a stale scrape_date (e.g. {stale[0].get('scrape_date')}, expected {run_date})."
            )
    if expected_run_id:
        wrong_run = [c for c in corpus if str(c.get("run_id", "")) != str(expected_run_id)]
        if wrong_run:
            result.errors.append(f"{len(wrong_run)} chunks are not from run {expected_run_id}.")

    allowed_urls = set(expected_schemes.values())
    foreign = sorted({c.get("source_url") for c in corpus if c.get("source_url") and c.get("source_url") not in allowed_urls})
    if foreign:
        result.errors.append(f"Chunks cite URLs outside data/urls.json: {', '.join(foreign[:3])}")

    grouped = group_by_scheme(corpus)
    facts = extract_facts(corpus, include_info=False)
    for scheme_id in expected_schemes:
        chunks = grouped.get(scheme_id, [])
        if not chunks:
            result.errors.append(f"Scheme `{scheme_id}` is missing from the index.")
            continue
        if len(chunks) < min_chunks:
            result.errors.append(f"Scheme `{scheme_id}` has {len(chunks)} chunks (< {min_chunks}).")
        if not any(KEY_FACTS_MARKER in str(c.get("section_heading", "")).lower() for c in chunks):
            result.errors.append(f"Scheme `{scheme_id}` has no Key Facts chunk.")
        for name, value in facts.get(scheme_id, {}).items():
            if not value:
                result.errors.append(f"Scheme `{scheme_id}`: core field '{CORE_FIELDS[name][0]}' not found.")

    unexpected = sorted(set(grouped) - set(expected_schemes))
    if unexpected:
        result.warnings.append(f"Index contains schemes not in data/urls.json: {', '.join(unexpected)}")
    return result


def compare_with_previous(
    current_corpus: List[Dict[str, Any]],
    previous_corpus: Optional[List[Dict[str, Any]]],
    threshold: float = CHUNK_COUNT_WARN_RATIO,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Non-blocking diff vs the previous snapshot.

    Returns (warnings, rows); each row is {scheme_id, field, label, previous, current, changed, expected}.
    Core-field changes and chunk-count swings > threshold are warnings; info fields (AUM) are listed only.
    """
    warnings: List[str] = []
    current_facts = extract_facts(current_corpus)
    if not previous_corpus:
        rows = [
            {"scheme_id": s, "field": f, "label": {**CORE_FIELDS, **INFO_FIELDS}[f][0],
             "previous": None, "current": v, "changed": False, "expected": f in INFO_FIELDS}
            for s, fields in current_facts.items() for f, v in fields.items()
        ]
        return warnings, rows

    previous_facts = extract_facts(previous_corpus)
    rows = []
    for scheme_id, fields in current_facts.items():
        for name, value in fields.items():
            prev = previous_facts.get(scheme_id, {}).get(name)
            changed = prev is not None and _fact_key(prev) != _fact_key(value)
            expected = name in INFO_FIELDS
            label = {**CORE_FIELDS, **INFO_FIELDS}[name][0]
            rows.append({"scheme_id": scheme_id, "field": name, "label": label,
                         "previous": prev, "current": value, "changed": changed, "expected": expected})
            if changed and not expected:
                warnings.append(f"`{scheme_id}` {label} changed: {prev} → {value}")

    prev_total, cur_total = len(previous_corpus), len(current_corpus)
    if prev_total and abs(cur_total - prev_total) / prev_total > threshold:
        warnings.append(f"Total chunk count moved {prev_total} → {cur_total} (> {threshold:.0%}).")
    prev_counts = {k: len(v) for k, v in group_by_scheme(previous_corpus).items()}
    for scheme_id, chunks in group_by_scheme(current_corpus).items():
        before = prev_counts.get(scheme_id)
        if before and abs(len(chunks) - before) / before > threshold:
            warnings.append(f"`{scheme_id}` chunk count moved {before} → {len(chunks)} (> {threshold:.0%}).")
    return warnings, rows
