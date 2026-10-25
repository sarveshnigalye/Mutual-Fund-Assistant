"""Streamlit frontend for HDFC Mutual Fund FAQ Assistant."""

import logging
import os
import requests
import streamlit as st

# Configure page
st.set_page_config(
    page_title="HDFC Mutual Fund FAQ Assistant",
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

# Example questions for quick start
EXAMPLE_QUESTIONS = [
    "What is the expense ratio of HDFC Mid Cap Fund Direct Growth?",
    "What is the exit load for HDFC Small Cap Fund?",
    "What is the minimum SIP amount for HDFC Top 100 Fund?",
]

# Custom CSS styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.1rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .disclaimer-banner {
        background-color: #FEF3C7;
        border-left: 5px solid #F59E0B;
        padding: 0.65rem 1rem;
        border-radius: 4px;
        color: #92400E;
        font-weight: 600;
        font-size: 0.95rem;
        margin-bottom: 1.2rem;
    }
    .welcome-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1.5rem;
        margin: 1rem 0;
    }
    .source-box {
        background-color: #F1F5F9;
        border-left: 4px solid #3B82F6;
        padding: 0.5rem 0.8rem;
        font-size: 0.9rem;
        margin-top: 0.5rem;
    }
    .thread-title-btn {
        text-align: left;
        width: 100%;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_request(method: str, endpoint: str, json_data=None):
    """Makes HTTP request to FastAPI backend with local fallback."""
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
        # Fallback to local Python modules if API server is not running
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


# --- SIDEBAR: Multi-Thread Chat Management ---
with st.sidebar:
    st.title("💬 Conversations")

    if st.button("➕ New Chat", use_container_width=True, type="primary"):
        create_new_thread()

    st.markdown("---")

    threads_data = api_request("GET", "threads") or []
    if not threads_data:
        # Auto-create initial thread if none exist
        init_thread = api_request("POST", "threads", {"title": "New Chat"})
        if init_thread:
            st.session_state.current_thread_id = init_thread["thread_id"]
            threads_data = [init_thread]

    # Ensure valid current thread id
    thread_ids = [t["thread_id"] for t in threads_data]
    if st.session_state.current_thread_id not in thread_ids and thread_ids:
        st.session_state.current_thread_id = thread_ids[0]

    for t in threads_data:
        t_id = t["thread_id"]
        t_title = t.get("title", "New Chat")
        is_active = (t_id == st.session_state.current_thread_id)

        col1, col2 = st.columns([0.82, 0.18])
        with col1:
            btn_label = f"📌 {t_title}" if is_active else f"💭 {t_title}"
            if st.button(btn_label, key=f"t_{t_id}", use_container_width=True):
                switch_thread(t_id)
        with col2:
            if st.button("🗑️", key=f"del_{t_id}", help="Delete chat"):
                api_request("DELETE", f"threads/{t_id}")
                if st.session_state.current_thread_id == t_id:
                    st.session_state.current_thread_id = None
                st.rerun()

    st.markdown("---")
    st.caption("🏦 **Corpus Covered (HDFC AMC on Groww):**")
    st.caption("• HDFC Mid-Cap Opportunities Fund\n• HDFC Small Cap Fund\n• HDFC Top 100 Large Cap Fund\n• HDFC Silver ETF FoF\n• HDFC Multi Cap Fund")


# --- MAIN AREA ---
st.markdown('<div class="main-header">🏦 HDFC Mutual Fund FAQ Assistant</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="disclaimer-banner">⚠️ <b>MANDATORY DISCLAIMER:</b> Facts-only assistant. No investment advice, opinions, or recommendations provided. Not a SEBI-registered advisor.</div>',
    unsafe_allow_html=True,
)

# Fetch messages for current thread
current_thread = None
messages = []
if st.session_state.current_thread_id:
    current_thread = api_request("GET", f"threads/{st.session_state.current_thread_id}")
    if current_thread:
        messages = current_thread.get("messages", [])

# Display Welcome Screen if thread has no messages
if not messages:
    with st.container():
        st.markdown(
            """
            <div class="welcome-card">
                <h3>👋 Welcome to the Facts-Only Mutual Fund FAQ Assistant</h3>
                <p>I answer objective, verifiable questions about <b>5 HDFC Mutual Fund schemes</b> based exclusively on official Groww scheme data.</p>
                <p>Click any example question below or type your own question:</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        cols = st.columns(3)
        for i, q in enumerate(EXAMPLE_QUESTIONS):
            with cols[i]:
                if st.button(q, key=f"ex_{i}", use_container_width=True):
                    st.session_state.pending_query = q
                    st.rerun()

# Display chat history
for msg in messages:
    role = msg.get("role", "user")
    content = msg.get("content", "")
    with st.chat_message(role):
        st.markdown(content)

# Handle Pending Query or New User Input
user_input = st.chat_input("Ask a factual question about HDFC Mutual Fund schemes...")

query_to_send = None
if st.session_state.pending_query:
    query_to_send = st.session_state.pending_query
    st.session_state.pending_query = None
elif user_input:
    query_to_send = user_input.strip()

if query_to_send:
    # 1. Display user query immediately
    with st.chat_message("user"):
        st.markdown(query_to_send)

    # 2. Call backend with spinner
    with st.chat_message("assistant"):
        with st.spinner("Retrieving verified facts & generating response..."):
            payload = {
                "query": query_to_send,
                "thread_id": st.session_state.current_thread_id,
            }
            res = api_request("POST", "chat", payload)

            if res and "response" in res:
                response_text = res["response"]
                st.markdown(response_text)
                if "thread_id" in res:
                    st.session_state.current_thread_id = res["thread_id"]
            else:
                st.error("Failed to generate response. Please try again.")

    st.rerun()

# Footer disclaimer
st.markdown("---")
st.caption(
    "🔒 **Regulatory Compliance Note:** All answers are restricted to factual Groww data, capped at 3 sentences, and cite verified source URLs. "
    "For financial planning or advisory services, please consult a SEBI-registered financial advisor."
)
