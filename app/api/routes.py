"""FastAPI route definitions for chat, threads, and health operations."""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Path, status

from app.chat.manager import chat_manager
from app.chat.models import (
    ChatRequest,
    ChatResponse,
    Thread,
    ThreadCreate,
    ThreadUpdate,
)
from app.config import settings
from app.core.generator import rag_pipeline

logger = logging.getLogger("api.routes")
router = APIRouter(prefix="/api", tags=["Chat & Threads"])


@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def send_chat_message(request: ChatRequest):
    """
    Core conversational endpoint:
    - Resolves or creates a thread
    - Persists user query
    - Executes safety check & RAG pipeline
    - Persists assistant response
    - Auto-titles thread on first turn
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string cannot be empty.",
        )

    # 1. Resolve or create thread
    thread_id = request.thread_id
    thread = None
    if thread_id:
        thread = chat_manager.get_thread(thread_id)

    if not thread:
        thread = chat_manager.create_thread(title="New Chat")
        thread_id = thread.thread_id

    # 2. Persist user message
    user_msg = chat_manager.add_message(
        thread_id=thread_id,
        role="user",
        content=query,
    )

    # 3. Execute RAG pipeline
    rag_result = rag_pipeline.run(query)

    response_text = rag_result.get("response", "")
    source_url = rag_result.get("source_url") or None
    category = rag_result.get("category", "FACTUAL")
    is_refusal = rag_result.get("is_refusal", False)

    # 4. Persist assistant message
    assistant_msg = chat_manager.add_message(
        thread_id=thread_id,
        role="assistant",
        content=response_text,
        source_url=source_url,
    )

    # 5. Auto-title thread if newly created
    if thread.title == "New Chat":
        chat_manager.auto_title_thread(thread_id, query)

    return ChatResponse(
        thread_id=thread_id,
        message_id=assistant_msg.message_id,
        response=response_text,
        source_url=source_url,
        category=category,
        is_refusal=is_refusal,
        created_at=assistant_msg.created_at,
    )


@router.post("/threads", response_model=Thread, status_code=status.HTTP_201_CREATED)
def create_thread(request: Optional[ThreadCreate] = None):
    """Creates a new conversation thread."""
    title = request.title if request and request.title else "New Chat"
    return chat_manager.create_thread(title=title)


@router.get("/threads", response_model=List[Thread])
def list_threads():
    """Lists all threads sorted by recent activity."""
    return chat_manager.list_threads()


@router.get("/threads/{thread_id}", response_model=Thread)
def get_thread(thread_id: str = Path(..., description="Thread UUID")):
    """Retrieves a thread with complete message history."""
    thread = chat_manager.get_thread(thread_id)
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found.",
        )
    return thread


@router.delete("/threads/{thread_id}", status_code=status.HTTP_200_OK)
def delete_thread(thread_id: str = Path(..., description="Thread UUID")):
    """Deletes a thread and its messages via cascade delete."""
    success = chat_manager.delete_thread(thread_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found.",
        )
    return {"status": "deleted", "thread_id": thread_id}


@router.patch("/threads/{thread_id}", response_model=Thread)
def rename_thread(request: ThreadUpdate, thread_id: str = Path(..., description="Thread UUID")):
    """Renames an existing thread."""
    success = chat_manager.rename_thread(thread_id, request.title)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found.",
        )
    return chat_manager.get_thread(thread_id)


@router.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint confirming system health and configuration."""
    return {
        "status": "healthy",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "disclaimer": "Facts-only. No investment advice.",
    }
