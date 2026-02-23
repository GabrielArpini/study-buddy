from __future__ import annotations

from study.connectors.base import LLMConnector

CONNECTOR_MAP: dict[str, str] = {
    "ollama": "study.connectors.ollama.OllamaConnector",
    "anthropic": "study.connectors.anthropic.AnthropicConnector",
    "openai": "study.connectors.openai.OpenAIConnector",
}


def get_connector(name: str, model: str) -> LLMConnector:
    """Factory: resolve connector name to class and instantiate."""
    if name not in CONNECTOR_MAP:
        raise ValueError(f"Unknown connector '{name}'. Available: {list(CONNECTOR_MAP)}")
    module_path, class_name = CONNECTOR_MAP[name].rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(model=model)
