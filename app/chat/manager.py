"""SQLite-backed multi-thread conversation manager."""

import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, List, Optional

from app.chat.models import Message, Thread
from app.config import settings

logger = logging.getLogger("chat.manager")


class ChatThreadManager:
    """Manages multi-thread SQLite database operations with thread isolation and cascading deletion."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.chat_db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Creates a database connection with foreign key enforcement and guaranteed closure."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Crucial for CASCADE DELETE in SQLite:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initializes tables and indexes."""
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    thread_id   TEXT PRIMARY KEY,
                    title       TEXT NOT NULL DEFAULT 'New Chat',
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_id  TEXT PRIMARY KEY,
                    thread_id   TEXT NOT NULL,
                    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content     TEXT NOT NULL,
                    source_url  TEXT,
                    created_at  TEXT NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
                """
            )
            conn.commit()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_thread(self, title: str = "New Chat") -> Thread:
        """Creates a new conversation thread."""
        thread_id = str(uuid.uuid4())
        now = self._now_iso()

        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO threads (thread_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (thread_id, title.strip() or "New Chat", now, now),
            )
            conn.commit()

        return Thread(
            thread_id=thread_id,
            title=title.strip() or "New Chat",
            created_at=now,
            updated_at=now,
            message_count=0,
            messages=[],
        )

    def list_threads(self) -> List[Thread]:
        """Lists all threads ordered by updated_at descending, including message counts."""
        with self._get_connection() as conn:
            query = """
                SELECT t.thread_id, t.title, t.created_at, t.updated_at,
                       COUNT(m.message_id) AS message_count
                FROM threads t
                LEFT JOIN messages m ON t.thread_id = m.thread_id
                GROUP BY t.thread_id
                ORDER BY t.updated_at DESC
            """
            cursor = conn.execute(query)
            rows = cursor.fetchall()

        threads = []
        for r in rows:
            threads.append(
                Thread(
                    thread_id=r["thread_id"],
                    title=r["title"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    message_count=r["message_count"],
                    messages=[],
                )
            )
        return threads

    def get_thread(self, thread_id: str, limit: Optional[int] = None) -> Optional[Thread]:
        """Retrieves a specific thread along with its full or paginated message history."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT thread_id, title, created_at, updated_at FROM threads WHERE thread_id = ?",
                (thread_id,),
            )
            t_row = cursor.fetchone()
            if not t_row:
                return None

            # Count total messages in thread
            count_cursor = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE thread_id = ?",
                (thread_id,),
            )
            total_messages = count_cursor.fetchone()[0]

            if limit and limit > 0:
                # Retrieve the most recent N messages, ordered chronologically
                cursor = conn.execute(
                    "SELECT message_id, thread_id, role, content, source_url, created_at FROM messages WHERE thread_id = ? ORDER BY created_at DESC LIMIT ?",
                    (thread_id, limit),
                )
                m_rows = list(reversed(cursor.fetchall()))
            else:
                cursor = conn.execute(
                    "SELECT message_id, thread_id, role, content, source_url, created_at FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
                    (thread_id,),
                )
                m_rows = cursor.fetchall()

        messages = [
            Message(
                message_id=m["message_id"],
                thread_id=m["thread_id"],
                role=m["role"],
                content=m["content"],
                source_url=m["source_url"],
                created_at=m["created_at"],
            )
            for m in m_rows
        ]

        return Thread(
            thread_id=t_row["thread_id"],
            title=t_row["title"],
            created_at=t_row["created_at"],
            updated_at=t_row["updated_at"],
            message_count=total_messages,
            messages=messages,
        )

    def get_thread_history(self, thread_id: str, limit: Optional[int] = None) -> List[Message]:
        """Returns message list for a thread, with optional limit."""
        thread = self.get_thread(thread_id, limit=limit)
        return thread.messages if thread else []

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        source_url: Optional[str] = None,
    ) -> Message:
        """Appends a message to a thread and updates the thread's updated_at timestamp."""
        # Ensure thread exists
        thread = self.get_thread(thread_id)
        if not thread:
            thread = self.create_thread()
            thread_id = thread.thread_id

        message_id = str(uuid.uuid4())
        now = self._now_iso()

        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO messages (message_id, thread_id, role, content, source_url, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (message_id, thread_id, role, content, source_url, now),
            )
            conn.execute(
                "UPDATE threads SET updated_at = ? WHERE thread_id = ?",
                (now, thread_id),
            )
            conn.commit()

        return Message(
            message_id=message_id,
            thread_id=thread_id,
            role=role,
            content=content,
            source_url=source_url,
            created_at=now,
        )

    def delete_thread(self, thread_id: str) -> bool:
        """Deletes a thread. Messages are removed automatically via ON DELETE CASCADE."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
            conn.commit()
            return cursor.rowcount > 0

    def rename_thread(self, thread_id: str, title: str) -> bool:
        """Renames an existing thread."""
        now = self._now_iso()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE threads SET title = ?, updated_at = ? WHERE thread_id = ?",
                (title.strip(), now, thread_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def auto_title_thread(self, thread_id: str, first_query: str) -> str:
        """
        Auto-generates a concise title (≤ 6 words) from the user's first query
        if the thread is currently titled 'New Chat'.
        """
        thread = self.get_thread(thread_id)
        if not thread or thread.title != "New Chat":
            return thread.title if thread else ""

        # Extract first 6 words
        words = first_query.strip().split()
        if not words:
            return "New Chat"

        short_title = " ".join(words[:6])
        if len(words) > 6:
            short_title += "..."

        self.rename_thread(thread_id, short_title)
        return short_title


# Global manager instance
chat_manager = ChatThreadManager()
