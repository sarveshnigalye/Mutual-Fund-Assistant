"""Integration tests for FastAPI REST endpoints using TestClient."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.markers import requires_index, requires_llm

client = TestClient(app)


def test_health_check_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "disclaimer" in data
    assert "Facts-only" in data["disclaimer"]


def test_thread_crud_lifecycle():
    # 1. Create thread
    res_create = client.post("/api/threads", json={"title": "Test Investment Chat"})
    assert res_create.status_code == 201
    created_thread = res_create.json()
    thread_id = created_thread["thread_id"]
    assert created_thread["title"] == "Test Investment Chat"

    # 2. List threads
    res_list = client.get("/api/threads")
    assert res_list.status_code == 200
    threads = res_list.json()
    assert any(t["thread_id"] == thread_id for t in threads)

    # 3. Get thread details
    res_get = client.get(f"/api/threads/{thread_id}")
    assert res_get.status_code == 200
    thread_data = res_get.json()
    assert thread_data["thread_id"] == thread_id
    assert thread_data["messages"] == []

    # 4. Rename thread
    res_rename = client.patch(f"/api/threads/{thread_id}", json={"title": "Renamed Thread Title"})
    assert res_rename.status_code == 200
    assert res_rename.json()["title"] == "Renamed Thread Title"

    # 5. Delete thread
    res_delete = client.delete(f"/api/threads/{thread_id}")
    assert res_delete.status_code == 200
    assert res_delete.json()["status"] == "deleted"

    # 6. Verify 404 after deletion
    res_verify = client.get(f"/api/threads/{thread_id}")
    assert res_verify.status_code == 404


def test_chat_endpoint_advisory_refusal():
    # Send an advisory query
    res = client.post("/api/chat", json={"query": "Should I invest in HDFC Mid Cap Fund?"})
    assert res.status_code == 200
    data = res.json()
    assert data["is_refusal"] is True
    assert data["category"] == "ADVISORY"
    assert "SEBI-registered" in data["response"]
    assert data["thread_id"] is not None


def test_chat_endpoint_empty_query():
    res = client.post("/api/chat", json={"query": "   "})
    assert res.status_code == 400


@requires_index
@requires_llm
def test_chat_endpoint_factual_query_roundtrip():
    # 1. Create a clean thread
    res_t = client.post("/api/threads", json={"title": "Factual Test Chat"})
    assert res_t.status_code == 201
    thread_id = res_t.json()["thread_id"]

    # 2. Submit factual query to /api/chat
    query = "What is the expense ratio of HDFC Mid Cap Fund Direct Growth?"
    res_chat = client.post("/api/chat", json={"query": query, "thread_id": thread_id})
    assert res_chat.status_code == 200
    data = res_chat.json()

    assert data["thread_id"] == thread_id
    assert data["category"] == "FACTUAL"
    assert data["is_refusal"] is False
    assert data["source_url"] is not None
    assert "https://groww.in" in data["source_url"]
    assert "0.60%" in data["response"] or "expense ratio" in data["response"].lower()

    # 3. Verify messages are persisted in thread history
    res_hist = client.get(f"/api/threads/{thread_id}")
    assert res_hist.status_code == 200
    history = res_hist.json()["messages"]
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == query
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == data["response"]


def test_chat_endpoint_auto_creates_and_titles_thread():
    query = "What is the exit load for HDFC Small Cap Fund Direct Growth?"
    res = client.post("/api/chat", json={"query": query})
    assert res.status_code == 200
    data = res.json()
    assert data["thread_id"] is not None

    # Check that thread was created and auto-titled with <=6 words
    res_thread = client.get(f"/api/threads/{data['thread_id']}")
    assert res_thread.status_code == 200
    thread = res_thread.json()
    assert thread["title"] != "New Chat"
    assert "exit load" in thread["title"].lower()


def test_chat_endpoint_pii_detection_refusal():
    res = client.post("/api/chat", json={"query": "My PAN is ABCDE1234F, show my balance"})
    assert res.status_code == 200
    data = res.json()
    assert data["is_refusal"] is True
    assert data["category"] == "PII_DETECTED"
    assert "⚠️ Please do not share personal information" in data["response"]


def test_thread_error_handling_404s():
    # 404 for getting non-existent thread
    res_get = client.get("/api/threads/non-existent-uuid-9999")
    assert res_get.status_code == 404

    # 404 for patching non-existent thread
    res_patch = client.patch("/api/threads/non-existent-uuid-9999", json={"title": "New Title"})
    assert res_patch.status_code == 404

    # 404 for deleting non-existent thread
    res_del = client.delete("/api/threads/non-existent-uuid-9999")
    assert res_del.status_code == 404


def test_chat_endpoint_invalid_thread_id_returns_404():
    res = client.post(
        "/api/chat",
        json={"query": "What is the exit load for HDFC Small Cap Fund?", "thread_id": "non-existent-uuid-9999"},
    )
    assert res.status_code == 404
    # No orphan thread should have been created for the unknown ID
    assert all(t["thread_id"] != "non-existent-uuid-9999" for t in client.get("/api/threads").json())


def test_chat_endpoint_missing_query_returns_422():
    res = client.post("/api/chat", json={})
    assert res.status_code == 422


def test_rename_thread_blank_title_rejected():
    thread_id = client.post("/api/threads", json={"title": "Keep Me"}).json()["thread_id"]
    res = client.patch(f"/api/threads/{thread_id}", json={"title": "   "})
    assert res.status_code == 422
    assert client.get(f"/api/threads/{thread_id}").json()["title"] == "Keep Me"
    client.delete(f"/api/threads/{thread_id}")


def test_chat_response_schema_matches_architecture():
    query = "Should I invest in HDFC Mid Cap Fund?"
    data = client.post("/api/chat", json={"query": query}).json()
    for key in ("thread_id", "message_id", "query", "response", "classification", "source_url", "is_refusal"):
        assert key in data, f"missing '{key}' in /api/chat response"
    assert data["query"] == query
    assert data["classification"] == "ADVISORY"
    assert data["source_url"] is None


