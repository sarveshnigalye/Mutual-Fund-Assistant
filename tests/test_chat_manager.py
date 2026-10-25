"""Unit tests for the SQLite-backed ChatThreadManager."""

import os
import tempfile
import pytest

from app.chat.manager import ChatThreadManager


@pytest.fixture
def temp_manager():
    """Provides a ChatThreadManager with a clean temporary SQLite database."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "test_chat.db")
        manager = ChatThreadManager(db_path=db_path)
        yield manager


def test_create_and_list_threads(temp_manager):
    thread1 = temp_manager.create_thread("First Thread")
    thread2 = temp_manager.create_thread("Second Thread")

    threads = temp_manager.list_threads()
    assert len(threads) == 2
    ids = [t.thread_id for t in threads]
    assert thread1.thread_id in ids
    assert thread2.thread_id in ids


def test_add_and_retrieve_messages(temp_manager):
    thread = temp_manager.create_thread("Test Thread")

    msg1 = temp_manager.add_message(
        thread_id=thread.thread_id,
        role="user",
        content="What is expense ratio of HDFC Mid Cap?",
    )
    msg2 = temp_manager.add_message(
        thread_id=thread.thread_id,
        role="assistant",
        content="The expense ratio is 0.60%.",
        source_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
    )

    history = temp_manager.get_thread_history(thread.thread_id)
    assert len(history) == 2
    assert history[0].content == "What is expense ratio of HDFC Mid Cap?"
    assert history[0].role == "user"
    assert history[1].content == "The expense ratio is 0.60%."
    assert history[1].role == "assistant"
    assert history[1].source_url == "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"


def test_thread_isolation(temp_manager):
    thread_a = temp_manager.create_thread("Thread A")
    thread_b = temp_manager.create_thread("Thread B")

    temp_manager.add_message(thread_a.thread_id, "user", "Message in A 1")
    temp_manager.add_message(thread_b.thread_id, "user", "Message in B 1")
    temp_manager.add_message(thread_a.thread_id, "assistant", "Message in A 2")

    history_a = temp_manager.get_thread_history(thread_a.thread_id)
    history_b = temp_manager.get_thread_history(thread_b.thread_id)

    assert len(history_a) == 2
    assert len(history_b) == 1
    assert [m.content for m in history_a] == ["Message in A 1", "Message in A 2"]
    assert [m.content for m in history_b] == ["Message in B 1"]


def test_delete_thread_cascades(temp_manager):
    thread = temp_manager.create_thread("To Delete")
    temp_manager.add_message(thread.thread_id, "user", "Will be deleted")
    temp_manager.add_message(thread.thread_id, "assistant", "Also deleted")

    assert len(temp_manager.get_thread_history(thread.thread_id)) == 2

    # Delete thread
    deleted = temp_manager.delete_thread(thread.thread_id)
    assert deleted is True

    # Verify thread and messages are gone
    assert temp_manager.get_thread(thread.thread_id) is None
    assert len(temp_manager.get_thread_history(thread.thread_id)) == 0

    with temp_manager._get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM messages WHERE thread_id = ?", (thread.thread_id,))
        count = cursor.fetchone()[0]
        assert count == 0


def test_rename_and_auto_title(temp_manager):
    thread = temp_manager.create_thread("New Chat")
    assert thread.title == "New Chat"

    # Auto title based on first query
    query = "What is the exit load for HDFC Small Cap Fund Direct Growth?"
    new_title = temp_manager.auto_title_thread(thread.thread_id, query)
    assert new_title == "What is the exit load for..."

    # Manual rename
    renamed = temp_manager.rename_thread(thread.thread_id, "Small Cap Exit Load FAQ")
    assert renamed is True

    updated_thread = temp_manager.get_thread(thread.thread_id)
    assert updated_thread.title == "Small Cap Exit Load FAQ"


def test_auto_title_variations(temp_manager):
    thread1 = temp_manager.create_thread("New Chat")
    # Short query (<6 words) should not have trailing ellipsis
    title1 = temp_manager.auto_title_thread(thread1.thread_id, "Expense ratio query")
    assert title1 == "Expense ratio query"

    thread2 = temp_manager.create_thread("New Chat")
    # Empty query should keep 'New Chat'
    title2 = temp_manager.auto_title_thread(thread2.thread_id, "   ")
    assert title2 == "New Chat"


def test_thread_history_with_limit(temp_manager):
    thread = temp_manager.create_thread("Pagination Test")
    for i in range(1, 6):
        temp_manager.add_message(thread.thread_id, "user", f"User query {i}")
        temp_manager.add_message(thread.thread_id, "assistant", f"Assistant answer {i}")

    # Total messages: 10
    full_thread = temp_manager.get_thread(thread.thread_id)
    assert full_thread.message_count == 10
    assert len(full_thread.messages) == 10

    # Paginated: last 4 messages in chronological order
    limited_thread = temp_manager.get_thread(thread.thread_id, limit=4)
    assert limited_thread.message_count == 10  # Total remains 10
    assert len(limited_thread.messages) == 4
    assert limited_thread.messages[0].content == "User query 4"
    assert limited_thread.messages[1].content == "Assistant answer 4"
    assert limited_thread.messages[2].content == "User query 5"
    assert limited_thread.messages[3].content == "Assistant answer 5"


def test_nonexistent_thread_handling(temp_manager):
    # Nonexistent thread returns None
    assert temp_manager.get_thread("nonexistent-id-12345") is None
    assert temp_manager.get_thread_history("nonexistent-id-12345") == []

    # Adding message to nonexistent thread auto-creates the thread
    msg = temp_manager.add_message(
        thread_id="nonexistent-id-auto",
        role="user",
        content="Auto create thread test",
    )
    assert msg.thread_id != "nonexistent-id-auto"  # A valid UUID was assigned
    created = temp_manager.get_thread(msg.thread_id)
    assert created is not None
    assert len(created.messages) == 1

