from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class Message(BaseModel):
    role: str  # "user" | "assistant" | "tool"
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None  # for role="tool" responses
    name: str | None = None  # tool name for role="tool"


class Tool(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object


class Response(BaseModel):
    message: Message
    stop_reason: str  # "stop" | "tool_use"
    model: str = ""
