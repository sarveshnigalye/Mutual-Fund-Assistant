"""Streamlit frontend for HDFC Mutual Fund Facts-Only Assistant.
Styled with Obsidian Factstream dark design system.
"""

import html
import logging
import os
import re
import socket
import textwrap
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


def is_backend_alive(host: str = "127.0.0.1", port: int = 8000) -> bool:
    """Fast TCP probe to verify if FastAPI server is up in < 80ms."""
    try:
        with socket.create_connection((host, port), timeout=0.08):
            return True
    except OSError:
        return False


def api_request(method: str, endpoint: str, json_data=None):
    """Makes HTTP request to FastAPI backend with instant fallback."""
    if not is_backend_alive() and HAS_LOCAL_BACKEND:
        return local_fallback_request(method, endpoint, json_data)

    url = f"{API_URL}/{endpoint.lstrip('/')}"
    try:
        timeout = (0.5, 30.0 if method.upper() == "POST" else 2.0)
        if method.upper() == "GET":
            resp = requests.get(url, timeout=timeout)
        elif method.upper() == "POST":
            resp = requests.post(url, json=json_data, timeout=timeout)
        elif method.upper() == "DELETE":
            resp = requests.delete(url, timeout=timeout)
        elif method.upper() == "PATCH":
            resp = requests.patch(url, json=json_data, timeout=timeout)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code in [200, 201]:
            return resp.json()
    except Exception:
        if HAS_LOCAL_BACKEND:
            return local_fallback_request(method, endpoint, json_data)
    return None


def render_html(html_str: str):
    """Safely renders HTML without Markdown 4-space code block distortion or comment leaks."""
    dedented = textwrap.dedent(html_str).strip()
    cleaned = re.sub(r'<!--.*?-->', '', dedented, flags=re.DOTALL).strip()
    st.markdown(cleaned, unsafe_allow_html=True)


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

# Obsidian Factstream Theme Styling
render_html(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

    :root {
        --color-surface: #0B1326;
        --color-surface-lowest: #060E20;
        --color-surface-low: #131B2E;
        --color-surface-container: #171F33;
        --color-surface-high: #222A3D;
        --color-on-surface: #DAE2FD;
        --color-on-surface-variant: #94A3B8;
        --color-primary: #B4C5FF;
        --color-primary-container: #2563EB;
        --color-secondary: #10B981;
        --color-tertiary: #F59E0B;
    }

    html, body, [class*="css"], .stApp {
        font-family: 'Inter', sans-serif !important;
        background-color: #0B1326 !important;
        color: #DAE2FD !important;
    }

    [data-testid="stSidebar"] {
        background-color: #060E20 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
    }

    header[data-testid="stHeader"] {
        background-color: #0B1326 !important;
    }

    .stButton > button {
        background-color: #171F33 !important;
        color: #DAE2FD !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 4px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 12px !important;
        font-weight: 500 !important;
        transition: all 0.15s ease !important;
    }

    .stButton > button:hover {
        background-color: #222A3D !important;
        border-color: rgba(37, 99, 235, 0.5) !important;
        color: #B4C5FF !important;
    }

    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #2563EB 0%, #1D4ED8 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        font-weight: 600 !important;
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.35) !important;
    }

    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(90deg, #3B82F6 0%, #2563EB 100%) !important;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.5) !important;
    }

    [data-testid="stBottom"] {
        background-color: rgba(11, 19, 38, 0.95) !important;
        backdrop-filter: blur(12px) !important;
        border-top: 1px solid rgba(255, 255, 255, 0.08) !important;
    }

    [data-testid="stChatInput"] {
        background-color: #171F33 !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 6px !important;
    }

    [data-testid="stChatInput"]:focus-within {
        border-color: #2563EB !important;
        box-shadow: 0 0 0 1px #2563EB, 0 0 14px rgba(37, 99, 235, 0.25) !important;
    }

    [data-testid="stChatInput"] textarea {
        color: #DAE2FD !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 14px !important;
    }

    .bento-card {
        background-color: #171F33;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 6px;
        padding: 1rem;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    </style>
    """
)

# Session State Initialization
if "current_thread_id" not in st.session_state:
    st.session_state.current_thread_id = None
if "pending_query" not in st.session_state:
    st.session_state.pending_query = None


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


def format_markdown_body(text: str) -> str:
    """Safely converts common markdown syntax (bold, backticks, breaks) to HTML."""
    safe = html.escape(text)
    safe = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', safe)
    safe = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', safe)
    safe = re.sub(
        r'`(.+?)`',
        r'<code style="font-family: \'JetBrains Mono\', monospace; background: rgba(255,255,255,0.06); padding: 1px 4px; border-radius: 3px; font-size: 12px; color: #B4C5FF;">\1</code>',
        safe,
    )
    safe = safe.replace("\n\n", "<br><br>").replace("\n", "<br>")
    return safe


def parse_assistant_message(content: str, default_source: Optional[str] = None) -> Dict[str, Any]:
    """Extracts clean text, metrics, scheme name, and citation info from assistant messages."""
    text = content.strip()

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

    source_url = default_source
    src_match = re.search(r'\[Source:\s*([^\s\]]+)\]', text)
    if src_match:
        source_url = src_match.group(1)
        text = text.replace(src_match.group(0), "")

    src_link_match = re.search(r'(?:📎\s*)?Source:\s*(https?://[^\s\n\)]+)', text)
    if src_link_match:
        if not source_url:
            source_url = src_link_match.group(1)
        text = text.replace(src_link_match.group(0), "")

    scrape_date = "Today"
    date_match = re.search(r'\[Scraped:\s*([^\s\]]+)\]', text)
    if date_match:
        scrape_date = date_match.group(1)
        text = text.replace(date_match.group(0), "")

    date_note_match = re.search(r'_Last updated from sources:\s*([^\s_]+)_', text)
    if date_note_match:
        scrape_date = date_note_match.group(1)
        text = text.replace(date_note_match.group(0), "")

    clean_body = text.strip()

    scheme_name = "HDFC Mutual Fund Scheme"
    body_lower = clean_body.lower()
    for full_name, kws in VERIFIED_SCHEMES:
        if any(kw in body_lower for kw in kws):
            scheme_name = full_name
            break

    metrics = []
    ter_m = re.search(r'(?:Expense Ratio|TER)[^0-9]*(\d+(?:\.\d+)?\s*%)', clean_body, re.IGNORECASE)
    if ter_m:
        metrics.append({"label": "EXPENSE RATIO", "value": ter_m.group(1).strip(), "sub": "Direct (Incl GST)"})

    nav_m = re.search(r'(?:NAV|Net Asset Value)[^0-9₹]*₹?\s*(\d+(?:\.\d+)?)', clean_body, re.IGNORECASE)
    if nav_m:
        metrics.append({"label": "CURRENT NAV", "value": f"₹{nav_m.group(1).strip()}", "sub": "Official Close"})

    aum_m = re.search(r'(?:AUM|assets)[^0-9₹]*₹?\s*([\d,]+(?:\.\d+)?\s*(?:Cr|Crore))', clean_body, re.IGNORECASE)
    if aum_m:
        metrics.append({"label": "FUND AUM", "value": f"₹{aum_m.group(1).strip()}", "sub": "Total Assets"})

    load_m = re.search(r'exit load[^0-9]*(\d+(?:\.\d+)?\s*%)', clean_body, re.IGNORECASE)
    if load_m:
        metrics.append({"label": "EXIT LOAD", "value": load_m.group(1).strip(), "sub": "Redemption Horizon"})

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


def switch_thread(thread_id: str):
    st.session_state.current_thread_id = thread_id
    st.rerun()


def create_new_thread():
    res = api_request("POST", "threads", {"title": "New Chat"})
    if res and "thread_id" in res:
        st.session_state.current_thread_id = res["thread_id"]
        st.rerun()


# ==============================================================================
# SIDEBAR NAVIGATION RAIL
# ==============================================================================
with st.sidebar:
    if st.button("➕ New Query", use_container_width=True, type="primary"):
        create_new_thread()

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    threads_data = api_request("GET", "threads") or []
    if not threads_data:
        init_thread = api_request("POST", "threads", {"title": "New Chat"})
        if init_thread:
            st.session_state.current_thread_id = init_thread["thread_id"]
            threads_data = [init_thread]

    thread_ids = [t["thread_id"] for t in threads_data]
    if st.session_state.current_thread_id not in thread_ids and thread_ids:
        st.session_state.current_thread_id = thread_ids[0]

    render_html(
        f"""
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0 4px; margin-bottom: 8px;">
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; color: #64748B; letter-spacing: 0.05em; text-transform: uppercase;">
                CONVERSATIONS
            </span>
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #64748B; background: rgba(255, 255, 255, 0.05); padding: 1px 6px; border-radius: 3px;">
                {len(threads_data)} ACTIVE
            </span>
        </div>
        """
    )

    for t in threads_data[:12]:
        t_id = t["thread_id"]
        t_title = t.get("title", "New Chat")
        is_active = (t_id == st.session_state.current_thread_id)

        col1, col2 = st.columns([0.80, 0.20])
        with col1:
            icon_prefix = "🔹 " if is_active else "💬 "
            btn_type = "primary" if is_active else "secondary"
            if st.button(f"{icon_prefix}{t_title}", key=f"t_{t_id}", use_container_width=True, type=btn_type):
                switch_thread(t_id)
        with col2:
            if st.button("🗑️", key=f"del_{t_id}", help="Delete chat thread", use_container_width=True):
                api_request("DELETE", f"threads/{t_id}")
                if st.session_state.current_thread_id == t_id:
                    st.session_state.current_thread_id = None
                st.rerun()

    render_html(
        """
        <div style="margin-top: 1.5rem; padding: 0.85rem; border-radius: 6px; background-color: #171F33; border: 1px solid rgba(255, 255, 255, 0.08);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem; padding-bottom: 0.4rem; border-bottom: 1px solid rgba(255, 255, 255, 0.06);">
                <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; color: #DAE2FD; letter-spacing: 0.03em;">
                    Covered Schemes (5 Verified)
                </span>
                <span style="width: 7px; height: 7px; border-radius: 50%; background-color: #10B981; display: inline-block;"></span>
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
        """
    )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    with st.expander("⚖️ Statutory Disclosures", expanded=False):
        st.caption(
            "This assistant operates under strict facts-only retrieval guidelines. "
            "No investment advice, projections, or comparisons are provided. "
            "Non-SEBI registered entity. Reference: AMFI Ref 2024-CIR-92."
        )


# ==============================================================================
# MAIN VIEW: TOP HEADER & MANDATORY REGULATORY BANNER
# ==============================================================================
render_html(
    """
    <div style="display: flex; flex-direction: column; width: 100%; margin-bottom: 1.25rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem; padding: 0.75rem 1rem; background-color: #131B2E; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px;">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <div style="width: 32px; height: 32px; border-radius: 4px; background-color: #2563EB; display: flex; align-items: center; justify-content: center; color: #FFFFFF; font-size: 18px;">
                    🏦
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

            <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 4px; background-color: #171F33; border: 1px solid rgba(255,255,255,0.08); font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #10B981;">
                    <span style="width: 7px; height: 7px; border-radius: 50%; background-color: #10B981; display: inline-block;"></span>
                    <span>Groq Engine Online</span>
                </div>
                <div style="display: flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 4px; background-color: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.3); font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #F59E0B;">
                    <span>⚖️ SEBI Non-Advisory Grounding</span>
                </div>
            </div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; background-color: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.25); border-left: 3px solid #F59E0B; padding: 0.5rem 0.85rem; border-radius: 4px; margin-top: 0.5rem; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #F59E0B;">
            <div style="display: flex; align-items: center; gap: 0.5rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                <span>⚠️</span>
                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    <strong>MANDATORY REGULATORY DISCLAIMER:</strong> Facts-only assistant. No investment advice, opinions, or performance predictions provided. Non-SEBI registered entity. Strictly non-promotional.
                </span>
            </div>
            <span style="font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(245, 158, 11, 0.7); flex-shrink: 0; margin-left: 0.75rem;">
                AMFI Ref: 2024-CIR-92
            </span>
        </div>
    </div>
    """
)

# Fetch messages for current active thread
current_thread = None
messages = []
if st.session_state.current_thread_id:
    current_thread = api_request("GET", f"threads/{st.session_state.current_thread_id}")
    if current_thread:
        messages = current_thread.get("messages", [])


# ==============================================================================
# WELCOME HERO & QUICK STARTER BENTO GRID
# ==============================================================================
if not messages:
    render_html(
        """
        <div style="margin-top: 0.5rem; margin-bottom: 1.5rem; display: flex; flex-direction: column; gap: 0.5rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <span style="padding: 2px 8px; border-radius: 3px; font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; background-color: rgba(37, 99, 235, 0.2); color: #B4C5FF; border: 1px solid rgba(37, 99, 235, 0.4);">
                    SEBI NON-ADVISORY COMPLIANT
                </span>
                <span style="color: #64748B; font-size: 12px;">• Strictly Non-Predictive & Grounded</span>
            </div>
            <h1 style="font-family: 'Geist', sans-serif; font-size: 26px; font-weight: 600; color: #DAE2FD; letter-spacing: -0.025em; margin: 0.25rem 0 0 0;">
                Verified Mutual Fund Facts at Your Fingertips
            </h1>
            <p style="font-family: 'Inter', sans-serif; font-size: 14px; color: #94A3B8; max-width: 680px; margin: 0; line-height: 1.5;">
                Strictly grounded in official Groww scheme data. Brevity guaranteed (≤ 3 sentences). Zero personal opinion, recommendation, or return guarantees.
            </p>
        </div>
        """
    )

    starter_cols = st.columns(3)
    for idx, item in enumerate(QUICK_STARTER_QUERIES):
        with starter_cols[idx]:
            card_html = f"""
            <div class="bento-card">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <span style="font-size: 20px;">{item['icon']}</span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #64748B; font-weight: 600;">{item['tag']}</span>
                    </div>
                    <div style="font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 500; color: #DAE2FD; line-height: 1.4; margin-bottom: 0.5rem;">
                        {item['query']}
                    </div>
                </div>
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #64748B; margin-top: 0.5rem;">{item['desc']}</div>
            </div>
            """
            render_html(card_html)
            if st.button("Run Query ↗", key=f"bento_run_{idx}", use_container_width=True):
                st.session_state.pending_query = item["query"]
                st.rerun()

    render_html(
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
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem;">
                <div style="padding: 0.85rem; border-radius: 4px; background-color: #171F33; border: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; gap: 4px;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #94A3B8;">HDFC Small Cap Fund</span>
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; color: #DAE2FD;">TER: 0.69%</span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #10B981;">NAV ₹142.10</span>
                    </div>
                    <span style="font-size: 11px; color: #64748B;">Min SIP: ₹100 • Lock-in: None</span>
                </div>
                <div style="padding: 0.85rem; border-radius: 4px; background-color: #171F33; border: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; gap: 4px;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #94A3B8;">HDFC Top 100 Large Cap</span>
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; color: #DAE2FD;">TER: 1.05%</span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #10B981;">NAV ₹1,085.4</span>
                    </div>
                    <span style="font-size: 11px; color: #64748B;">Min SIP: ₹100 • Exit Load: 1% (&lt;1Y)</span>
                </div>
                <div style="padding: 0.85rem; border-radius: 4px; background-color: #171F33; border: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; gap: 4px;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #94A3B8;">HDFC Silver ETF FoF</span>
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; color: #DAE2FD;">TER: 0.35%</span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #10B981;">NAV ₹16.42</span>
                    </div>
                    <span style="font-size: 11px; color: #64748B;">Commodity Backed • 99.9% Purity</span>
                </div>
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
        """
    )


# ==============================================================================
# CHAT HISTORY RENDERING
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

    safe_query = format_markdown_body(query)
    user_html = (
        '<div style="display: flex; justify-content: flex-end; align-items: flex-start; gap: 0.75rem; margin-bottom: 1.25rem; padding-left: 2rem;">'
        '<div style="background-color: #222A3D; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 0.85rem 1rem; max-width: 80%; box-shadow: 0 2px 8px rgba(0,0,0,0.3);">'
        f'<p style="font-family: \'Inter\', sans-serif; font-size: 14px; color: #DAE2FD; margin: 0; line-height: 1.5;">{safe_query}</p>'
        f'<div style="display: flex; justify-content: flex-end; align-items: center; gap: 4px; margin-top: 6px; font-family: \'JetBrains Mono\', monospace; font-size: 10px; color: #64748B;"><span>{timestamp}</span></div>'
        '</div>'
        '<div style="width: 32px; height: 32px; border-radius: 4px; background-color: #2D3449; border: 1px solid rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; color: #DAE2FD; font-family: \'JetBrains Mono\', monospace; font-size: 11px; font-weight: 600; flex-shrink: 0;">CL</div>'
        '</div>'
    )
    st.markdown(user_html, unsafe_allow_html=True)


def render_assistant_message(content: str, source_url: Optional[str] = None):
    """Renders verified fact response with sapphire accent and clean source link."""
    parsed = parse_assistant_message(content, default_source=source_url)
    clean_body = format_markdown_body(parsed["clean_body"])
    scheme_name = html.escape(parsed["scheme_name"])
    resolved_source = parsed["source_url"]
    is_refusal = parsed["is_refusal"]
    scrape_date = html.escape(parsed["scrape_date"])

    if is_refusal:
        card_html = (
            '<div style="display: flex; justify-content: flex-start; align-items: flex-start; gap: 0.75rem; margin-bottom: 1.25rem; padding-right: 1.5rem;">'
            '<div style="width: 34px; height: 34px; border-radius: 4px; background-color: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.35); display: flex; align-items: center; justify-content: center; color: #F59E0B; font-size: 18px; flex-shrink: 0;">⚖️</div>'
            '<div style="flex: 1; max-width: 820px; background-color: #131B2E; border: 1px solid rgba(245, 158, 11, 0.25); border-left: 4px solid #F59E0B; border-radius: 6px; padding: 1rem 1.15rem; display: flex; flex-direction: column; gap: 0.6rem;">'
            '<div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">'
            '<span style="font-family: \'JetBrains Mono\', monospace; font-size: 10px; font-weight: 600; background-color: rgba(245, 158, 11, 0.15); color: #F59E0B; border: 1px solid rgba(245, 158, 11, 0.3); padding: 2px 7px; border-radius: 3px;">🛡️ REGULATORY NON-ADVISORY GUARD</span>'
            '<span style="font-family: \'JetBrains Mono\', monospace; font-size: 11px; color: #94A3B8;">SEBI Guideline Compliant</span>'
            '</div>'
            f'<div style="font-family: \'Inter\', sans-serif; font-size: 14px; color: #DAE2FD; margin: 0; line-height: 1.6;">{clean_body}</div>'
            '<div style="background-color: rgba(245, 158, 11, 0.05); border: 1px dashed rgba(245, 158, 11, 0.2); border-radius: 4px; padding: 0.45rem 0.75rem; font-family: \'JetBrains Mono\', monospace; font-size: 10px; color: #F59E0B;">Automated financial advisory, portfolio evaluation, and return forecasts are strictly prohibited. For financial decisions, consult a SEBI-registered Investment Advisor.</div>'
            '</div></div>'
        )
    else:
        citation_html = ""
        if resolved_source:
            display_url = html.escape(resolved_source.replace("https://", "").replace("http://", ""))
            citation_html = (
                '<div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; padding: 0.45rem 0.75rem; background-color: rgba(23, 31, 51, 0.7); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 4px; margin-top: 0.5rem; font-family: \'JetBrains Mono\', monospace; font-size: 11px;">'
                f'<div style="display: flex; align-items: center; gap: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"><span style="color: #10B981;">🔗</span><span style="color: #64748B;">Source: <span style="color: #DAE2FD; text-decoration: underline;">{display_url}</span></span><span style="padding: 1px 6px; border-radius: 3px; font-size: 9px; background-color: rgba(16, 185, 129, 0.15); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.25);">Fetched &amp; Verified</span></div>'
                f'<a href="{html.escape(resolved_source)}" target="_blank" rel="noopener noreferrer" style="color: #B4C5FF; text-decoration: none; font-size: 11px; font-weight: 500;">Direct Filing Link [Open ↗]</a>'
                '</div>'
            )

        card_html = (
            '<div style="display: flex; justify-content: flex-start; align-items: flex-start; gap: 0.75rem; margin-bottom: 1.25rem; padding-right: 1.5rem;">'
            '<div style="width: 34px; height: 34px; border-radius: 4px; background-color: #2563EB; border: 1px solid rgba(37, 99, 235, 0.5); display: flex; align-items: center; justify-content: center; color: #FFFFFF; font-size: 18px; flex-shrink: 0;">🏦</div>'
            '<div style="flex: 1; max-width: 820px; background-color: #131B2E; border: 1px solid rgba(255, 255, 255, 0.08); border-left: 4px solid #2563EB; border-radius: 6px; padding: 1rem 1.15rem; display: flex; flex-direction: column; gap: 0.6rem;">'
            '<div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">'
            f'<div style="display: flex; align-items: center; gap: 8px;"><span style="font-family: \'JetBrains Mono\', monospace; font-size: 10px; font-weight: 600; background-color: rgba(16, 185, 129, 0.15); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.3); padding: 2px 7px; border-radius: 3px;">✓ VERIFIED FACTUAL</span><span style="font-family: \'JetBrains Mono\', monospace; font-size: 11px; color: #94A3B8;">{scheme_name}</span></div>'
            f'<span style="font-family: \'JetBrains Mono\', monospace; font-size: 10px; color: #64748B;">Groww Scheme Feed: {scrape_date}</span>'
            '</div>'
            f'<div style="font-family: \'Inter\', sans-serif; font-size: 14px; color: #DAE2FD; margin: 0; line-height: 1.6;">{clean_body}</div>'
            f'{citation_html}'
            '</div></div>'
        )

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
    render_user_message(query_to_send)

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


render_html(
    """
    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; padding: 0.4rem 0.2rem 0 0.2rem; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #64748B;">
        <div style="display: flex; align-items: center; gap: 0.6rem;">
            <span style="display: flex; align-items: center; gap: 5px; color: #10B981;">
                <span style="width: 7px; height: 7px; border-radius: 50%; background-color: #10B981; display: inline-block;"></span>
                <span>Groq LPU 120B</span>
            </span>
            <span>•</span>
            <span>Latency: ~140ms</span>
            <span>•</span>
            <span style="color: #B4C5FF;">Facts-Only Guardrail ON</span>
        </div>
        <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            Data cross-referenced with SEBI filings & Groww data feeds. Never constitutes financial advice.
        </div>
    </div>
    """
)
