from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

import study.vault as vault_mod
from study.connectors.base import LLMConnector
from study.git_ops import commit_session
from study.models import Message, Tool
from study.renderer import extract_pdf_text, handle_command, render_graph_snapshot
from study.tools import TOOLS, ToolExecutor

console = Console()

MAX_TOOL_ROUNDS = 10

SYSTEM_PROMPT_TEMPLATE = """\
{framework}

---

## Learner Profile
{profile}

---

## Current Topic: {topic}

{topic_note}

---

## Existing Subtopics of {topic}

{existing_subtopics}

Do NOT call `suggest_subtopic` for any name already listed above.

---

## Behavior Rules

- You are a Socratic study partner, NOT a lecturer.
- Ask at most 5 questions per response. Start easy, progress to harder.
- NEVER give away answers unprompted. Guide the learner to discover them.
- Use wikilinks [[like this]] for concepts. Use [[other-topic]] for cross-topic links.
- After each exchange, decide if you need to call tools to update the vault.
- Call `update_understanding` when the learner demonstrates or fails to demonstrate mastery.
- Call `append_session_log` at the end of the session with a brief summary.
- Do NOT invent sources. Only call `add_source` when the learner explicitly names a specific source they have used (a book title, paper, course name). NEVER add URLs or web links — you cannot verify they exist.
- Do NOT generate URLs, hyperlinks, or web addresses of any kind in your responses. If a resource exists, name it (e.g. "the Wikipedia article on X") without linking it.
- If you called `add_source` for something that turns out to be wrong or the learner didn't ask for it, call `remove_source` immediately to undo it.
- Stay scoped to the current topic unless the learner explicitly connects to another.
- When the learner clearly shifts focus to a distinct sub-area (a specific project, algorithm, or theorem), call `suggest_subtopic` once. Do not call it for every new concept — only when the sub-area is substantial enough to warrant its own note.

## Understanding Level Definitions

- **Solid**: Learner can explain the concept clearly in their own words, apply it, and spot edge cases.
- **Shaky**: Learner has partial understanding — knows the concept exists but can't fully explain or apply it.
- **Not Yet Engaged**: Concept has been introduced but learner hasn't demonstrated any engagement with it.
"""


class StudySession:
    def __init__(
        self,
        topic: str,
        vault: Path,
        connector: LLMConnector,
        tools: list[Tool] | None = None,
    ) -> None:
        self.topic = topic
        self.vault = vault
        self.connector = connector
        self.tools = tools or TOOLS
        self.executor = ToolExecutor(vault, topic)
        self._pending_pdf: str | None = None
        self.messages: list[Message] = []
        self.start_time = datetime.now()
        self.user_exchanges = 0
        self.user_word_count = 0
        self._build_system_prompt()

    def _build_system_prompt(self) -> None:
        framework = ""
        fw_path = vault_mod.framework_path(self.vault)
        if fw_path.exists():
            framework = fw_path.read_text()

        profile = vault_mod.read_profile(self.vault)

        vault_mod.ensure_topic(self.vault, self.topic)
        topic_note = vault_mod.read_note(self.vault, self.topic)

        all_topics = vault_mod.list_topics(self.vault)
        prefix = self.topic + "/"
        existing_subtopics = [t for t in all_topics if t.startswith(prefix)]

        system_content = SYSTEM_PROMPT_TEMPLATE.format(
            framework=framework,
            profile=profile or "(no profile yet)",
            topic=self.topic,
            topic_note=topic_note,
            existing_subtopics=(
                "\n".join(f"- {s}" for s in existing_subtopics)
                if existing_subtopics else "(none)"
            ),
        )
        self.messages = [Message(role="system", content=system_content)]

    def boot(self) -> str | None:
        """Display the graph snapshot panel. If prior sessions exist, return LLM recap text."""
        render_graph_snapshot(self.vault, self.topic)

        path = vault_mod.topic_path(self.vault, self.topic)
        if not path.exists():
            return None
        content = path.read_text()
        has_prior_data = any(
            vault_mod.get_section(content, s).strip()
            for s in (
                "Session Log",
                "Core Concepts",
                "Understanding/Solid",
                "Understanding/Shaky",
            )
        )
        if not has_prior_data:
            return None

        self.messages.append(Message(
            role="user",
            content="Briefly recap where we left off and ask me one opening question to pick up from there.",
        ))
        return self._run_tool_loop()

    def send(self, text: str) -> str | None:
        """
        Process user input. Returns None for ! commands handled locally.
        Returns the assistant reply text for normal messages.
        """
        # Handle ! commands
        if text.startswith("!"):
            parts = text.strip().split(None, 1)
            cmd = parts[0].lstrip("!").lower()
            if cmd == "add":
                pdf_path = parts[1] if len(parts) > 1 else ""
                pdf_text = extract_pdf_text(pdf_path)
                if pdf_text.startswith("Error"):
                    console.print(f"[red]{pdf_text}[/red]")
                else:
                    self._pending_pdf = pdf_text
                    console.print(f"[green]PDF loaded ({len(pdf_text)} chars). Include it in your next message.[/green]")
                return None
            else:
                handle_command(text, self.vault, self.topic)
                return None

        # Build user message (inject PDF context if any)
        user_content = text
        if self._pending_pdf:
            user_content = f"[PDF Context]\n{self._pending_pdf}\n\n---\n\n{text}"
            self._pending_pdf = None
            console.print("[dim]  (PDF context attached)[/dim]")

        self.messages.append(Message(role="user", content=user_content))
        self.user_exchanges += 1
        self.user_word_count += len(text.split())
        reply = self._run_tool_loop()
        return reply

    def _run_tool_loop(self) -> str:
        """Agentic loop: call LLM, execute tool calls, loop until stop."""
        last_text = ""
        for _round in range(MAX_TOOL_ROUNDS):
            with console.status("[dim]thinking...[/dim]", spinner="dots"):
                response = self.connector.complete(self.messages, tools=self.tools)
            self.messages.append(response.message)

            if response.message.content:
                last_text = response.message.content

            if response.stop_reason == "stop" or not response.message.tool_calls:
                break

            # Execute tool calls and collect results
            for tc in response.message.tool_calls:
                console.print(f"[dim]  tool: {tc.name}({_fmt_args(tc.arguments)})[/dim]")
                result = self.executor.execute(tc.name, tc.arguments)
                self.messages.append(Message(
                    role="tool",
                    content=result,
                    tool_call_id=tc.id,
                    name=tc.name,
                ))

        return last_text

    def get_summary(self) -> dict:
        elapsed = datetime.now() - self.start_time
        minutes, seconds = divmod(int(elapsed.total_seconds()), 60)
        return {
            "topic": self.topic,
            "duration": f"{minutes}m {seconds}s",
            "exchanges": self.user_exchanges,
            "words": self.user_word_count,
            "stats": self.executor.stats,
        }

    def end_session(self) -> None:
        """Finalize: append daily log, commit vault changes."""
        summary = _extract_session_summary(self.messages)
        vault_mod.append_daily_log(self.vault, self.topic, summary)
        committed = commit_session(self.vault, self.topic)
        if committed:
            console.print("[dim]Vault changes committed to git.[/dim]")


def _fmt_args(args: dict[str, Any]) -> str:
    """Format tool arguments for display (truncated)."""
    parts = []
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 40:
            sv = sv[:37] + "..."
        parts.append(f"{k}={sv!r}")
    return ", ".join(parts)


def _extract_session_summary(messages: list[Message]) -> str:
    """Build a short summary from the conversation for the daily log."""
    user_msgs = [m.content for m in messages if m.role == "user" and m.content]
    if not user_msgs:
        return "Session with no user messages."
    count = len(user_msgs)
    first = user_msgs[0][:80].replace("\n", " ")
    return f"{count} exchange(s). Started with: {first!r}"
