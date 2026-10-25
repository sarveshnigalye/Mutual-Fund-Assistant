# Problem Statement: Mutual Fund FAQ Assistant (Facts-Only Q&A)

## 1. Overview
The objective of this project is to build a **facts-only FAQ assistant** for mutual fund schemes, using **Groww** as the reference product context. The assistant answers objective, verifiable queries related to mutual funds by retrieving information exclusively from official public sources—such as Asset Management Company (AMC) websites, the Association of Mutual Funds in India (AMFI), and the Securities and Exchange Board of India (SEBI).

> [!IMPORTANT]
> The system must **strictly avoid providing investment advice, opinions, or recommendations**. Every response must include a single, clear source citation link and adhere to defined constraints around clarity, accuracy, and regulatory compliance.

---

## 2. Objective
Design and implement a lightweight **Retrieval-Augmented Generation (RAG)**-based assistant that:
- Answers factual queries about mutual fund schemes accurately.
- Uses a curated corpus of official documents.
- Delivers concise, source-backed responses.

---

## 3. Target Users
- **Retail Investors:** Users seeking objective, factual information when exploring or comparing mutual fund schemes.
- **Customer Support & Content Teams:** Support agents and content teams handling high-frequency, repetitive mutual fund queries.

---

## 4. Scope of Work

### 4.1. Corpus Definition
1. **Asset Management Company (AMC):** Selected AMC: **HDFC Mutual Fund (HDFC AMC)**.
2. **Mutual Fund Schemes (Category Diversity):**
   - **Mid-Cap:** HDFC Mid-Cap Opportunities Fund
   - **Small-Cap:** HDFC Small Cap Fund
   - **Large-Cap:** HDFC Large Cap / Top 100 Fund
   - **Commodities / FoF:** HDFC Silver ETF Fund of Fund (FoF)
   - **Multi-Cap:** HDFC Multi Cap Fund
3. **Reference Product Context (Groww Scheme URLs):**
   - [HDFC Mid Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth)
   - [HDFC Small Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth)
   - [HDFC Large Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth)
   - [HDFC Silver ETF FoF Direct Growth](https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth)
   - [HDFC Multi Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-multi-cap-fund-direct-growth)
4. **Official Public URLs:** Curate and index **15–25 official public URLs** corresponding to these schemes, including:
   - Scheme Factsheets
   - KIM (Key Information Memorandum)
   - SID (Scheme Information Document)
   - AMC FAQ / Help pages
   - AMFI & SEBI guidance pages
   - Statement and tax/capital gains document download guides

### 4.2. FAQ Assistant Requirements
- **Factual Query Coverage:** Answer objective queries such as:
  - Expense ratio (TER - Regular / Direct)
  - Exit load details and applicable periods
  - Minimum SIP and lump-sum investment amounts
  - ELSS lock-in period requirements
  - Riskometer classification (e.g., Low, Moderate, Very High)
  - Benchmark index (e.g., NIFTY 50 TRI, BSE 500 TRI)
  - Step-by-step procedures to download account statements or capital gains reports
- **Response Format Constraints:**
  - **Sentence Count:** Limited to a maximum of **3 sentences** per response.
  - **Citation:** Exactly **one** official citation link per response.
  - **Mandatory Footer:** Every response must conclude with:
    > `Last updated from sources: <date>`

### 4.3. Refusal Handling
The assistant must identify and refuse non-factual, subjective, or advisory queries, such as:
- *"Should I invest in this fund?"*
- *"Which fund is better?"*
- *"Will this fund outperform the market?"*

**Refusal Response Requirements:**
- Be polite and clearly worded.
- Explicitly reinforce the **facts-only limitation**.
- Provide a relevant educational link (e.g., AMFI Investor Education or SEBI Investor portal).

### 4.4. User Interface (Minimal)
The solution should include a simple, user-friendly interface with:
- A welcome message introducing the assistant's capabilities and scope.
- At least three example questions demonstrating factual queries.
- A prominent, visible disclaimer:
  > **“Facts-only. No investment advice.”**

---

## 5. Constraints & Compliance

| Area | Guidelines & Rules |
| :--- | :--- |
| **Data and Sources** | Use **only official public sources** (AMC, AMFI, SEBI). Third-party blogs, forums, or aggregator websites are strictly prohibited. |
| **Privacy and Security** | **Do not collect, store, or process Personally Identifiable Information (PII) or credentials**, such as PAN, Aadhaar numbers, account numbers, OTPs, email addresses, or phone numbers. |
| **Content Restrictions** | **No investment advice or recommendations.** No performance comparisons or return calculations. For performance-related queries, provide a direct link to the official factsheet only. |
| **Transparency & Brevity** | Responses must be short, factual, and verifiable against corpus sources. Every answer must include a citation link and a last updated date. |

---

## 6. Expected Deliverables

1. **README Document:**
   - Complete setup and run instructions.
   - Selected AMC and chosen schemes.
   - Architecture overview detailing the RAG pipeline (document ingestion, chunking, embeddings, vector database, LLM, prompt templates).
   - Known limitations and assumptions.
2. **Disclaimer Snippet:**
   - Prominently displayed: `“Facts-only. No investment advice.”`
3. **Multiple Chat Thread Support:**
   - A RAG-based chatbot architecture capable of handling multiple independent conversations or threads simultaneously.

---

## 7. Success Criteria

- **Accurate Information Retrieval:** Zero hallucination on factual mutual fund parameters sourced from official AMC/AMFI/SEBI data.
- **Strict Adherence to Facts-Only Policy:** Absolute prevention of advisory creep, bias, or speculative answers.
- **Consistent Citations & Footers:** 100% adherence to single-citation formatting and last updated date stamps.
- **Polite & Safe Refusals:** Immediate, safe redirection of subjective, advisory, or comparative investment questions to educational resources.
- **Clean UI & Multi-Threading:** Intuitive, minimal interface supporting concurrent, isolated chat threads.

---

## 8. Summary
The goal is to build a trustworthy, transparent, and compliant mutual fund FAQ assistant that **prioritizes accuracy over intelligence**. The system guarantees that users receive verified, source-backed financial information without advisory bias, speculation, or compliance violations.

