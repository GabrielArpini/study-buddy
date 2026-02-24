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
        name="update_goal",
        description=(
            "Set or update the top-level goal of the project. Call this when the user "
            "describes what they are trying to build or achieve overall. "
            "This is NOT a decision — do not use record_decision for goal statements."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic slug"},
                "goal": {"type": "string", "description": "The project goal in the user's own words"},
            },
            "required": ["topic", "goal"],
        },
    ),
    Tool(
        name="record_decision",
        description=(
            "Capture a design or architecture decision in the user's own words. "
            "Call this whenever the user commits to a direction — even tentatively. "
            "The tool result includes existing decisions so you can detect conflicts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic slug"},
                "component": {"type": "string", "description": "System component or area this decision applies to"},
                "decision": {"type": "string", "description": "The decision in the user's own words"},
                "rationale": {"type": "string", "description": "Why this decision was made (optional)"},
            },
            "required": ["topic", "component", "decision"],
        },
    ),
    Tool(
        name="update_architecture",
        description=(
            "Upsert the description of a system component. Use this when the user "
            "describes how a part of their project works or is structured."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic slug"},
                "component": {"type": "string", "description": "Component name"},
                "description": {"type": "string", "description": "Description of the component"},
            },
            "required": ["topic", "component", "description"],
        },
    ),
    Tool(
        name="add_open_question",
        description=(
            "Log an unresolved question about the project. Use when the user raises "
            "something they haven't decided yet."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic slug"},
                "question": {"type": "string", "description": "The unresolved question"},
            },
            "required": ["topic", "question"],
        },
    ),
    Tool(
        name="resolve_open_question",
        description="Remove a question from Open Questions once the user answers it.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic slug"},
                "question": {"type": "string", "description": "The question to remove (partial match)"},
            },
            "required": ["topic", "question"],
        },
    ),
    Tool(
        name="add_tension",
        description=(
            "Log a detected conflict between the user's current thinking and a "
            "previous decision. Call this after surfacing the conflict to the user."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic slug"},
                "tension": {"type": "string", "description": "One-sentence description of the conflict"},
            },
            "required": ["topic", "tension"],
        },
    ),
    Tool(
        name="resolve_tension",
        description="Remove a tension that the user has resolved or reconciled.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic slug"},
                "tension": {"type": "string", "description": "The tension to remove (partial match)"},
            },
            "required": ["topic", "tension"],
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
        name="suggest_subtopic",
        description=(
            "Suggest creating a subtopic under the current topic. "
            "Call this when the user is clearly focusing on a distinct sub-area "
            "that deserves its own note."
        ),
        parameters={
            "type": "object",
            "properties": {
                "subtopic": {
                    "type": "string",
                    "description": "Suggested subtopic name in kebab-case",
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
        name="link_to_topic",
        description=(
            "Record a cross-topic link from this project to a concept topic in the vault. "
            "Call this when the user references a concept that has its own vault note."
        ),
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
        name="read_note",
        description=(
            "Read the full vault note for a topic. Use this to check what the user "
            "already understands about a concept they reference — so you can tailor "
            "your response to their existing knowledge."
        ),
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
        description="List all topic names in the vault. Use to check if a concept has an existing note before linking.",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
]


# ---------------------------------------------------------------------------
# Decision conflict helpers
# ---------------------------------------------------------------------------

def _parse_decision_blocks(decisions_text: str) -> list[dict]:
    """Parse the Decisions section into [{component, decision}, ...] dicts."""
    blocks: list[dict] = []
    lines = decisions_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("### ") and " — " in line:
            component = line.split(" — ", 1)[1].strip()
            # Next non-empty, non-metadata line is the decision text
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            decision_text = ""
            if j < len(lines) and not lines[j].startswith(("#", "**Why")):
                decision_text = lines[j].strip()
            blocks.append({"component": component, "decision": decision_text})
        i += 1
    return blocks


def _components_match(a: str, b: str) -> bool:
    """True if component names are the same or one is a substring of the other."""
    a, b = a.lower().strip(), b.lower().strip()
    return a == b or a in b or b in a


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
        link_info = self._auto_link_topics(goal, topic)
        if link_info:
            return f"Project goal updated.\n\n{link_info}"
        return "Project goal updated."

    def _tool_record_decision(self, topic: str, component: str, decision: str, rationale: str = "") -> str:
        existing = vault_mod.get_decisions(self.vault, topic)
        vault_mod.record_decision(self.vault, topic, component, decision, rationale)

        if not existing.strip():
            link_info = self._auto_link_topics(component + " " + decision + " " + rationale, topic)
            result = f"Recorded: {component} → {decision}. No prior decisions."
            return result + (f"\n\n{link_info}" if link_info else "")

        # Auto-detect same-component conflicts (Python-level, reliable)
        prior_blocks = _parse_decision_blocks(existing)
        same_component = [
            b for b in prior_blocks
            if _components_match(b["component"], component) and b["decision"]
        ]
        if same_component:
            for prior in same_component:
                tension = f"{component}: '{prior['decision']}' vs '{decision}'"
                vault_mod.add_tension(self.vault, topic, tension)
            prior_str = "; ".join(f"'{b['decision']}'" for b in same_component)
            link_info = self._auto_link_topics(component + " " + decision + " " + rationale, topic)
            result = (
                f"Recorded: {component} → {decision}.\n\n"
                f"CONFLICT DETECTED AND LOGGED: '{component}' was previously {prior_str}. "
                f"Tension has been written to the vault. "
                f"You MUST surface this to the user — quote the old decision and ask if this is a direction change."
            )
            return result + (f"\n\n{link_info}" if link_info else "")

        # No same-component conflict found — ask model to check cross-component semantics
        link_info = self._auto_link_topics(component + " " + decision + " " + rationale, topic)
        result = (
            f"Recorded: {component} → {decision}.\n\n"
            f"Prior decisions (check for cross-component conflicts — "
            f"call add_tension if '{decision}' cannot coexist with any of these):\n{existing}"
        )
        return result + (f"\n\n{link_info}" if link_info else "")

    def _tool_update_architecture(self, topic: str, component: str, description: str) -> str:
        vault_mod.update_architecture(self.vault, topic, component, description)
        link_info = self._auto_link_topics(component + " " + description, topic)
        if link_info:
            return f"Architecture updated: '{component}'.\n\n{link_info}"
        return f"Architecture updated: '{component}'."

    def _tool_add_open_question(self, topic: str, question: str) -> str:
        vault_mod.add_open_question(self.vault, topic, question)
        return "Open question logged."

    def _tool_resolve_open_question(self, topic: str, question: str) -> str:
        vault_mod.resolve_open_question(self.vault, topic, question)
        return "Open question resolved."

    def _tool_add_tension(self, topic: str, tension: str) -> str:
        vault_mod.add_tension(self.vault, topic, tension)
        return "Tension logged."

    def _tool_resolve_tension(self, topic: str, tension: str) -> str:
        vault_mod.resolve_tension(self.vault, topic, tension)
        return "Tension resolved."

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
