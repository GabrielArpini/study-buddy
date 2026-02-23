from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator

from study.models import Message, Response, Tool


class LLMConnector(ABC):
    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
    def complete(self, messages: list[Message], tools: list[Tool] | None = None) -> Response:
        """Non-streaming completion. Always use this when tools are provided."""
        ...

    @abstractmethod
    def stream(self, messages: list[Message], tools: list[Tool] | None = None) -> Iterator[str]:
        """Streaming text completion. Should not be used when tools are active."""
        ...

    def _messages_to_dicts(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert Message objects to plain dicts for API calls."""
        result = []
        for msg in messages:
            if msg.role == "tool":
                result.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content or "",
                    "name": msg.name,
                })
            elif msg.tool_calls:
                d: dict[str, Any] = {
                    "role": msg.role,
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": tc.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
                result.append(d)
            else:
                result.append({
                    "role": msg.role,
                    "content": msg.content or "",
                })
        return result
