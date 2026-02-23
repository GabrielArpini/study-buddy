from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Vault layout helpers
# ---------------------------------------------------------------------------

def topic_path(vault: Path, topic: str) -> Path:
    return vault / "topics" / f"{topic}.md"


def daily_path(vault: Path, day: date | None = None) -> Path:
    d = day or date.today()
    return vault / "_daily" / f"{d.isoformat()}.md"


def framework_path(vault: Path) -> Path:
    return vault / "_framework.md"


def profile_path(vault: Path) -> Path:
    return vault / "_profile.md"


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def _split_frontmatter(content: str) -> tuple[str, str]:
    """Return (frontmatter_str, body_str). frontmatter_str excludes --- delimiters."""
    if not content.startswith("---"):
        return "", content
    end = content.find("\n---", 3)
    if end == -1:
        return "", content
    fm = content[3:end].strip()
    body = content[end + 4:].lstrip("\n")
    return fm, body


def _join_frontmatter(fm_str: str, body: str) -> str:
    if not fm_str:
        return body
    return f"---\n{fm_str}\n---\n{body}"


def _parse_frontmatter(content: str) -> dict[str, Any]:
    fm_str, _ = _split_frontmatter(content)
    if not fm_str:
        return {}
    return yaml.safe_load(fm_str) or {}


def _set_frontmatter(content: str, key: str, value: Any) -> str:
    fm_str, body = _split_frontmatter(content)
    fm: dict[str, Any] = yaml.safe_load(fm_str) or {} if fm_str else {}
    fm[key] = value
    new_fm = yaml.dump(fm, default_flow_style=False).rstrip()
    return _join_frontmatter(new_fm, body)


# ---------------------------------------------------------------------------
# Section access
# ---------------------------------------------------------------------------

def get_section(content: str, section_path: str) -> str:
    """
    Return the text content of a section identified by section_path.
    section_path can be "Core Concepts" or "Understanding/Solid".
    Returns empty string if not found.
    """
    parts = [p.strip() for p in section_path.split("/")]
    depth = len(parts)
    heading_level = depth + 1  # e.g. depth=1 → ## heading

    # Build a pattern to find the heading
    target_heading = "#" * heading_level + " " + parts[-1]

    # For nested paths, verify parent headings exist first
    if depth > 1:
        parent_section = "/".join(parts[:-1])
        parent_content = get_section(content, parent_section)
        if not parent_content:
            return ""
        search_in = parent_content
    else:
        _, search_in = _split_frontmatter(content)

    lines = search_in.splitlines(keepends=True)
    start_idx = None
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if stripped == target_heading:
            start_idx = i + 1
            break

    if start_idx is None:
        return ""

    # Collect lines until next heading at same or higher (lower-number) level
    end_idx = len(lines)
    stop_pattern = re.compile(r"^#{1," + str(heading_level) + r"} ")
    for i in range(start_idx, len(lines)):
        if stop_pattern.match(lines[i]):
            end_idx = i
            break

    return "".join(lines[start_idx:end_idx]).strip()


def update_section(file_path: Path, section_path: str, new_content: str) -> None:
    """
    Replace the body of a section in the file at file_path.
    Creates the section if it doesn't exist (appended at end of file).
    """
    content = file_path.read_text()
    parts = [p.strip() for p in section_path.split("/")]
    depth = len(parts)
    heading_level = depth + 1
    target_heading = "#" * heading_level + " " + parts[-1]

    _, body = _split_frontmatter(content)
    fm_str, _ = _split_frontmatter(content)

    lines = body.splitlines(keepends=True)
    start_idx = None
    for i, line in enumerate(lines):
        if line.rstrip("\n") == target_heading:
            start_idx = i
            break

    stop_pattern = re.compile(r"^#{1," + str(heading_level) + r"} ")
    if start_idx is not None:
        # Find end of this section
        end_idx = len(lines)
        for i in range(start_idx + 1, len(lines)):
            if stop_pattern.match(lines[i]):
                end_idx = i
                break

        new_section_lines = [target_heading + "\n"]
        if new_content.strip():
            new_section_lines.append(new_content.rstrip() + "\n")
        new_section_lines.append("\n")

        new_body_lines = lines[:start_idx] + new_section_lines + lines[end_idx:]
        new_body = "".join(new_body_lines)
    else:
        # Append section at end
        new_body = body.rstrip() + f"\n\n{target_heading}\n"
        if new_content.strip():
            new_body += new_content.rstrip() + "\n"

    new_content_full = _join_frontmatter(fm_str, new_body)
    file_path.write_text(new_content_full)
    _touch_last_session(file_path)


# ---------------------------------------------------------------------------
# Topic management
# ---------------------------------------------------------------------------

TOPIC_TEMPLATE = """\
---
topic: {topic}
created: {today}
last_session: {today}
---
## Sources

## Core Concepts

## Understanding

### Solid

### Shaky

### Not Yet Engaged

## My Synthesis

## Session Log
"""


def ensure_topic(vault: Path, topic: str) -> Path:
    """Create topic note from template if it doesn't exist. Return path."""
    path = topic_path(vault, topic)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        today = date.today().isoformat()
        path.write_text(TOPIC_TEMPLATE.format(topic=topic, today=today))
    return path


def list_topics(vault: Path) -> list[str]:
    topics_dir = vault / "topics"
    if not topics_dir.exists():
        return []
    return sorted(
        str(p.relative_to(topics_dir).with_suffix(""))
        for p in topics_dir.rglob("*.md")
    )


def read_note(vault: Path, topic: str) -> str:
    path = topic_path(vault, topic)
    if not path.exists():
        return f"Note for topic '{topic}' does not exist."
    return path.read_text()


def _touch_last_session(file_path: Path) -> None:
    if not file_path.exists():
        return
    content = file_path.read_text()
    today = date.today().isoformat()
    updated = _set_frontmatter(content, "last_session", today)
    file_path.write_text(updated)


def get_last_session(vault: Path, topic: str) -> str | None:
    path = topic_path(vault, topic)
    if not path.exists():
        return None
    fm = _parse_frontmatter(path.read_text())
    return str(fm.get("last_session", "")) or None


# ---------------------------------------------------------------------------
# Understanding level manipulation
# ---------------------------------------------------------------------------

UNDERSTANDING_LEVELS = ["Solid", "Shaky", "Not Yet Engaged"]


def update_understanding(vault: Path, topic: str, level: str, concept: str, notes: str) -> None:
    """Move concept to the given understanding level, removing from others."""
    path = ensure_topic(vault, topic)

    for lvl in UNDERSTANDING_LEVELS:
        content = path.read_text()
        section_content = get_section(content, f"Understanding/{lvl}")
        lines = [l for l in section_content.splitlines() if l.strip()]
        # Remove concept if present (match bullet or bare)
        new_lines = [l for l in lines if not _concept_in_line(concept, l)]
        update_section(path, f"Understanding/{lvl}", "\n".join(new_lines))

    # Now add to target level
    content = path.read_text()
    section_content = get_section(content, f"Understanding/{level}")
    lines = [l for l in section_content.splitlines() if l.strip()]
    entry = f"- [[{concept}]]"
    if notes:
        entry += f" — {notes}"
    lines.append(entry)
    update_section(path, f"Understanding/{level}", "\n".join(lines))


def _concept_in_line(concept: str, line: str) -> bool:
    lc = line.lower()
    return concept.lower() in lc


# ---------------------------------------------------------------------------
# Concept and source management
# ---------------------------------------------------------------------------

def add_concept(vault: Path, topic: str, concept: str, links: list[str]) -> None:
    path = ensure_topic(vault, topic)
    content = path.read_text()
    section_content = get_section(content, "Core Concepts")
    lines = [l for l in section_content.splitlines() if l.strip()]

    entry = f"- [[{concept}]]"
    if links:
        linked = ", ".join(f"[[{l}]]" for l in links)
        entry += f" → {linked}"

    if entry not in lines:
        lines.append(entry)
        update_section(path, "Core Concepts", "\n".join(lines))


def add_source(vault: Path, topic: str, source: str) -> None:
    path = ensure_topic(vault, topic)
    content = path.read_text()
    section_content = get_section(content, "Sources")
    lines = [l for l in section_content.splitlines() if l.strip()]
    entry = f"- {source}"
    if entry not in lines:
        lines.append(entry)
        update_section(path, "Sources", "\n".join(lines))


def remove_source(vault: Path, topic: str, source: str) -> bool:
    """Remove a source entry from the Sources section. Returns True if found and removed."""
    path = topic_path(vault, topic)
    if not path.exists():
        return False
    content = path.read_text()
    section_content = get_section(content, "Sources")
    lines = [l for l in section_content.splitlines() if l.strip()]
    new_lines = [l for l in lines if source.lower() not in l.lower()]
    if len(new_lines) == len(lines):
        return False
    update_section(path, "Sources", "\n".join(new_lines))
    return True


def link_to_topic(vault: Path, concept: str, from_topic: str, to_topic: str) -> None:
    path = ensure_topic(vault, from_topic)
    content = path.read_text()
    section_content = get_section(content, "Core Concepts")
    lines = [l for l in section_content.splitlines() if l.strip()]

    entry = f"- [[{concept}]] → [[{to_topic}]]"
    if entry not in lines:
        lines.append(entry)
        update_section(path, "Core Concepts", "\n".join(lines))


def append_session_log(vault: Path, topic: str, entry: str) -> None:
    path = ensure_topic(vault, topic)
    content = path.read_text()
    section_content = get_section(content, "Session Log")
    today = date.today().isoformat()
    new_entry = f"### {today}\n{entry}"
    new_content = (section_content.rstrip() + "\n\n" + new_entry).lstrip()
    update_section(path, "Session Log", new_content)


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

def read_profile(vault: Path) -> str:
    p = profile_path(vault)
    if not p.exists():
        return ""
    return p.read_text()


def update_profile(vault: Path, content: str) -> None:
    p = profile_path(vault)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


# ---------------------------------------------------------------------------
# Wikilink extraction
# ---------------------------------------------------------------------------

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]")


def get_all_wikilinks(vault: Path, topic: str) -> dict[str, list[str]]:
    """Return {'concepts': [...], 'cross_topic': [...]}"""
    path = topic_path(vault, topic)
    if not path.exists():
        return {"concepts": [], "cross_topic": []}
    content = path.read_text()
    all_topics = set(list_topics(vault))
    concepts = []
    cross_topic = []
    for match in WIKILINK_RE.finditer(content):
        target = match.group(1).strip()
        if target in all_topics and target != topic:
            cross_topic.append(target)
        elif target != topic:
            concepts.append(target)
    return {"concepts": list(dict.fromkeys(concepts)), "cross_topic": list(dict.fromkeys(cross_topic))}


# ---------------------------------------------------------------------------
# Daily log
# ---------------------------------------------------------------------------

def append_daily_log(vault: Path, topic: str, summary: str) -> None:
    path = daily_path(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        today = date.today().isoformat()
        path.write_text(f"# Study Log — {today}\n\n")
    existing = path.read_text()
    entry = f"- **{topic}**: {summary}\n"
    path.write_text(existing.rstrip() + "\n" + entry)


# ---------------------------------------------------------------------------
# Vault init
# ---------------------------------------------------------------------------

def ensure_vault_structure(vault: Path) -> None:
    """Create vault directories and template files if not present."""
    (vault / "topics").mkdir(parents=True, exist_ok=True)
    (vault / "_daily").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Vault reset helpers
# ---------------------------------------------------------------------------

def reset_topic(vault: Path, topic: str) -> None:
    """Overwrite a topic file with a blank template, preserving frontmatter dates."""
    path = topic_path(vault, topic)
    today = date.today().isoformat()
    created = today
    if path.exists():
        fm = _parse_frontmatter(path.read_text())
        created = str(fm.get("created", today))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TOPIC_TEMPLATE.format(topic=topic, today=today).replace(
        f"created: {today}", f"created: {created}"
    ))


def reset_all_topics(vault: Path) -> int:
    """Delete all topic files. Returns count of files removed."""
    topics_dir = vault / "topics"
    if not topics_dir.exists():
        return 0
    files = list(topics_dir.rglob("*.md"))
    for f in files:
        f.unlink()
    return len(files)


def reset_daily_logs(vault: Path) -> int:
    """Delete all daily log files. Returns count of files removed."""
    daily_dir = vault / "_daily"
    if not daily_dir.exists():
        return 0
    files = list(daily_dir.glob("*.md"))
    for f in files:
        f.unlink()
    return len(files)


def reset_profile(vault: Path) -> None:
    """Reset _profile.md to the blank template (caller supplies template text)."""
    p = profile_path(vault)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Reset to minimal blank state; the full template is owned by cli.py
    p.write_text(
        "# Learner Profile\n\n"
        "*This file is updated by the model as it learns about you.*\n\n"
        "## Background\n\n(unknown — will be filled in as we talk)\n\n"
        "## Learning Preferences\n\n(unknown)\n\n"
        "## Metacognitive Notes\n\n(unknown)\n"
    )
