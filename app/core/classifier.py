"""Two-layer query classifier (Layer 1 Heuristics + Layer 2 Groq LLM Zero-shot)."""

import json
import logging
import os
import re
from enum import Enum
from typing import Optional, Tuple

from groq import Groq

from app.config import settings
from app.core.retriever import SUPPORTED_SCHEMES, detect_scheme_name
from app.core.safety import scan_pii

logger = logging.getLogger("core.classifier")


class QueryCategory(str, Enum):
    FACTUAL = "FACTUAL"
    ADVISORY = "ADVISORY"
    COMPARATIVE = "COMPARATIVE"
    PERFORMANCE = "PERFORMANCE"
    PII_DETECTED = "PII_DETECTED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    INCONCLUSIVE = "INCONCLUSIVE"


# Load refusal templates
REFUSAL_FILE = os.path.join(os.path.dirname(__file__), "..", "prompts", "refusal_templates.json")
try:
    with open(REFUSAL_FILE, "r", encoding="utf-8") as f:
        REFUSAL_TEMPLATES = json.load(f)
except Exception:
    REFUSAL_TEMPLATES = {
        "ADVISORY": "I'm a facts-only assistant and cannot provide investment advice. For investment guidance, consult a SEBI-registered advisor: https://investor.sebi.gov.in/",
        "COMPARATIVE": "I can only share factual details about individual schemes and cannot compare funds. Review factsheets at: https://www.hdfcfund.com",
        "PII_DETECTED": "⚠️ Please do not share personal information. I do not collect or process personal data: https://www.hdfcfund.com/investor-services",
        "PERFORMANCE": "I cannot provide return calculations or performance comparisons. Refer to official scheme details: {factsheet_link}",
        "OUT_OF_SCOPE": "This question is outside my scope. Learn about mutual funds at: https://www.amfiindia.com/investor-corner/knowledge-center",
    }

# Layer 1 Heuristics Patterns
ADVISORY_PATTERNS = [
    r"\bshould\s+(?:i|we)\b",
    r"\brecommend\b",
    r"\bsuggest\b",
    r"\bworth\s+(?:it|investing)\b",
    r"\bgood\s+fund\b",
    r"\bbest\s+fund\b",
    r"\btop\s+fund\b",
    r"\bwhich\s+fund\s+is\s+better\b",
    r"\boutperform\b",
    r"\bpredict\b",
    r"\bwill\s+it\s+(?:grow|give|make)\b",
    r"\bis\s+it\s+(?:safe|good|profitable)\s+to\s+invest\b",
    r"\bright\s+time\s+to\s+invest\b",
    r"\bwhere\s+should\s+i\s+put\s+my\s+money\b",
    r"\binvestment\s+advice\b",
    r"\bcan\s+i\s+get\s+rich\b",
    r"\bbuy\s+or\s+sell\b",
]

COMPARATIVE_PATTERNS = [
    r"\bwhich\s+is\s+better\b",
    r"\b(?:vs|versus)\b",
    r"\bcompare\b",
    r"\bcomparison\b",
    r"\bbetter\s+than\b",
    r"\bdifference\s+between\b",
    r"\bor\s+should\s+i\s+choose\b",
    r"\bwhich\s+one\s+should\s+i\s+(?:pick|buy|invest)\b",
]

PERFORMANCE_PATTERNS = [
    r"\b(?:returns?|past\s+performance|historical\s+returns?)\b",
    r"\bcagr\b",
    r"\bannualized\s+returns?\b",
    r"\bhow\s+much\s+(?:return|profit|gain|loss)\b",
    r"\b(?:1|3|5|10)\s*years?\s+returns?\b",
    r"\bnav\s+history\b",
    r"\btrack\s+record\b",
]

OUT_OF_SCOPE_PATTERNS = [
    r"\b(?:weather|temperature|forecast|rain|climate)\b",
    r"\b(?:cricket|football|sports|ipl|world\s+cup|match|score)\b",
    r"\b(?:recipe|cook|food|restaurant|dinner|lunch)\b",
    r"\b(?:joke|poem|story|song|movie|actor|actress|cinema)\b",
    r"\b(?:prime\s+minister|president|modi|biden|trump|politics|election)\b",
    r"\bcapital\s+of\b",
    r"\bwhat\s+is\s+the\s+meaning\s+of\s+life\b",
    r"\b(?:system\s+prompt|initial\s+instructions|prompt\s+instructions|internal\s+prompt)\b",
    r"^(?:hi|hello|hey|good\s+morning|good\s+evening|howdy|sup)[\s!\.]*$",
]

FACTUAL_PATTERNS = [
    r"\bexpense\s+ratio\b",
    r"\bter\b",
    r"\bexit\s+load\b",
    r"\block[\s-]in(?:\s+period)?\b",
    r"\bmin(?:imum)?\s+(?:for\s+)?sip\b",
    r"\bmin(?:imum)?\s+(?:for\s+)?lumpsum\b",
    r"\bmin(?:imum)?\s+investment\b",
    r"\b(?:fund\s+size|aum)\b",
    r"\bnav\b",
    r"\bportfolio\s+turnover\b",
    r"\bfund\s+manager\b",
    r"\brisk(?:ometer)?\b",
    r"\bbenchmark\b",
    r"\bstamp\s+duty\b",
    r"\b(?:stcg|ltcg|taxation|tax\s+implications)\b",
    r"\bholdings\b",
    r"\basset\s+allocation\b",
    r"\binception\s+date\b",
]


class QueryClassifier:
    """Classifies user queries using a 2-layer safety funnel."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.groq_api_key
        self.model = model or settings.groq_model
        self.client: Optional[Groq] = None
        if self.api_key:
            self.client = Groq(api_key=self.api_key)

    def classify_layer1(self, query: str) -> QueryCategory:
        """
        Fast Layer 1 regex heuristic classification without API calls.
        """
        query_clean = query.strip().lower()

        # 1. PII Check (Immediate Refusal)
        has_pii, _ = scan_pii(query)
        if has_pii:
            return QueryCategory.PII_DETECTED

        # 2. Advisory Check
        for pat in ADVISORY_PATTERNS:
            if re.search(pat, query_clean):
                return QueryCategory.ADVISORY

        # 3. Comparative Check
        for pat in COMPARATIVE_PATTERNS:
            if re.search(pat, query_clean):
                return QueryCategory.COMPARATIVE

        # 4. Performance Check
        for pat in PERFORMANCE_PATTERNS:
            if re.search(pat, query_clean):
                return QueryCategory.PERFORMANCE

        # 5. Out of Scope Check
        for pat in OUT_OF_SCOPE_PATTERNS:
            if re.search(pat, query_clean):
                return QueryCategory.OUT_OF_SCOPE

        # 6. Factual Check
        for pat in FACTUAL_PATTERNS:
            if re.search(pat, query_clean):
                return QueryCategory.FACTUAL

        return QueryCategory.INCONCLUSIVE

    def classify_layer2_llm(self, query: str) -> QueryCategory:
        """
        Layer 2 Groq zero-shot classification for ambiguous queries.
        """
        if not self.client:
            return QueryCategory.FACTUAL

        prompt = (
            "You are a strict query classifier for an HDFC mutual fund FAQ assistant.\n"
            "Classify the following query into exactly ONE of these categories:\n"
            "- FACTUAL: Asking for verifiable facts SPECIFICALLY about mutual fund schemes or investing (e.g. expense ratio, exit load, minimum SIP, lock-in, NAV, fund manager, riskometer, benchmark, process). "
            "Note: questions about general world trivia (politics, weather, geography, celebrities, general science) are OUT_OF_SCOPE.\n"
            "- ADVISORY: Asking for investment advice, recommendations, fund selection, opinions, or predictions ('Should I invest?', 'Is this good?').\n"
            "- COMPARATIVE: Comparing two or more funds or asking which is better.\n"
            "- PERFORMANCE: Asking for returns, CAGR, profit/loss calculations, or past performance.\n"
            "- OUT_OF_SCOPE: Unrelated topics, greetings, weather, politics, non-financial trivia.\n\n"
            "Respond with ONLY the category name. Do not include any explanations.\n\n"
            f"USER QUERY: {query}\n\n"
            "CATEGORY:"
        )

        try:
            res = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=25,
            )
            raw = (res.choices[0].message.content or "").strip().upper()
            # Clean possible markdown or reasoning tokens
            cleaned = re.sub(r"[^A-Z_]", "", raw)

            for cat in [
                QueryCategory.FACTUAL,
                QueryCategory.ADVISORY,
                QueryCategory.COMPARATIVE,
                QueryCategory.PERFORMANCE,
                QueryCategory.OUT_OF_SCOPE,
            ]:
                if cat.value in cleaned:
                    return cat

            return QueryCategory.FACTUAL
        except Exception as e:
            logger.warning(f"Layer 2 classification failed: {e}. Defaulting to FACTUAL.")
            return QueryCategory.FACTUAL

    def classify(self, query: str) -> QueryCategory:
        """
        Main entry point: executes Layer 1 heuristics, escalating to Layer 2 if inconclusive.
        """
        cat1 = self.classify_layer1(query)
        if cat1 != QueryCategory.INCONCLUSIVE:
            return cat1

        return self.classify_layer2_llm(query)

    def get_refusal(self, category: QueryCategory, query: str = "") -> str:
        """
        Retrieves the standardized refusal template text for a non-factual category.
        """
        if category == QueryCategory.PERFORMANCE:
            detected = detect_scheme_name(query)
            link = SUPPORTED_SCHEMES[detected]["url"] if detected else "https://www.hdfcfund.com"
            tmpl = REFUSAL_TEMPLATES.get("PERFORMANCE", "")
            return tmpl.format(factsheet_link=link)

        tmpl = REFUSAL_TEMPLATES.get(category.value, REFUSAL_TEMPLATES.get("OUT_OF_SCOPE", ""))
        return tmpl


# Global classifier instance
query_classifier = QueryClassifier()
