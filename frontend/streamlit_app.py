"""Streamlit frontend for the HDFC Mutual Fund FAQ Assistant (Phase 5).

Layout (architecture.md §8.1):
- Header: app title + persistent "Facts-only. No investment advice." badge
- Sidebar: "New Chat" button, thread list (click to switch, delete per thread), active thread highlighted
- Main area: welcome card with 3 clickable example questions on empty threads, otherwise chat history
- Bottom: chat input; spinner while the backend classifies, retrieves and generates

All data comes from the FastAPI backend (`API_URL`). If the backend is not reachable, the app
falls back to calling the same chat manager / RAG pipeline in-process, mirroring the API semantics.
"""

import os
import re
import socket
import sys
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import requests
import streamlit as st

st.set_page_config(
    page_title="HDFC Mutual Fund FAQ Assistant",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000/api").rstrip("/")
DISCLAIMER = "Facts-only. No investment advice."

EXAMPLE_QUESTIONS = [
    ("📊 Expense ratio", "What is the expense ratio of HDFC Mid Cap Fund Direct Growth?"),
    ("⏱️ Exit load", "What is the exit load for HDFC Small Cap Fund?"),
    ("💰 Minimum SIP", "What is the minimum SIP amount for HDFC Large Cap Fund?"),
]

COVERED_SCHEMES = [
    "HDFC Mid-Cap Opportunities Fund",
    "HDFC Small Cap Fund",
    "HDFC Large Cap Fund",
    "HDFC Silver ETF FoF",
    "HDFC Multi Cap Fund",
]

# In-process fallback (used only when the FastAPI server is down)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    from app.chat.manager import chat_manager
    from app.core.rag_pipeline import rag_pipeline

    HAS_LOCAL_BACKEND = True
except Exception:  # pragma: no cover - depends on environment
    HAS_LOCAL_BACKEND = False


# ==============================================================================
# API CLIENT
# ==============================================================================
def is_backend_alive() -> bool:
    """Fast TCP probe of the host/port in API_URL."""
    parsed = urlparse(API_URL)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=0.15):
            return True
    except OSError:
        return False


def api_request(method: str, endpoint: str, json_data: Optional[dict] = None) -> Tuple[int, Any]:
    """Calls the backend and returns (status_code, json_body). status 0 means unreachable."""
    method = method.upper()
    endpoint = endpoint.lstrip("/")

    if not is_backend_alive():
        if HAS_LOCAL_BACKEND:
            return local_request(method, endpoint, json_data)
        return 0, None

    url = f"{API_URL}/{endpoint}"
    timeout = (1.0, 60.0 if endpoint == "chat" else 5.0)
    try:
        resp = requests.request(method, url, json=json_data, timeout=timeout)
        try:
            body = resp.json()
        except ValueError:
            body = None
        return resp.status_code, body
    except requests.RequestException:
        if HAS_LOCAL_BACKEND:
            return local_request(method, endpoint, json_data)
        return 0, None


def local_request(method: str, endpoint: str, json_data: Optional[dict] = None) -> Tuple[int, Any]:
    """In-process equivalent of the REST API (same status codes as app/api/routes.py)."""
    json_data = json_data or {}
    parts = endpoint.split("/")

    if endpoint == "health" and method == "GET":
        return 200, {"status": "healthy", "mode": "in-process"}

    if endpoint == "threads":
        if method == "GET":
            return 200, [t.model_dump() for t in chat_manager.list_threads()]
        if method == "POST":
            return 201, chat_manager.create_thread(json_data.get("title") or "New Chat").model_dump()

    if len(parts) == 2 and parts[0] == "threads":
        thread_id = parts[1]
        if method == "GET":
            t = chat_manager.get_thread(thread_id)
            return (200, t.model_dump()) if t else (404, {"detail": "Thread not found."})
        if method == "DELETE":
            ok = chat_manager.delete_thread(thread_id)
            return (200, {"status": "deleted", "thread_id": thread_id}) if ok else (404, {"detail": "Thread not found."})

    if endpoint == "chat" and method == "POST":
        query = (json_data.get("query") or "").strip()
        if not query:
            return 400, {"detail": "Query string cannot be empty."}
        thread_id = json_data.get("thread_id")
        if thread_id:
            thread = chat_manager.get_thread(thread_id)
            if not thread:
                return 404, {"detail": "Thread not found."}
        else:
            thread = chat_manager.create_thread("New Chat")
            thread_id = thread.thread_id

        chat_manager.add_message(thread_id, "user", query)
        result = rag_pipeline.run(query)
        answer = chat_manager.add_message(
            thread_id, "assistant", result.response, source_url=result.source_url or None
        )
        if thread.title == "New Chat":
            chat_manager.auto_title_thread(thread_id, query)
        return 200, {
            "thread_id": thread_id,
            "message_id": answer.message_id,
            "query": query,
            "response": result.response,
            "source_url": result.source_url or None,
            "classification": result.category,
            "category": result.category,
            "is_refusal": result.is_refusal,
            "created_at": answer.created_at,
        }

    return 404, {"detail": "Unknown endpoint."}


# ==============================================================================
# RENDERING HELPERS
# ==============================================================================
SOURCE_RE = re.compile(r"📎\s*Source:\s*(https?://\S+)")
FOOTER_RE = re.compile(r"_?Last updated from sources:\s*([^_\n]+?)_?\s*$", re.MULTILINE)


def split_assistant_message(content: str, stored_source: Optional[str]) -> Dict[str, Optional[str]]:
    """Splits a formatted response (body / 📎 Source / footer) into its parts."""
    text = content.strip()

    source_url = stored_source
    m = SOURCE_RE.search(text)
    if m:
        source_url = source_url or m.group(1)
        text = text.replace(m.group(0), "")

    footer = None
    m = FOOTER_RE.search(text)
    if m:
        footer = f"Last updated from sources: {m.group(1).strip()}"
        text = text[: m.start()] + text[m.end():]

    return {"body": text.strip(), "source_url": source_url, "footer": footer}


def md_safe(text: str) -> str:
    """Prevents '$' amounts from being rendered as LaTeX by Streamlit markdown."""
    return text.replace("$", r"\$")


def render_assistant(content: str, source_url: Optional[str], is_refusal: Optional[bool] = None):
    """Renders an assistant answer: body, clickable citation, italic footer. Refusals are highlighted."""
    parts = split_assistant_message(content, source_url)
    # Refusals never carry a citation (rag_pipeline sets source_url=None for every non-FACTUAL category)
    if is_refusal is None:
        is_refusal = not parts["source_url"]

    if is_refusal:
        st.warning(md_safe(parts["body"]), icon="🛡️")
    else:
        st.markdown(md_safe(parts["body"]))
        if parts["source_url"]:
            url = parts["source_url"]
            st.markdown(f"📎 **Source:** [{url}]({url})")
    if parts["footer"]:
        st.markdown(f"*{parts['footer']}*")


# ==============================================================================
# STYLES — user bubbles right, assistant bubbles left
# ==============================================================================
st.markdown(
    """<style>
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    flex-direction: row-reverse;
    text-align: right;
    margin-left: 20%;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    margin-right: 20%;
}
.disclaimer-badge {
    display: inline-block;
    padding: 0.35rem 0.75rem;
    border-radius: 999px;
    border: 1px solid rgba(250, 202, 21, 0.6);
    background: rgba(250, 202, 21, 0.12);
    font-weight: 600;
    font-size: 0.9rem;
}
</style>""",
    unsafe_allow_html=True,
)

# ==============================================================================
# SESSION STATE
# ==============================================================================
st.session_state.setdefault("current_thread_id", None)
st.session_state.setdefault("pending_query", None)
st.session_state.setdefault("chat_error", None)

# ==============================================================================
# SIDEBAR — THREADS
# ==============================================================================
status_code, threads_body = api_request("GET", "threads")
threads = threads_body if status_code == 200 and isinstance(threads_body, list) else []
thread_ids = {t["thread_id"] for t in threads}

# Drop a stale selection (e.g. thread deleted elsewhere)
if st.session_state.current_thread_id and st.session_state.current_thread_id not in thread_ids:
    st.session_state.current_thread_id = threads[0]["thread_id"] if threads else None
# Default to the most recent thread on first load
if st.session_state.current_thread_id is None and threads:
    st.session_state.current_thread_id = threads[0]["thread_id"]

with st.sidebar:
    st.markdown(f'<span class="disclaimer-badge">⚠️ {DISCLAIMER}</span>', unsafe_allow_html=True)
    st.markdown("### 📋 Threads")

    if st.button("➕ New Chat", use_container_width=True, type="primary"):
        current = next((t for t in threads if t["thread_id"] == st.session_state.current_thread_id), None)
        # Reuse the current thread if it is still empty instead of piling up blank threads
        if not (current and current.get("message_count", 0) == 0):
            code, created = api_request("POST", "threads", {"title": "New Chat"})
            if code == 201 and created:
                st.session_state.current_thread_id = created["thread_id"]
            else:
                st.session_state.current_thread_id = None  # first message will auto-create a thread
        st.rerun()

    st.divider()

    if status_code == 0:
        st.error("Backend unreachable. Start it with `uvicorn app.main:app --port 8000`.")
    elif not threads:
        st.caption("No conversations yet. Ask a question to start one.")

    for t in threads:
        t_id = t["thread_id"]
        is_active = t_id == st.session_state.current_thread_id
        col_title, col_del = st.columns([0.8, 0.2])
        with col_title:
            label = f"{'● ' if is_active else '○ '}{t.get('title') or 'New Chat'}"
            if st.button(label, key=f"t_{t_id}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state.current_thread_id = t_id
                st.rerun()
        with col_del:
            if st.button("🗑️", key=f"del_{t_id}", help="Delete this thread", use_container_width=True):
                api_request("DELETE", f"threads/{t_id}")
                if is_active:
                    st.session_state.current_thread_id = None
                st.rerun()

    st.divider()
    st.caption("🏦 **Covered schemes**")
    st.caption("\n".join(f"• {s}" for s in COVERED_SCHEMES))

# ==============================================================================
# HEADER
# ==============================================================================
col_title, col_badge = st.columns([0.68, 0.32])
with col_title:
    st.markdown("## 🏦 HDFC Mutual Fund FAQ Assistant")
with col_badge:
    st.markdown(f'<span class="disclaimer-badge">⚠️ {DISCLAIMER}</span>', unsafe_allow_html=True)
st.divider()

# ==============================================================================
# CHAT AREA
# ==============================================================================
messages = []
if st.session_state.current_thread_id:
    code, thread = api_request("GET", f"threads/{st.session_state.current_thread_id}")
    if code == 200 and thread:
        messages = thread.get("messages") or []

if st.session_state.chat_error:
    st.error(st.session_state.chat_error)
    st.session_state.chat_error = None

if not messages and not st.session_state.pending_query:
    # Welcome card
    with st.container(border=True):
        st.markdown("#### 👋 Welcome! I can answer factual questions about HDFC Mutual Fund schemes.")
        st.markdown(
            "Ask about expense ratio, exit load, minimum SIP, lock-in, riskometer, benchmark, "
            "or how to download statements. Every answer is at most 3 sentences with one official source link."
        )
        st.warning(f"**{DISCLAIMER}** I can't recommend, compare or predict fund performance.", icon="⚠️")
        st.markdown("**Try asking:**")
        cols = st.columns(len(EXAMPLE_QUESTIONS))
        for idx, (label, question) in enumerate(EXAMPLE_QUESTIONS):
            with cols[idx]:
                if st.button(f"{label}\n\n{question}", key=f"example_{idx}", use_container_width=True):
                    st.session_state.pending_query = question
                    st.rerun()

for msg in messages:
    if msg.get("role") == "user":
        with st.chat_message("user"):
            st.markdown(md_safe(msg.get("content", "")))
    else:
        with st.chat_message("assistant"):
            render_assistant(msg.get("content", ""), msg.get("source_url"))

# ==============================================================================
# INPUT & SEND
# ==============================================================================
user_input = st.chat_input("Type your question...")

query = None
if st.session_state.pending_query:
    query = st.session_state.pending_query
    st.session_state.pending_query = None
elif user_input and user_input.strip():
    query = user_input.strip()

if query:
    with st.chat_message("user"):
        st.markdown(md_safe(query))

    with st.chat_message("assistant"):
        with st.spinner("Retrieving verified facts..."):
            payload = {"query": query, "thread_id": st.session_state.current_thread_id}
            code, res = api_request("POST", "chat", payload)
            if code == 404:
                # Active thread vanished; start a new one with this question
                payload["thread_id"] = None
                code, res = api_request("POST", "chat", payload)

        if code == 200 and res and "response" in res:
            st.session_state.current_thread_id = res["thread_id"]
            st.rerun()  # re-render from persisted history (updates sidebar titles too)
        else:
            detail = (res or {}).get("detail") if isinstance(res, dict) else None
            st.session_state.chat_error = (
                f"Could not get a response ({detail or 'backend unavailable'}). Please try again."
            )
            st.rerun()
