from __future__ import annotations

from typing import Iterator

from study.connectors.base import LLMConnector
from study.models import Message, Response, Tool


class OpenAIConnector(LLMConnector):
    def complete(self, messages: list[Message], tools: list[Tool] | None = None) -> Response:
        raise NotImplementedError(
            "OpenAIConnector is not yet implemented. "
            "Set connector = 'ollama' in ~/.study/config.toml"
        )

    def stream(self, messages: list[Message], tools: list[Tool] | None = None) -> Iterator[str]:
        raise NotImplementedError("OpenAIConnector is not yet implemented.")
