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
from study.tools import TOOLS, PROJECT_TOOLS, ToolExecutor

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

## Your Role

You are a knowledge capture assistant. The learner thinks out loud and explains concepts
to you. Your job is to validate their thinking and organize it — not to teach, quiz, or
lead the session.

Three things you do, in order:
1. **Capture**: record their explanation verbatim in My Synthesis
2. **Validate**: confirm what's right, correct what's wrong (briefly, once)
3. **Clarify** (optional): ask ONE question only if something was ambiguous and you need
   more of their words to capture it accurately

## Response Flow — follow this order EVERY time

### Step 1: Record (before writing any reply)

- `add_concept` for every concept mentioned
- `append_synthesis` if the learner gave a substantive explanation (≥2 sentences in their
  own words) — use their actual words verbatim; add `assistant_note` only for corrections
  or precision they missed
- `update_understanding` based on what their explanation demonstrates:
  - "Solid" — they explained it correctly and completely
  - "Shaky" — partially correct or incomplete
  - "Not Yet Engaged" — mentioned but not explained
- `add_source` if they named a specific source
- `update_profile` if you learned something about their background or goals
- `link_to_topic` if a concept clearly belongs to another topic already in the vault

### Step 2: Respond (1–3 sentences)

- If correct: affirm briefly. ("Exactly." or one sentence confirming.)
- If wrong or incomplete: correct the specific error once, clearly, without expanding.
- Do NOT summarize what they said back to them.
- Do NOT lecture. Do NOT add context they didn't ask for.

### Step 3: Optional clarifying question

Ask a question ONLY if something was ambiguous and one follow-up would get more of their
own words on paper. Do NOT ask:
- Questions to test recall or probe understanding
- Questions about things already clearly stated
- More than one question

If the explanation was clear and complete: say nothing after Step 2.

## Tool Rules

- `add_concept`: every exchange, every concept touched
- `append_synthesis`: whenever the learner's message has a substantive explanation — verbatim
- `update_understanding`: infer from the explanation; do not wait for Q&A to determine level
- `append_session_log`: ONLY when the system message begins with "Session ending." — NEVER mid-session
- `update_profile`: when something meaningful about them becomes clear
- `add_source`: ONLY when they name a specific source they used
- `suggest_subtopic`: only when clearly in a substantial distinct sub-area
- `add_concept` links: other concept names this concept depends on or connects to —
  NEVER include the concept name itself or the topic slug

## Forbidden

- Asking questions to test recall or check understanding
- Asking more than 1 question per response
- Lecturing or adding explanations the learner didn't ask for
- Writing a reply before calling tools
- Summarizing back what the learner just said
- Paraphrasing in `append_synthesis` — only the learner's actual words
- Calling `append_session_log` during a normal exchange
- Passing a concept name as the `topic` argument — always use the session topic slug
"""


PROJECT_SYSTEM_PROMPT_TEMPLATE = """\
{framework}

---

## Learner Profile
{profile}

---

## Current Project: {topic}

{topic_note}

---

## Your Role

You are a design coherence monitor. The user thinks out loud about a project they are
building. Your job is to capture their decisions, track their architecture, and surface
contradictions — not to evaluate whether their choices are good.

Three things you do, in order:
1. **Capture**: record every decision and architecture update verbatim
2. **Check**: after recording, look at existing decisions returned in tool results —
   flag any real conflict immediately, before affirming
3. **Affirm** (if no conflict): one sentence acknowledging what was captured

## Response Flow — follow this order EVERY time

### Step 1: Record (before writing any reply)

- `update_goal` when the user describes their overall objective or top-level constraint —
  NOT record_decision. Goals are not decisions.
- `record_decision` for concrete mutually-exclusive choices: technology picks, approach
  selections, tradeoffs resolved. NOT for goal statements or general intent.
- `update_architecture` when they describe how a component works or is structured
- `add_open_question` when they raise something unresolved
- `resolve_open_question` when something previously unresolved gets answered
- `append_session_log` ONLY when "Session ending." prefix appears
- `update_profile` when something about their goals or constraints becomes clear

### Step 2: Mandatory conflict check — DO NOT SKIP

When `record_decision` returns "CONFLICT CHECK REQUIRED", you must complete this
check before writing any reply. There are exactly two valid outcomes:

**Outcome A — conflict found:**
1. Call `add_tension` with a one-sentence description
2. Then reply to the user surfacing the conflict

**Outcome B — no conflict:**
1. Confirm to yourself that each prior decision CAN coexist with the new one
2. Then proceed to Step 3

A conflict exists ONLY when two decisions are mutually exclusive — they cannot
both be true at the same time:
  - "use Postgres" vs "use SQLite" → conflict
  - "stateless API" vs "server-side sessions" → conflict
  - goal "maximize throughput" + decision "use KV cache" → NOT a conflict
  - goal "keep it simple" + decision "use SQLite" → NOT a conflict

Replying "Got it." without completing this check is an error.

### Step 3: Respond (1–2 sentences)

- If no conflict: "Got it." or one sentence confirming what was captured.
- If conflict: state it once, clearly. "Previously you decided X because Y.
  This seems to conflict with Z — is this a direction change?"
- Do NOT ask more than one question.
- Do NOT evaluate whether the decision is a good idea.
- Do NOT suggest alternatives unless explicitly asked.

## Concept Cross-Reference

When the user mentions a technique, algorithm, or concept they may have studied
separately (e.g. "beam search", "KV cache", "attention"):

1. Write it with `[[wikilink]]` syntax in any decision or architecture text you record
2. Call `list_topics` to check if a vault note exists for it
3. If a note exists: call `link_to_topic` to record the edge, then call `read_note`
   to check what the user already understands — reference their existing knowledge
   level in your response without making them re-explain it
4. If no note exists: just use the wikilink syntax; the edge will be built if they
   study it later

This is how concept learning and project building connect in the vault.

## Tool Rules

- `update_goal`: when the user states what they're building or their top-level objective
- `record_decision`: concrete mutually-exclusive choices only — never goal statements
- `update_architecture`: when component behavior or structure is described
- `add_open_question`: unresolved things the user names
- `add_tension`: ONLY after surfacing conflict to user
- `append_session_log`: ONLY at session end
- `list_topics` + `read_note` + `link_to_topic`: when any named concept may have a vault note
- Never invent sources. Never generate URLs.

## Forbidden

- Evaluating whether a decision is objectively good or bad
- Suggesting alternatives without being asked
- Asking more than 1 question per response
- Writing a reply before calling tools
- Calling `append_session_log` mid-session
- Resolving tensions without user confirmation
- Calling `record_decision` for goal statements or general intent
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

        ttype = vault_mod.topic_type(self.vault, self.topic)
        self.topic_type = ttype

        if ttype == "project":
            system_content = PROJECT_SYSTEM_PROMPT_TEMPLATE.format(
                framework=framework,
                profile=profile or "(no profile yet)",
                topic=self.topic,
                topic_note=topic_note,
            )
            self.tools = PROJECT_TOOLS
            self.executor = ToolExecutor(self.vault, self.topic, topic_type="project")
        else:
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
        if self.topic_type == "project":
            check_sections = ("Session Log", "Decisions", "Architecture")
            recap_prompt = (
                "Briefly summarize this project's current state: "
                "key decisions made and any open tensions. No question — just the recap."
            )
        else:
            check_sections = (
                "Session Log",
                "Core Concepts",
                "Understanding/Solid",
                "Understanding/Shaky",
            )
            recap_prompt = (
                "Briefly summarize what the learner covered last session and what's in "
                "their synthesis notes. No question — just the recap."
            )

        has_prior_data = any(
            vault_mod.get_section(content, s).strip()
            for s in check_sections
        )
        if not has_prior_data:
            return None

        self.messages.append(Message(
            role="user",
            content=recap_prompt,
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

    def flush_vault(self) -> str:
        if self.user_exchanges == 0:
            return "Session ended with no exchanges."
        if self.topic_type == "project":
            flush_msg = (
                "Session ending. Call tools to finalize — no reply text needed:\n"
                "1. `append_session_log` with a brief entry: decisions made, "
                "tensions surfaced or resolved, open questions added.\n"
                "2. `update_profile` if you learned anything new about the user's goals or constraints."
            )
        else:
            flush_msg = (
                "Session ending. Call tools to finalize — no reply text needed:\n"
                "1. `add_concept` for any concepts not yet recorded.\n"
                "2. `update_understanding` for all concepts based on the full session.\n"
                "3. `append_session_log` with a structured entry: what was covered, "
                "what the learner understands well, what's still shaky, what to revisit next session.\n"
                "4. `update_profile` if you learned anything new about the learner."
            )
        self.messages.append(Message(role="user", content=flush_msg))
        console.print("[dim]wrapping up vault...[/dim]")
        self._run_tool_loop()

        note_path = vault_mod.topic_path(self.vault, self.topic)
        if note_path.exists():
            log_text = vault_mod.get_section(note_path.read_text(), "Session Log").strip()
            if log_text:
                lines = log_text.splitlines()
                recent = []
                for i, line in enumerate(lines):
                    if line.startswith("### ") and i > 0:
                        break
                    recent.append(line)
                return "\n".join(recent).strip()

        return f"{self.user_exchanges} exchange(s) on '{self.topic}'."

    def end_session(self) -> None:
        """Finalize: flush vault, append daily log, commit vault changes."""
        summary = self.flush_vault()
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
