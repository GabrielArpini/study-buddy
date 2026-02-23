from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from study.models import Tool
import study.vault as vault_mod

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    Tool(
        name="read_note",
        description="Read the full markdown note for a topic from the vault.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic name (kebab-case)"},
            },
            "required": ["topic"],
        },
    ),
    Tool(
        name="list_topics",
        description="List all topic names stored in the vault.",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="update_section",
        description=(
            "Replace the content of a section in a topic note. "
            "Use section paths like 'Core Concepts' or 'My Synthesis'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "section": {"type": "string", "description": "Section path, e.g. 'Core Concepts'"},
                "content": {"type": "string", "description": "New markdown content for the section"},
            },
            "required": ["topic", "section", "content"],
        },
    ),
    Tool(
        name="add_concept",
        description="Add a concept wikilink to the Core Concepts section of a topic note.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "concept": {"type": "string", "description": "Concept noun phrase"},
                "links": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Related concept names to link to",
                },
            },
            "required": ["topic", "concept", "links"],
        },
    ),
    Tool(
        name="add_source",
        description="Add a source reference to the Sources section of a topic note.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "source": {"type": "string", "description": "Source description or URL"},
            },
            "required": ["topic", "source"],
        },
    ),
    Tool(
        name="update_understanding",
        description=(
            "Move a concept to a specific understanding level. "
            "Level must be 'Solid', 'Shaky', or 'Not Yet Engaged'. "
            "The concept is removed from all other levels automatically."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "level": {
                    "type": "string",
                    "enum": ["Solid", "Shaky", "Not Yet Engaged"],
                },
                "concept": {"type": "string"},
                "notes": {"type": "string", "description": "Brief explanation of current understanding"},
            },
            "required": ["topic", "level", "concept", "notes"],
        },
    ),
    Tool(
        name="remove_source",
        description=(
            "Remove a source entry from the Sources section of a topic note. "
            "Use this immediately if you added a source by mistake or without the learner asking."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "source": {"type": "string", "description": "The source text to remove (partial match is fine)"},
            },
            "required": ["topic", "source"],
        },
    ),
    Tool(
        name="link_to_topic",
        description="Record a cross-topic link: concept in from_topic connects to to_topic.",
        parameters={
            "type": "object",
            "properties": {
                "concept": {"type": "string"},
                "from_topic": {"type": "string"},
                "to_topic": {"type": "string"},
            },
            "required": ["concept", "from_topic", "to_topic"],
        },
    ),
    Tool(
        name="append_session_log",
        description="Append a dated entry to the Session Log section of a topic note.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "entry": {"type": "string", "description": "Session summary or key points"},
            },
            "required": ["topic", "entry"],
        },
    ),
    Tool(
        name="suggest_subtopic",
        description=(
            "Suggest creating a subtopic under the current topic. "
            "Call this when the learner is clearly focusing on a distinct sub-area "
            "that deserves its own note (e.g. a specific project, algorithm, or theorem). "
            "The user will confirm, decline, or rename before anything is created."
        ),
        parameters={
            "type": "object",
            "properties": {
                "subtopic": {
                    "type": "string",
                    "description": "Suggested subtopic name in kebab-case (e.g. 'mini-gpt')",
                },
                "reason": {
                    "type": "string",
                    "description": "One-line reason for suggesting this subtopic",
                },
            },
            "required": ["subtopic", "reason"],
        },
    ),
    Tool(
        name="update_profile",
        description=(
            "Overwrite the learner profile (_profile.md) with updated content. "
            "Use this to record learner preferences, background, or metacognitive notes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Full markdown content for _profile.md"},
            },
            "required": ["content"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

class ToolExecutor:
    def __init__(self, vault: Path, topic: str = "") -> None:
        self.vault = vault
        self.topic = topic
        self.stats: dict = {
            "concepts_added": 0,
            "understanding_updates": [],   # list of (concept, level)
            "sources_added": 0,
            "subtopics_created": [],       # list of full subtopic names
        }

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        method = getattr(self, f"_tool_{name}", None)
        if method is None:
            return f"Error: unknown tool '{name}'"
        try:
            result = method(**arguments)
            return result if isinstance(result, str) else "OK"
        except Exception as e:
            return f"Error executing {name}: {e}\n{traceback.format_exc()}"

    def _tool_read_note(self, topic: str) -> str:
        return vault_mod.read_note(self.vault, topic)

    def _tool_list_topics(self) -> str:
        topics = vault_mod.list_topics(self.vault)
        if not topics:
            return "No topics yet."
        return "\n".join(topics)

    def _tool_update_section(self, topic: str, section: str, content: str) -> str:
        path = vault_mod.ensure_topic(self.vault, topic)
        vault_mod.update_section(path, section, content)
        return f"Section '{section}' updated in '{topic}'."

    def _tool_add_concept(self, topic: str, concept: str, links: list[str]) -> str:
        vault_mod.add_concept(self.vault, topic, concept, links)
        self.stats["concepts_added"] += 1
        return f"Concept '[[{concept}]]' added to '{topic}'."

    def _tool_add_source(self, topic: str, source: str) -> str:
        vault_mod.add_source(self.vault, topic, source)
        self.stats["sources_added"] += 1
        return f"Source added to '{topic}'."

    def _tool_remove_source(self, topic: str, source: str) -> str:
        removed = vault_mod.remove_source(self.vault, topic, source)
        if removed:
            return f"Source '{source}' removed from '{topic}'."
        return f"Source '{source}' not found in '{topic}'."

    def _tool_update_understanding(self, topic: str, level: str, concept: str, notes: str) -> str:
        vault_mod.update_understanding(self.vault, topic, level, concept, notes)
        self.stats["understanding_updates"].append((concept, level))
        return f"'{concept}' moved to {level} in '{topic}'."

    def _tool_link_to_topic(self, concept: str, from_topic: str, to_topic: str) -> str:
        vault_mod.link_to_topic(self.vault, concept, from_topic, to_topic)
        return f"Cross-topic link: [[{concept}]] in {from_topic} → {to_topic}."

    def _tool_append_session_log(self, topic: str, entry: str) -> str:
        vault_mod.append_session_log(self.vault, topic, entry)
        return f"Session log updated for '{topic}'."

    def _tool_update_profile(self, content: str) -> str:
        vault_mod.update_profile(self.vault, content)
        return "Learner profile updated."

    def _tool_suggest_subtopic(self, subtopic: str, reason: str) -> str:
        import questionary
        from rich.console import Console
        from rich.markup import escape
        from rich.panel import Panel

        con = Console()
        con.print(Panel(
            f"[bold cyan]{escape(subtopic)}[/bold cyan]\n[dim]{escape(reason)}[/dim]",
            title="[bold yellow]create subtopic?[/bold yellow]",
            expand=False,
        ))

        choice = questionary.select(
            "Action:",
            choices=["yes", "no", "rename"],
        ).ask()

        if choice is None or choice == "no":
            return "User declined — subtopic not created."

        if choice == "rename":
            subtopic = questionary.text("New name:", default=subtopic).ask() or subtopic

        full = f"{self.topic}/{subtopic}" if self.topic else subtopic
        vault_mod.ensure_topic(self.vault, full)
        self.stats["subtopics_created"].append(full)
        return f"Subtopic '{full}' created. Use this name in subsequent tool calls."
