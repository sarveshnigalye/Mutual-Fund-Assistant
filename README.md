# Mutual Fund FAQ Assistant (Facts-Only Q&A)

> **Disclaimer:** Facts-only. No investment advice.

A lightweight, reliable Retrieval-Augmented Generation (RAG)-based FAQ assistant for mutual fund schemes, with Groww as the reference product context and HDFC Mutual Fund as the selected Asset Management Company (AMC).

---

## 1. Project Overview

The assistant provides objective, verifiable factual answers (expense ratio, exit load, minimum SIP, lock-in period, riskometer, benchmark index, statement download steps) strictly grounded in a curated corpus of official Groww scheme pages.

It strictly adheres to:
- **Facts-only responses:** No investment advice, opinions, or performance comparisons.
- **Strict response length:** Maximum 3 sentences per response.
- **Single citation:** Exactly one valid source link per factual answer.
- **Mandatory footer:** `Last updated from sources: <date>`.
- **Safety guardrails:** Immediate refusal of advisory queries, out-of-scope prompts, and PII detection.
- **Multi-thread support:** Independent conversation sessions with isolated message histories.

---

## 2. Selected AMC & Schemes

**AMC:** HDFC Mutual Fund (HDFC AMC)

| # | Scheme Name | Category | Reference URL |
| :---: | :--- | :--- | :--- |
| 1 | HDFC Mid-Cap Opportunities Fund | Mid Cap Fund | [Groww Scheme Page](https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth) |
| 2 | HDFC Small Cap Fund | Small Cap Fund | [Groww Scheme Page](https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth) |
| 3 | HDFC Large Cap / Top 100 Fund | Large Cap Fund | [Groww Scheme Page](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) |
| 4 | HDFC Silver ETF Fund of Fund (FoF) | Commodities / FoF | [Groww Scheme Page](https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth) |
| 5 | HDFC Multi Cap Fund | Multi Cap Fund | [Groww Scheme Page](https://groww.in/mutual-funds/hdfc-multi-cap-fund-direct-growth) |

---

## 3. Tech Stack

- **LLM Provider:** Groq (`openai/gpt-oss-120b` / `openai/gpt-oss-20b` / `llama-3.3-70b-versatile`)
- **Backend:** FastAPI + Uvicorn
- **Frontend:** Streamlit
- **Web Scraping:** Selenium + BeautifulSoup4 (Headless Chromium/Edge)
- **Vector Retrieval:** TF-IDF & Vector Cosine Similarity (`scikit-learn`, `numpy`, `scipy`) + BM25 ranking (`rank-bm25`)
- **Chat Database:** SQLite (`data/chat.db`)

---

## 4. Setup & Installation

### Prerequisites
- Python 3.10+ (Python 3.15 supported)
- Google Chrome or Microsoft Edge browser
- Groq API Key

### Quick Start

1. **Clone & enter directory:**
   ```bash
   cd "f:\AI projects\Milestone2"
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment:**
   ```bash
   copy .env.example .env
   ```
   Add your `GROQ_API_KEY` in `.env`.

5. **Verify setup with Smoke Test:**
   ```bash
   python scripts/smoke_test.py
   ```

---

## 5. Project Structure

```
Milestone2/
├── Docs/
│   ├── Problem Statement.txt
│   ├── problemstatement.md
│   ├── architecture.md
│   ├── implementation-plan.md
│   └── edge-cases.md
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI entrypoint
│   ├── config.py                # Pydantic configuration loader
│   ├── ingestion/               # Scraping, chunking, indexing
│   ├── core/                    # Classifier, retriever, generator, safety
│   ├── chat/                    # Multi-thread chat manager (SQLite)
│   ├── api/                     # REST API routes
│   └── prompts/                 # Prompt templates & refusal responses
├── frontend/
│   └── streamlit_app.py         # Streamlit UI
├── data/
│   ├── urls.json                # 5 curated Groww scheme URLs
│   ├── vectorstore/             # Persistent index storage
│   ├── raw/                     # Raw scraped data cache
│   └── chat.db                  # SQLite chat history
├── scripts/
│   ├── smoke_test.py            # Phase 0 verification test
│   ├── ingest.py                # Phase 1 ingestion script
│   └── reset_db.py              # Database reset utility
├── tests/                       # Pytest test suite
├── .env.example                 # Environment variable template
├── .gitignore                   # Git ignore file
├── requirements.txt             # Python package dependencies
└── README.md                    # Project documentation
```

---

## 6. Implementation Status

- [x] **Phase 0:** Project Bootstrap, Environment Setup, Groq & Selenium Integration (Verified)
- [ ] **Phase 1:** Data Ingestion Pipeline (Groww Scraper & Indexer)
- [ ] **Phase 2:** Core RAG Engine (Retriever & LLM Generator)
- [ ] **Phase 3:** Safety & Guardrails Layer (PII Scanner & Refusal Handling)
- [ ] **Phase 4:** Multi-Thread Chat Management (SQLite CRUD)
- [ ] **Phase 5:** Frontend UI (Streamlit) & FastAPI Endpoints
- [ ] **Phase 6:** End-to-End Integration & Edge Case Testing
- [ ] **Phase 7:** Documentation & Release

---

## 7. Disclaimer
Facts-only. No investment advice. This system provides purely objective, verifiable mutual fund information from official public scheme pages. It does not provide financial planning, recommendation, or investment advice.

