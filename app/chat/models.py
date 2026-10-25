"""Pydantic models and request/response schemas for chat and thread management."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class MessageBase(BaseModel):
    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    source_url: Optional[str] = Field(default=None, description="Citation URL if applicable")


class MessageCreate(MessageBase):
    thread_id: str = Field(..., description="Thread UUID")


class Message(MessageBase):
    message_id: str = Field(..., description="Unique message UUID")
    thread_id: str = Field(..., description="Thread UUID")
    created_at: str = Field(..., description="ISO timestamp")


class ThreadBase(BaseModel):
    title: str = Field(default="New Chat", description="Thread display title")


class ThreadCreate(BaseModel):
    title: Optional[str] = Field(default="New Chat", description="Optional initial thread title")


class ThreadUpdate(BaseModel):
    title: str = Field(..., description="Updated thread title")


class Thread(ThreadBase):
    thread_id: str = Field(..., description="Unique thread UUID")
    created_at: str = Field(..., description="ISO timestamp")
    updated_at: str = Field(..., description="ISO timestamp")
    message_count: Optional[int] = Field(default=0, description="Count of messages in thread")
    messages: Optional[List[Message]] = Field(default_factory=list, description="Thread message history")


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User question or prompt")
    thread_id: Optional[str] = Field(default=None, description="Existing thread ID or None for auto-create")


class ChatResponse(BaseModel):
    thread_id: str = Field(..., description="Thread ID")
    message_id: str = Field(..., description="Assistant message UUID")
    response: str = Field(..., description="Formatted answer or refusal text")
    source_url: Optional[str] = Field(default=None, description="Official cited URL")
    category: str = Field(default="FACTUAL", description="Classification category")
    is_refusal: bool = Field(default=False, description="Whether the answer is a refusal")
    created_at: str = Field(..., description="ISO timestamp")
