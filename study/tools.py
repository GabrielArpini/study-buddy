from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from study.models import Tool
import study.vault as vault_mod

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------


def _get_tool(tool_list: list[Tool], name: str) -> Tool:
    """Return the first Tool with the given name from tool_list.

    Raises KeyError if not found, so construction of derived tool lists
    fails loudly rather than silently skipping a tool.
    """
    for tool in tool_list:
        if tool.name == name:
            return tool
    raise KeyError(f"Tool '{name}' not found in provided list")


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
        name="append_synthesis",
        description=(
            "Capture the learner's explanation of a concept in their own words, "
            "optionally annotated with corrections or clarifications. "
            "Call this whenever the learner gives a substantive explanation — not just a brief acknowledgment. "
            "Use the learner's actual words, not a paraphrase."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic slug"},
                "concept": {
                    "type": "string",
                    "description": "Concept name (title case, e.g. 'Beam Search')",
                },
                "learner_text": {
                    "type": "string",
                    "description": "The learner's explanation in their own words (verbatim or very lightly edited for readability)",
                },
                "assistant_note": {
                    "type": "string",
                    "description": "Optional annotation: corrections, clarifications, or precision the learner missed. Be brief and specific.",
                },
            },
            "required": ["topic", "concept", "learner_text"],
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

PROJECT_TOOLS: list[Tool] = [
    Tool(
        name="record_moment",
        description=(
            "Append a narrative entry to the project Timeline. "
            "Call for every substantive update: what was done, discovered, built, or hit. "
            "Breakthrough and blocker entries are also written to their curated sections."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "moment_type": {
                    "type": "string",
                    "enum": ["progress", "breakthrough", "blocker", "struggle"],
                },
                "text": {
                    "type": "string",
                    "description": "The user's own words describing what happened",
                },
            },
            "required": ["topic", "moment_type", "text"],
        },
    ),
    Tool(
        name="resolve_blocker",
        description=(
            "Mark a previous blocker as resolved. "
            "Call when the user describes getting past something they were stuck on."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "blocker_text": {
                    "type": "string",
                    "description": "Partial text identifying the blocker entry",
                },
                "resolution": {
                    "type": "string",
                    "description": "How it was resolved, in the user's words",
                },
            },
            "required": ["topic", "blocker_text", "resolution"],
        },
    ),
    Tool(
        name="add_graph_node",
        description=(
            "Add a typed node to the project graph and optionally connect it to existing nodes. "
            "The tool returns the current node list — use the slugs shown there when setting "
            "resolves_slug or contributes_to_slug. "
            "Node types: milestone (something shipped/achieved), uncertainty (soft unknown), "
            "certainty (explicitly confirmed/tested), blocker (hard stop). "
            "Edge types: resolves (uncertainty/blocker → certainty), "
            "contributes (any → milestone)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "node_type": {
                    "type": "string",
                    "enum": ["milestone", "uncertainty", "certainty", "blocker"],
                },
                "text": {
                    "type": "string",
                    "description": "One sentence describing this moment",
                },
                "resolves_slug": {
                    "type": "string",
                    "description": "Slug of the uncertainty/blocker node this resolves (optional)",
                },
                "contributes_to_slug": {
                    "type": "string",
                    "description": "Slug of the milestone node this contributes to (optional)",
                },
            },
            "required": ["topic", "node_type", "text"],
        },
    ),
    Tool(
        name="update_goal",
        description="Set or update the project's top-level goal. Not a decision.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "goal": {"type": "string"},
            },
            "required": ["topic", "goal"],
        },
    ),
    Tool(
        name="record_decision",
        description=(
            "Capture a concrete mutually-exclusive choice. "
            "Not for goal statements or general intent."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "component": {"type": "string"},
                "decision": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["topic", "component", "decision"],
        },
    ),
    _get_tool(TOOLS, "add_source"),
    _get_tool(TOOLS, "append_session_log"),
    _get_tool(TOOLS, "update_profile"),
    _get_tool(TOOLS, "read_note"),
    _get_tool(TOOLS, "list_topics"),
    _get_tool(TOOLS, "link_to_topic"),
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

class ToolExecutor:
    def __init__(self, vault: Path, topic: str = "", topic_type: str = "concept") -> None:
        self.vault = vault
        self.topic = topic
        self.topic_type = topic_type
        self.stats: dict = {
            "concepts_added": 0,
            "understanding_updates": [],   # list of (concept, level)
            "sources_added": 0,
            "subtopics_created": [],       # list of full subtopic names
            "moments_recorded": 0,         # project mode
            "breakthroughs": [],           # project mode
            "blockers_logged": [],         # project mode
            "graph_nodes_added": 0,        # project mode
        }

    def _normalize_topic_arg(self, arguments: dict) -> tuple[dict, str]:
        if "topic" not in arguments:
            fixed = dict(arguments)
            fixed["topic"] = self.topic
            return fixed, f"[auto-added topic='{self.topic}']"
        given = arguments["topic"]
        if given == self.topic or given.startswith(self.topic + "/"):
            return arguments, ""
        fixed = dict(arguments)
        fixed["topic"] = self.topic
        return fixed, f"[auto-corrected topic '{given}' → '{self.topic}']"

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        arguments, topic_warning = self._normalize_topic_arg(arguments)
        method = getattr(self, f"_tool_{name}", None)
        if method is None:
            return f"Error: unknown tool '{name}'"
        try:
            result = method(**arguments)
            result = result if isinstance(result, str) else "OK"
            return (topic_warning + "\n" + result).strip() if topic_warning else result
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

    def _tool_append_synthesis(
        self,
        topic: str,
        concept: str,
        learner_text: str,
        assistant_note: str = "",
    ) -> str:
        existing = vault_mod.get_synthesis_entry(self.vault, topic, concept)
        if existing:
            return (
                f"A synthesis entry for '{concept}' already exists:\n\n{existing}\n\n"
                "Revise it to incorporate the new explanation. Call append_synthesis again "
                "with the merged learner_text (and updated assistant_note if needed). "
                "Preserve the learner's own voice. Only call once more — do not loop."
            )
        vault_mod.append_synthesis(self.vault, topic, concept, learner_text, assistant_note)
        self.stats["synthesis"] = self.stats.get("synthesis", 0) + 1
        current = vault_mod.get_section(
            vault_mod.topic_path(self.vault, topic).read_text(), "My Synthesis"
        )
        return f"Synthesis entry added for '{concept}'.\n\nCurrent My Synthesis:\n{current}"

    def _tool_update_profile(self, content: str) -> str:
        vault_mod.update_profile(self.vault, content)
        return "Learner profile updated."

    def _auto_link_topics(self, text: str, from_topic: str) -> str:
        """
        Scan text for mentions of existing vault topics. For each match:
        - Auto-record a cross-topic link in the vault
        - Return the user's prior understanding of that topic for model context
        Returns an empty string if no topics were mentioned.
        """
        all_topics = vault_mod.list_topics(self.vault)
        results = []
        for slug in all_topics:
            if slug == from_topic:
                continue
            phrase = slug.replace("-", " ").replace("_", " ")
            if phrase in text.lower():
                concept = phrase.title()
                vault_mod.link_to_topic(self.vault, concept, from_topic, slug)
                note = vault_mod.read_note(self.vault, slug)
                understanding = vault_mod.get_section(note, "Understanding")
                synthesis = vault_mod.get_section(note, "My Synthesis")
                prior = "\n\n".join(s for s in [understanding, synthesis] if s.strip())
                results.append(
                    f"Auto-linked [[{slug}]] (concept: {concept}).\n"
                    f"User's prior notes on this topic:\n{prior if prior else '(no notes yet)'}"
                )
        return "\n\n---\n\n".join(results)

    def _tool_update_goal(self, topic: str, goal: str) -> str:
        path = vault_mod.ensure_topic(self.vault, topic)
        vault_mod.update_section(path, "Goal", goal)
        return "Project goal updated."

    def _tool_record_decision(self, topic: str, component: str, decision: str, rationale: str = "") -> str:
        vault_mod.record_decision(self.vault, topic, component, decision, rationale)
        return f"Decision recorded: {component} → {decision}."

    def _tool_record_moment(self, topic: str, moment_type: str, text: str) -> str:
        """Dispatch record_moment vault op and update session stats."""
        vault_mod.record_moment(self.vault, topic, moment_type, text)
        self.stats["moments_recorded"] += 1
        if moment_type == "breakthrough":
            self.stats["breakthroughs"].append(text[:60])
        elif moment_type == "blocker":
            self.stats["blockers_logged"].append(text[:60])
        return f"Moment recorded ({moment_type})."

    def _tool_resolve_blocker(self, topic: str, blocker_text: str, resolution: str) -> str:
        """Dispatch resolve_blocker vault op."""
        found = vault_mod.resolve_blocker(self.vault, topic, blocker_text, resolution)
        if found:
            return f"Blocker resolved: '{blocker_text[:40]}'."
        return f"No matching blocker found for '{blocker_text[:40]}'."

    def _tool_add_graph_node(
        self,
        topic: str,
        node_type: str,
        text: str,
        resolves_slug: str = "",
        contributes_to_slug: str = "",
    ) -> str:
        """Dispatch add_graph_node vault op and update stats."""
        result = vault_mod.add_graph_node(
            self.vault,
            topic,
            node_type,
            text,
            resolves_slug=resolves_slug,
            contributes_to_slug=contributes_to_slug,
        )
        self.stats["graph_nodes_added"] += 1
        return result

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
