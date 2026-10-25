"""Integration tests for FastAPI REST endpoints using TestClient."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

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

