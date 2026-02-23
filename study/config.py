from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

CONFIG_DIR = Path("~/.study").expanduser()
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULTS: dict[str, Any] = {
    "llm": {
        "connector": "ollama",
        "model": "qwen2.5:7b",
    },
    "vault": {
        "path": "~/Documents/study-vault",
    },
}


def load() -> dict[str, Any]:
    """Load config from ~/.study/config.toml, merging with defaults."""
    config = _deep_merge({}, DEFAULTS)
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "rb") as f:
            on_disk = tomllib.load(f)
        config = _deep_merge(config, on_disk)
    return config


def save(config: dict[str, Any]) -> None:
    """Save config dict to ~/.study/config.toml (manual TOML serialization)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = _dict_to_toml(config)
    CONFIG_FILE.write_text("\n".join(lines) + "\n")


def vault_path(config: dict[str, Any]) -> Path:
    return Path(config["vault"]["path"]).expanduser()


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _dict_to_toml(d: dict[str, Any], prefix: str = "") -> list[str]:
    """Minimal TOML serializer for simple nested dicts with string values."""
    lines: list[str] = []
    sections: list[tuple[str, dict]] = []

    for k, v in d.items():
        if isinstance(v, dict):
            sections.append((k, v))
        else:
            lines.append(f'{k} = {_toml_value(v)}')

    for section_key, section_val in sections:
        header = f"[{section_key}]" if not prefix else f"[{prefix}.{section_key}]"
        lines.append("")
        lines.append(header)
        for sk, sv in section_val.items():
            lines.append(f'{sk} = {_toml_value(sv)}')

    return lines


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(v)
    if isinstance(v, str):
        return f'"{v}"'
    raise ValueError(f"Unsupported TOML value type: {type(v)}")
