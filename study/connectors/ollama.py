from __future__ import annotations

import uuid
from typing import Any, Iterator

import ollama

from study.connectors.base import LLMConnector
from study.models import Message, Response, Tool, ToolCall


def _tool_to_ollama(tool: Tool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


class OllamaConnector(LLMConnector):
    def complete(self, messages: list[Message], tools: list[Tool] | None = None) -> Response:
        msg_dicts = self._messages_to_ollama(messages)
        kwargs: dict[str, Any] = {"model": self.model, "messages": msg_dicts}
        if tools:
            kwargs["tools"] = [_tool_to_ollama(t) for t in tools]

        response = ollama.chat(**kwargs)
        ollama_msg = response.message

        tool_calls: list[ToolCall] = []
        if ollama_msg.tool_calls:
            for tc in ollama_msg.tool_calls:
                # Ollama .arguments is already a dict — do NOT json.loads()
                args = tc.function.arguments
                if not isinstance(args, dict):
                    import json
                    args = json.loads(args)
                tool_calls.append(ToolCall(
                    id=str(uuid.uuid4()),  # Ollama doesn't assign IDs
                    name=tc.function.name,
                    arguments=args,
                ))

        stop_reason = "tool_use" if tool_calls else "stop"
        msg = Message(
            role="assistant",
            content=ollama_msg.content or None,
            tool_calls=tool_calls,
        )
        return Response(message=msg, stop_reason=stop_reason, model=self.model)

    def stream(self, messages: list[Message], tools: list[Tool] | None = None) -> Iterator[str]:
        """Stream text. Do not call with tools — Ollama doesn't support streaming + tools."""
        msg_dicts = self._messages_to_ollama(messages)
        for chunk in ollama.chat(model=self.model, messages=msg_dicts, stream=True):
            text = chunk.message.content
            if text:
                yield text

    def _messages_to_ollama(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert Message objects to Ollama-compatible dicts."""
        result = []
        for msg in messages:
            if msg.role == "tool":
                result.append({
                    "role": "tool",
                    "content": msg.content or "",
                })
            elif msg.tool_calls:
                result.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": tc.name,
                                "arguments": tc.arguments,
                            }
                        }
                        for tc in msg.tool_calls
                    ],
                })
            else:
                result.append({
                    "role": msg.role,
                    "content": msg.content or "",
                })
        return result
