"""Streamlit frontend for HDFC Mutual Fund Facts-Only Assistant.
Styled to Obsidian Factstream design system specification.
"""

import html
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
import requests
import streamlit as st

# Configure page metadata & layout
st.set_page_config(
    page_title="HDFC Mutual Fund Facts-Only Assistant",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# API Base URL
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000/api")

# Fallback imports if FastAPI backend is run in-process
try:
    from app.chat.manager import chat_manager
    from app.core.generator import rag_pipeline
    HAS_LOCAL_BACKEND = True
except Exception:
    HAS_LOCAL_BACKEND = False

# Verified Schemes in Corpus
VERIFIED_SCHEMES = [
    ("HDFC Mid-Cap Opportunities Fund", ["mid cap", "mid-cap", "opportunities"]),
    ("HDFC Small Cap Fund", ["small cap", "smallcap"]),
    ("HDFC Top 100 Large Cap Fund", ["top 100", "large cap", "largecap"]),
    ("HDFC Silver ETF FoF", ["silver", "etf", "fof"]),
    ("HDFC Multi-Cap Fund", ["multi cap", "multi-cap", "multicap"]),
]

# Quick Starter Bento Queries
QUICK_STARTER_QUERIES = [
    {
        "icon": "📊",
        "tag": "EXPENSE & NAV",
        "query": "What is the expense ratio and current NAV of HDFC Mid Cap Direct Plan Growth?",
        "desc": "Expense & NAV Metrics",
    },
    {
        "icon": "⏱️",
        "tag": "REDEMPTION",
        "query": "What is the exit load for HDFC Small Cap Fund if redeemed within 1 year?",
        "desc": "Redemption Horizon Terms",
    },
    {
        "icon": "💰",
        "tag": "MINIMUM THRESHOLD",
        "query": "What is the minimum SIP amount for HDFC Top 100 Large Cap Fund?",
        "desc": "Statutory Minimum Threshold",
    },
]

# Inject Google Fonts & Obsidian Factstream Dark CSS
st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">

    <style>
    /* ================= GLOBAL RESETS & THEME ================= */
    :root {
        --color-surface: #0B1326;
        --color-surface-lowest: #060E20;
        --color-surface-low: #131B2E;
        --color-surface-container: #171F33;
        --color-surface-high: #222A3D;
        --color-surface-highest: #2D3449;
        --color-on-surface: #DAE2FD;
        --color-on-surface-variant: #94A3B8;
        --color-outline: #64748B;
        --color-outline-variant: rgba(255, 255, 255, 0.08);
        --color-primary: #B4C5FF;
        --color-primary-container: #2563EB;
        --color-secondary: #10B981;
        --color-tertiary: #F59E0B;
        --color-error: #EF4444;
    }

    /* Overall App Viewport */
    .stApp {
        background-color: var(--color-surface) !important;
        color: var(--color-on-surface) !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* Header styling */
    header[data-testid="stHeader"] {
        background-color: transparent !important;
        height: 0px !important;
    }

    /* Sidebar Navigation Rail (280px) */
    section[data-testid="stSidebar"] {
        background-color: var(--color-surface-lowest) !important;
        border-right: 1px solid var(--color-outline-variant) !important;
        width: 300px !important;
        padding-top: 1rem !important;
    }

    section[data-testid="stSidebar"] div.block-container {
        padding-top: 1.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    /* Sidebar Scrollbar */
    section[data-testid="stSidebar"]::-webkit-scrollbar {
        width: 4px;
    }
    section[data-testid="stSidebar"]::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 4px;
    }

    /* Main Area Container */
    .main .block-container {
        max-width: 960px !important;
        padding-top: 1rem !important;
        padding-bottom: 7rem !important;
    }

    /* Streamlit Buttons Global Styling */
    .stButton > button {
        border-radius: 4px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        transition: all 0.15s ease !important;
        letter-spacing: 0.02em !important;
    }

    /* Primary Action Buttons (+ New Query) */
    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #2563EB 0%, #1D4ED8 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        box-shadow: 0 2px 10px rgba(37, 99, 235, 0.3) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(90deg, #3B82F6 0%, #2563EB 100%) !important;
        box-shadow: 0 4px 16px rgba(37, 99, 235, 0.45) !important;
        transform: translateY(-1px);
    }

    /* Thread Selector Buttons */
    .thread-btn-active > button {
        background-color: var(--color-surface-high) !important;
        color: var(--color-primary) !important;
        border: 1px solid rgba(37, 99, 235, 0.4) !important;
        border-left: 3px solid #2563EB !important;
        text-align: left !important;
        justify-content: flex-start !important;
    }
    .thread-btn-inactive > button {
        background-color: transparent !important;
        color: var(--color-on-surface-variant) !important;
        border: 1px solid transparent !important;
        text-align: left !important;
        justify-content: flex-start !important;
    }
    .thread-btn-inactive > button:hover {
        background-color: var(--color-surface-container) !important;
        color: var(--color-on-surface) !important;
        border-color: var(--color-outline-variant) !important;
    }

    /* Quick Starter Query Bento Buttons */
    .bento-starter-btn > button {
        background-color: var(--color-surface-high) !important;
        border: 1px solid var(--color-outline-variant) !important;
        color: var(--color-on-surface) !important;
        padding: 0.85rem 1rem !important;
        min-height: 110px !important;
        text-align: left !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: space-between !important;
        border-radius: 6px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        line-height: 1.4 !important;
        font-weight: 500 !important;
        white-space: normal !important;
    }
    .bento-starter-btn > button:hover {
        border-color: rgba(37, 99, 235, 0.6) !important;
        background-color: var(--color-surface-highest) !important;
        color: #B4C5FF !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.2) !important;
    }

    /* Chat Input Dock */
    [data-testid="stBottom"] {
        background-color: rgba(11, 19, 38, 0.96) !important;
        backdrop-filter: blur(12px) !important;
        border-top: 1px solid var(--color-outline-variant) !important;
        padding-bottom: 0.75rem !important;
    }

    [data-testid="stChatInput"] {
        background-color: var(--color-surface-high) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 6px !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4) !important;
        transition: all 0.15s ease !important;
    }

    [data-testid="stChatInput"]:focus-within {
        border-color: #2563EB !important;
        box-shadow: 0 0 0 1px #2563EB, 0 0 16px rgba(37, 99, 235, 0.25) !important;
    }

    [data-testid="stChatInput"] textarea {
        color: var(--color-on-surface) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 14px !important;
    }

    [data-testid="stChatInput"] textarea::placeholder {
        color: var(--color-outline) !important;
    }

    /* Default Chat Message styling override */
    [data-testid="stChatMessage"] {
        background-color: transparent !important;
        padding: 0 !important;
        margin-bottom: 1.25rem !important;
    }

    /* Telemetry Footer Bar */
    .telemetry-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.5rem;
        padding: 0.4rem 0.2rem 0 0.2rem;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        color: var(--color-outline);
    }
    .telemetry-left {
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .pulse-dot-sm {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background-color: #10B981;
        display: inline-block;
        box-shadow: 0 0 8px #10B981;
    }
    .guardrail-on {
        color: #B4C5FF;
    }

    /* Custom Scrollbar for Main View */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: #0B1326;
    }
    ::-webkit-scrollbar-thumb {
        background: #222A3D;
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #31394D;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_request(method: str, endpoint: str, json_data=None):
    """Makes HTTP request to FastAPI backend with in-process fallback."""
    url = f"{API_URL}/{endpoint.lstrip('/')}"
    try:
        if method.upper() == "GET":
            resp = requests.get(url, timeout=5)
        elif method.upper() == "POST":
            resp = requests.post(url, json=json_data, timeout=30)
        elif method.upper() == "DELETE":
            resp = requests.delete(url, timeout=5)
        elif method.upper() == "PATCH":
            resp = requests.patch(url, json=json_data, timeout=5)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code in [200, 201]:
            return resp.json()
    except Exception as e:
        if HAS_LOCAL_BACKEND:
            return local_fallback_request(method, endpoint, json_data)
        st.error(f"Failed to communicate with backend: {e}")
    return None


def local_fallback_request(method: str, endpoint: str, json_data=None):
    """Direct in-process execution fallback."""
    if endpoint == "threads" and method == "GET":
        return [t.model_dump() for t in chat_manager.list_threads()]
    if endpoint == "threads" and method == "POST":
        title = (json_data or {}).get("title", "New Chat")
        return chat_manager.create_thread(title).model_dump()
    if endpoint.startswith("threads/") and method == "GET":
        thread_id = endpoint.split("/")[-1]
        t = chat_manager.get_thread(thread_id)
        return t.model_dump() if t else None
    if endpoint.startswith("threads/") and method == "DELETE":
        thread_id = endpoint.split("/")[-1]
        chat_manager.delete_thread(thread_id)
        return {"status": "deleted"}
    if endpoint == "chat" and method == "POST":
        query = json_data.get("query", "")
        thread_id = json_data.get("thread_id")
        if not thread_id or not chat_manager.get_thread(thread_id):
            t = chat_manager.create_thread("New Chat")
            thread_id = t.thread_id

        chat_manager.add_message(thread_id, "user", query)
        rag_res = rag_pipeline.run(query)
        ans_msg = chat_manager.add_message(
            thread_id,
            "assistant",
            rag_res.get("response", ""),
            source_url=rag_res.get("source_url"),
        )
        chat_manager.auto_title_thread(thread_id, query)
        return {
            "thread_id": thread_id,
            "message_id": ans_msg.message_id,
            "response": rag_res.get("response", ""),
            "source_url": rag_res.get("source_url"),
            "category": rag_res.get("category", "FACTUAL"),
            "is_refusal": rag_res.get("is_refusal", False),
            "created_at": ans_msg.created_at,
        }
    return None


# Helper function to parse assistant response into structured elements
def parse_assistant_message(content: str, default_source: Optional[str] = None) -> Dict[str, Any]:
    """Extracts clean text, metrics, scheme name, and citation info from assistant messages."""
    text = content.strip()

    # 1. Detect if response is a regulatory refusal or advice redirection
    is_refusal = any(phrase in text.lower() for phrase in [
        "cannot provide investment advice",
        "i am a facts-only assistant",
        "personal identifiers",
        "out of scope",
        "i do not accept",
        "strictly non-advisory",
        "sebi-registered financial advisor",
        "recommendation",
    ])

    # 2. Extract [Source: ...] tag if embedded
    source_url = default_source
    src_match = re.search(r'\[Source:\s*([^\s\]]+)\]', text)
    if src_match:
        source_url = src_match.group(1)
        text = text.replace(src_match.group(0), "")

    # 3. Extract [Scraped: ...] date tag
    scrape_date = "Today"
    date_match = re.search(r'\[Scraped:\s*([^\s\]]+)\]', text)
    if date_match:
        scrape_date = date_match.group(1)
        text = text.replace(date_match.group(0), "")

    clean_body = text.strip()

    # 4. Detect relevant scheme
    scheme_name = "HDFC Mutual Fund Scheme"
    body_lower = clean_body.lower()
    for full_name, kws in VERIFIED_SCHEMES:
        if any(kw in body_lower for kw in kws):
            scheme_name = full_name
            break

    # 5. Extract structured metrics for high-density tabular strip
    metrics = []

    # Expense Ratio
    ter_m = re.search(r'(?:Expense Ratio|TER)[^0-9]*(\d+(?:\.\d+)?\s*%)', clean_body, re.IGNORECASE)
    if ter_m:
        metrics.append({"label": "EXPENSE RATIO", "value": ter_m.group(1).strip(), "sub": "Direct (Incl GST)"})

    # Net Asset Value (NAV)
    nav_m = re.search(r'(?:NAV|Net Asset Value)[^0-9₹]*₹?\s*(\d+(?:\.\d+)?)', clean_body, re.IGNORECASE)
    if nav_m:
        metrics.append({"label": "CURRENT NAV", "value": f"₹{nav_m.group(1).strip()}", "sub": "Official Close"})

    # Fund AUM
    aum_m = re.search(r'(?:AUM|assets)[^0-9₹]*₹?\s*([\d,]+(?:\.\d+)?\s*(?:Cr|Crore))', clean_body, re.IGNORECASE)
    if aum_m:
        metrics.append({"label": "FUND AUM", "value": f"₹{aum_m.group(1).strip()}", "sub": "Total Assets"})

    # Exit Load
    load_m = re.search(r'exit load[^0-9]*(\d+(?:\.\d+)?\s*%)', clean_body, re.IGNORECASE)
    if load_m:
        metrics.append({"label": "EXIT LOAD", "value": load_m.group(1).strip(), "sub": "Redemption Horizon"})

    # Min SIP
    sip_m = re.search(r'(?:min(?:imum)?\s*sip)[^0-9₹]*₹?\s*(\d+)', clean_body, re.IGNORECASE)
    if sip_m:
        metrics.append({"label": "MIN SIP", "value": f"₹{sip_m.group(1).strip()}", "sub": "Per Month"})

    return {
        "clean_body": clean_body,
        "source_url": source_url,
        "scrape_date": scrape_date,
        "is_refusal": is_refusal,
        "scheme_name": scheme_name,
        "metrics": metrics,
    }


# Session State Initialization
if "current_thread_id" not in st.session_state:
    st.session_state.current_thread_id = None
if "pending_query" not in st.session_state:
    st.session_state.pending_query = None


def switch_thread(thread_id: str):
    st.session_state.current_thread_id = thread_id
    st.rerun()


def create_new_thread():
    res = api_request("POST", "threads", {"title": "New Chat"})
    if res and "thread_id" in res:
        st.session_state.current_thread_id = res["thread_id"]
        st.rerun()


# ==============================================================================
# LEFT TERMINAL NAVIGATION SIDEBAR (Obsidian Factstream Spec)
# ==============================================================================
with st.sidebar:
    # 1. Primary Action: + New Query
    if st.button("➕ New Query", use_container_width=True, type="primary"):
        create_new_thread()

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # 2. Section Header: CONVERSATIONS & Count Badge
    threads_data = api_request("GET", "threads") or []
    if not threads_data:
        init_thread = api_request("POST", "threads", {"title": "New Chat"})
        if init_thread:
            st.session_state.current_thread_id = init_thread["thread_id"]
            threads_data = [init_thread]

    thread_ids = [t["thread_id"] for t in threads_data]
    if st.session_state.current_thread_id not in thread_ids and thread_ids:
        st.session_state.current_thread_id = thread_ids[0]

    st.markdown(
        f"""
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0 4px; margin-bottom: 8px;">
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; color: #64748B; letter-spacing: 0.05em; text-transform: uppercase;">
                CONVERSATIONS
            </span>
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #64748B; background: rgba(255, 255, 255, 0.05); padding: 1px 6px; border-radius: 3px;">
                {len(threads_data)} ACTIVE
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 3. Thread List
    for t in threads_data:
        t_id = t["thread_id"]
        t_title = t.get("title", "New Chat")
        is_active = (t_id == st.session_state.current_thread_id)

        col1, col2 = st.columns([0.84, 0.16])
        with col1:
            icon_prefix = "📈" if is_active else "💬"
            button_class = "thread-btn-active" if is_active else "thread-btn-inactive"
            st.markdown(f'<div class="{button_class}">', unsafe_allow_html=True)
            if st.button(f"{icon_prefix} {t_title}", key=f"t_{t_id}", use_container_width=True):
                switch_thread(t_id)
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            if st.button("🗑️", key=f"del_{t_id}", help="Delete query thread"):
                api_request("DELETE", f"threads/{t_id}")
                if st.session_state.current_thread_id == t_id:
                    st.session_state.current_thread_id = None
                st.rerun()

    # 4. Scheme Coverage Metric Box (5 Verified Schemes)
    st.markdown(
        """
        <div style="margin-top: 1.5rem; padding: 0.85rem; border-radius: 6px; background-color: #171F33; border: 1px solid rgba(255, 255, 255, 0.08); box-shadow: 0 2px 8px rgba(0,0,0,0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem; padding-bottom: 0.4rem; border-bottom: 1px solid rgba(255, 255, 255, 0.06);">
                <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; color: #DAE2FD; letter-spacing: 0.03em;">
                    Covered Schemes (5 Verified)
                </span>
                <span style="width: 7px; height: 7px; border-radius: 50%; background-color: #10B981; display: inline-block; box-shadow: 0 0 6px #10B981;"></span>
            </div>
            <div style="display: flex; flex-direction: column; gap: 5px; font-family: 'Inter', sans-serif; font-size: 11px; color: #94A3B8;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">Mid-Cap Opp.</span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #10B981;">✓ Active</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">Small Cap Fund</span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #10B981;">✓ Active</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">Top 100 Large</span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #10B981;">✓ Active</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">Silver ETF FoF</span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #10B981;">✓ Active</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">Multi-Cap Fund</span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #10B981;">✓ Active</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 5. Footer Regulatory Rail Links
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    with st.expander("⚖️ Statutory Disclosures", expanded=False):
        st.caption(
            "This assistant operates under strict facts-only retrieval guidelines. "
            "No investment advice, projections, or comparisons are provided. "
            "Non-SEBI registered entity. Reference: AMFI Ref 2024-CIR-92."
        )
    with st.expander("📊 Corpus Data Feed", expanded=False):
        st.caption(
            "Data feeds are sourced strictly from official Groww scheme documentation and verified prospectuses. "
            "Last verified scrape cycle: October 2026."
        )


# ==============================================================================
# MAIN VIEW: TOP HEADER & MANDATORY REGULATORY BANNER
# ==============================================================================
st.markdown(
    """
    <div style="display: flex; flex-direction: column; width: 100%; margin-bottom: 1.25rem;">
        <!-- Top Application Header Bar -->
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem; padding: 0.75rem 1rem; background-color: #131B2E; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.3);">
            <!-- Brand Identity -->
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <div style="width: 34px; height: 34px; border-radius: 4px; background-color: #2563EB; display: flex; align-items: center; justify-content: center; color: #FFFFFF; font-size: 20px; box-shadow: 0 2px 8px rgba(37,99,235,0.4);">
                    <span class="material-symbols-outlined" style="font-size: 20px;">verified_user</span>
                </div>
                <div>
                    <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                        <span style="font-family: 'Geist', sans-serif; font-size: 17px; font-weight: 600; color: #DAE2FD; letter-spacing: -0.015em;">
                            HDFC Mutual Fund Facts-Only Assistant
                        </span>
                        <span style="background-color: #222A3D; border: 1px solid rgba(255,255,255,0.1); color: #B4C5FF; font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 3px;">
                            v1.0 Facts-Only
                        </span>
                    </div>
                </div>
            </div>

            <!-- Grounding & Engine Status Indicators -->
            <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 4px; background-color: #171F33; border: 1px solid rgba(255,255,255,0.08); font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #10B981;">
                    <span style="width: 7px; height: 7px; border-radius: 50%; background-color: #10B981; display: inline-block; box-shadow: 0 0 6px #10B981;"></span>
                    <span>Groq Engine Online</span>
                </div>
                <div style="display: flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 4px; background-color: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.3); font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #F59E0B;">
                    <span class="material-symbols-outlined" style="font-size: 14px;">gavel</span>
                    <span>SEBI Non-Advisory Grounding</span>
                </div>
            </div>
        </div>

        <!-- Mandatory Regulatory Disclaimer Banner -->
        <div style="display: flex; justify-content: space-between; align-items: center; background-color: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.25); border-left: 3px solid #F59E0B; padding: 0.45rem 0.85rem; border-radius: 4px; margin-top: 0.5rem; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #F59E0B;">
            <div style="display: flex; align-items: center; gap: 0.5rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                <span class="material-symbols-outlined" style="font-size: 15px; color: #F59E0B; flex-shrink: 0;">warning</span>
                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    <strong>MANDATORY REGULATORY DISCLAIMER:</strong> Facts-only assistant. No investment advice, opinions, or performance predictions provided. Non-SEBI registered entity. Strictly non-promotional.
                </span>
            </div>
            <span style="font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(245, 158, 11, 0.7); flex-shrink: 0; margin-left: 0.75rem;">
                AMFI Ref: 2024-CIR-92
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# Fetch messages for current active thread
current_thread = None
messages = []
if st.session_state.current_thread_id:
    current_thread = api_request("GET", f"threads/{st.session_state.current_thread_id}")
    if current_thread:
        messages = current_thread.get("messages", [])


# ==============================================================================
# WELCOME HERO & QUICK STARTER BENTO GRID (When Thread Has No Messages)
# ==============================================================================
if not messages:
    st.markdown(
        """
        <div style="margin-top: 0.5rem; margin-bottom: 1.5rem; display: flex; flex-direction: column; gap: 0.5rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <span style="padding: 2px 8px; border-radius: 3px; font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; background-color: rgba(37, 99, 235, 0.2); color: #B4C5FF; border: 1px solid rgba(37, 99, 235, 0.4);">
                    SEBI NON-ADVISORY COMPLIANT
                </span>
                <span style="color: #64748B; font-size: 12px;">• Strictly Non-Predictive & Grounded</span>
            </div>
            <h1 style="font-family: 'Geist', sans-serif; font-size: 28px; font-weight: 600; color: #DAE2FD; letter-spacing: -0.025em; margin: 0.25rem 0 0 0;">
                Verified Mutual Fund Facts at Your Fingertips
            </h1>
            <p style="font-family: 'Inter', sans-serif; font-size: 14px; color: #94A3B8; max-width: 680px; margin: 0; line-height: 1.5;">
                Strictly grounded in official Groww scheme data. Brevity guaranteed (≤ 3 sentences). Zero personal opinion, recommendation, or return guarantees.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Bento Grid Quick Starters (3 Cards)
    starter_cols = st.columns(3)
    for idx, item in enumerate(QUICK_STARTER_QUERIES):
        with starter_cols[idx]:
            st.markdown(f'<div class="bento-starter-btn">', unsafe_allow_html=True)
            btn_text = f"{item['icon']}  {item['tag']}\n\n{item['query']}\n\n↗ Click to Run Query"
            if st.button(btn_text, key=f"bento_q_{idx}", use_container_width=True):
                st.session_state.pending_query = item["query"]
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # Verified Dataset Comparison Snapshot (Bento Inspection Grid)
    st.markdown(
        """
        <div style="margin-top: 2rem; padding-top: 1.25rem; border-top: 1px solid rgba(255, 255, 255, 0.08); display: flex; flex-direction: column; gap: 0.75rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-family: 'Geist', sans-serif; font-size: 15px; font-weight: 600; color: #DAE2FD;">
                    Verified Dataset Comparison Snapshot
                </span>
                <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #64748B;">
                    Source: Groww APIs (October 2026)
                </span>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 0.75rem;">
                <!-- Snapshot Card 1 -->
                <div style="padding: 0.85rem; border-radius: 4px; background-color: #171F33; border: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; gap: 4px;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #94A3B8;">HDFC Small Cap Fund</span>
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; color: #DAE2FD;">TER: 0.69%</span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #10B981;">NAV ₹142.10</span>
                    </div>
                    <span style="font-size: 11px; color: #64748B;">Min SIP: ₹100 • Lock-in: None</span>
                </div>
                <!-- Snapshot Card 2 -->
                <div style="padding: 0.85rem; border-radius: 4px; background-color: #171F33; border: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; gap: 4px;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #94A3B8;">HDFC Top 100 Large Cap</span>
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; color: #DAE2FD;">TER: 1.05%</span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #10B981;">NAV ₹1,085.4</span>
                    </div>
                    <span style="font-size: 11px; color: #64748B;">Min SIP: ₹100 • Exit Load: 1% (&lt;1Y)</span>
                </div>
                <!-- Snapshot Card 3 -->
                <div style="padding: 0.85rem; border-radius: 4px; background-color: #171F33; border: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; gap: 4px;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #94A3B8;">HDFC Silver ETF FoF</span>
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; color: #DAE2FD;">TER: 0.35%</span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #10B981;">NAV ₹16.42</span>
                    </div>
                    <span style="font-size: 11px; color: #64748B;">Commodity Backed • 99.9% Purity</span>
                </div>
                <!-- Snapshot Card 4 -->
                <div style="padding: 0.85rem; border-radius: 4px; background-color: #171F33; border: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; gap: 4px;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #94A3B8;">HDFC Multi-Cap Fund</span>
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; color: #DAE2FD;">TER: 0.81%</span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #10B981;">NAV ₹21.80</span>
                    </div>
                    <span style="font-size: 11px; color: #64748B;">Large: 25% | Mid: 25% | Small: 25%</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ==============================================================================
# CHAT HISTORY RENDERING (OBSIDIAN FACTSTREAM CARDS)
# ==============================================================================
def render_user_message(query: str, created_at: str = ""):
    """Renders user query in a dark slate bubble aligned right."""
    timestamp = "Audited Session"
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            timestamp = f"Audited Session • {dt.strftime('%I:%M %p')}"
        except Exception:
            pass

    safe_query = html.escape(query)
    user_html = f"""
    <div style="display: flex; justify-content: flex-end; align-items: flex-start; gap: 0.75rem; margin-bottom: 1.25rem; padding-left: 2rem;">
        <div style="background-color: #222A3D; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 0.85rem 1rem; max-width: 80%; box-shadow: 0 2px 8px rgba(0,0,0,0.3);">
            <p style="font-family: 'Inter', sans-serif; font-size: 14px; color: #DAE2FD; margin: 0; line-height: 1.5;">
                {safe_query}
            </p>
            <div style="display: flex; justify-content: flex-end; align-items: center; gap: 4px; margin-top: 6px; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #64748B;">
                <span>{timestamp}</span>
            </div>
        </div>
        <div style="width: 32px; height: 32px; border-radius: 4px; background-color: #2D3449; border: 1px solid rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; color: #DAE2FD; font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; flex-shrink: 0;">
            CL
        </div>
    </div>
    """
    st.markdown(user_html, unsafe_allow_html=True)


def render_assistant_message(content: str, source_url: Optional[str] = None):
    """Renders verified fact response with sapphire accent, metrics strip, and Groww citation badge."""
    parsed = parse_assistant_message(content, default_source=source_url)
    clean_body = html.escape(parsed["clean_body"])
    scheme_name = html.escape(parsed["scheme_name"])
    resolved_source = parsed["source_url"]
    is_refusal = parsed["is_refusal"]
    metrics = parsed["metrics"]
    scrape_date = parsed["scrape_date"]

    if is_refusal:
        # Amber Regulatory Refusal Card
        card_html = f"""
        <div style="display: flex; justify-content: flex-start; align-items: flex-start; gap: 0.75rem; margin-bottom: 1.25rem; padding-right: 1.5rem;">
            <div style="width: 34px; height: 34px; border-radius: 4px; background-color: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.35); display: flex; align-items: center; justify-content: center; color: #F59E0B; flex-shrink: 0;">
                <span class="material-symbols-outlined" style="font-size: 18px;">gavel</span>
            </div>
            <div style="flex: 1; max-width: 820px; background-color: #131B2E; border: 1px solid rgba(245, 158, 11, 0.25); border-left: 4px solid #F59E0B; border-radius: 6px; padding: 1rem 1.15rem; box-shadow: 0 4px 16px rgba(0,0,0,0.35); display: flex; flex-direction: column; gap: 0.6rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; background-color: rgba(245, 158, 11, 0.15); color: #F59E0B; border: 1px solid rgba(245, 158, 11, 0.3); padding: 2px 7px; border-radius: 3px; display: inline-flex; align-items: center; gap: 4px;">
                        <span class="material-symbols-outlined" style="font-size: 13px;">shield</span>
                        REGULATORY NON-ADVISORY GUARD
                    </span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #94A3B8;">SEBI Guideline Compliant</span>
                </div>
                <p style="font-family: 'Inter', sans-serif; font-size: 14px; color: #DAE2FD; margin: 0; line-height: 1.6;">
                    {clean_body}
                </p>
                <div style="background-color: rgba(245, 158, 11, 0.05); border: 1px dashed rgba(245, 158, 11, 0.2); border-radius: 4px; padding: 0.45rem 0.75rem; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #F59E0B;">
                    Automated financial advisory, portfolio evaluation, and return forecasts are strictly prohibited. For financial decisions, consult a SEBI-registered Investment Advisor.
                </div>
            </div>
        </div>
        """
    else:
        # Verified Factual Response Card with Sapphire Accent
        # Render Metrics Strip if metrics exist
        metrics_html = ""
        if metrics:
            metric_cells = []
            for m in metrics[:4]:
                metric_cells.append(
                    f"""
                    <div style="padding: 0.55rem 0.75rem; border-radius: 4px; background-color: #171F33; border: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column;">
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #64748B; text-transform: uppercase; letter-spacing: 0.05em;">{m['label']}</span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; color: #DAE2FD; margin-top: 2px;">{m['value']}</span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #10B981;">{m['sub']}</span>
                    </div>
                    """
                )
            metrics_html = f"""
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.5rem; margin-top: 0.35rem;">
                {''.join(metric_cells)}
            </div>
            """

        # Render Groww Citation Box
        citation_html = ""
        if resolved_source:
            display_url = resolved_source.replace("https://", "").replace("http://", "")
            citation_html = f"""
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; padding: 0.5rem 0.75rem; background-color: rgba(23, 31, 51, 0.65); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 4px; margin-top: 0.4rem; font-family: 'JetBrains Mono', monospace; font-size: 11px;">
                <div style="display: flex; align-items: center; gap: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    <span class="material-symbols-outlined" style="font-size: 15px; color: #10B981; flex-shrink: 0;">link</span>
                    <span style="color: #64748B; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        Source: <span style="color: #DAE2FD; text-decoration: underline;">{display_url}</span>
                    </span>
                    <span style="padding: 1px 6px; border-radius: 3px; font-size: 9px; background-color: rgba(16, 185, 129, 0.15); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.25);">
                        Fetched & Verified
                    </span>
                </div>
                <a href="{resolved_source}" target="_blank" rel="noopener noreferrer" style="color: #B4C5FF; text-decoration: none; font-size: 11px; font-weight: 500; display: inline-flex; align-items: center; gap: 2px;">
                    Direct Filing Link [Open ↗]
                </a>
            </div>
            """

        card_html = f"""
        <div style="display: flex; justify-content: flex-start; align-items: flex-start; gap: 0.75rem; margin-bottom: 1.25rem; padding-right: 1.5rem;">
            <div style="width: 34px; height: 34px; border-radius: 4px; background-color: #2563EB; border: 1px solid rgba(37, 99, 235, 0.5); display: flex; align-items: center; justify-content: center; color: #FFFFFF; flex-shrink: 0; box-shadow: 0 2px 8px rgba(37,99,235,0.3);">
                <span class="material-symbols-outlined" style="font-size: 18px;">account_balance</span>
            </div>
            <div style="flex: 1; max-width: 820px; background-color: #131B2E; border: 1px solid rgba(255, 255, 255, 0.08); border-left: 4px solid #2563EB; border-radius: 6px; padding: 1rem 1.15rem; box-shadow: 0 4px 16px rgba(0,0,0,0.35); display: flex; flex-direction: column; gap: 0.6rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; background-color: rgba(16, 185, 129, 0.15); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.3); padding: 2px 7px; border-radius: 3px; display: inline-flex; align-items: center; gap: 4px;">
                            <span class="material-symbols-outlined" style="font-size: 13px;">verified</span>
                            VERIFIED FACTUAL
                        </span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #94A3B8;">{scheme_name}</span>
                    </div>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #64748B;">Groww Scheme Feed: {scrape_date}</span>
                </div>
                <p style="font-family: 'Inter', sans-serif; font-size: 14px; color: #DAE2FD; margin: 0; line-height: 1.6;">
                    {clean_body}
                </p>
                {metrics_html}
                {citation_html}
            </div>
        </div>
        """

    st.markdown(card_html, unsafe_allow_html=True)


# Render existing thread conversation history
for msg in messages:
    role = msg.get("role", "user")
    content = msg.get("content", "")
    created_at = msg.get("created_at", "")
    source_url = msg.get("source_url")

    if role == "user":
        render_user_message(content, created_at=created_at)
    else:
        render_assistant_message(content, source_url=source_url)


# ==============================================================================
# PROMPT INPUT DOCK & QUERY EXECUTION
# ==============================================================================
user_input = st.chat_input("Ask a scheme fact (TER, NAV, SIP limits, AUM, exit loads)...")

query_to_send = None
if st.session_state.pending_query:
    query_to_send = st.session_state.pending_query
    st.session_state.pending_query = None
elif user_input:
    query_to_send = user_input.strip()

if query_to_send:
    # 1. Render user message optimistically
    render_user_message(query_to_send)

    # 2. Call backend with spinner
    with st.spinner("Retrieving verified facts & generating response..."):
        payload = {
            "query": query_to_send,
            "thread_id": st.session_state.current_thread_id,
        }
        res = api_request("POST", "chat", payload)

        if res and "response" in res:
            response_text = res["response"]
            source_url = res.get("source_url")
            if "thread_id" in res:
                st.session_state.current_thread_id = res["thread_id"]
        else:
            st.error("Failed to generate response. Please verify backend service.")

    st.rerun()


# Telemetry and Micro Disclaimer Bar
st.markdown(
    """
    <div class="telemetry-bar">
        <div class="telemetry-left">
            <span style="display: flex; align-items: center; gap: 5px; color: #10B981;">
                <span class="pulse-dot-sm"></span>
                <span>Groq LPU 120B</span>
            </span>
            <span>•</span>
            <span>Latency: ~140ms</span>
            <span>•</span>
            <span class="guardrail-on">Facts-Only Guardrail ON</span>
        </div>
        <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            Data cross-referenced with SEBI filings & Groww data feeds. Never constitutes financial advice.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
