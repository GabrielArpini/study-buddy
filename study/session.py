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

## Current Project Journal: {topic}

{topic_note}

---

## Your Role

You are a project journal scribe. The user thinks out loud as they build something.
Capture everything in vault entries. Do not guide, evaluate, or teach.

## Response Flow — follow this order EVERY time

### Step 1: Record (before writing any reply)

- `record_moment` for every substantive update — use the [moment-type: X] hint in the message
- `add_graph_node` when the moment is significant enough to be a graph node (see rules below)
- `update_goal` when they describe what they are building overall
- `record_decision` for concrete mutually-exclusive choices only
- `add_source` only when they name a specific resource
- `resolve_blocker` when something they were stuck on is now resolved
- `link_to_topic` + `read_note` when they mention a concept with a vault note
- `append_session_log` ONLY when "Session ending." prefix appears
- `update_profile` when meaningful context about them becomes clear

### Step 2: Acknowledge

One sentence. "Got it." or a brief confirmation of the key thing captured.
No summaries. No opinions. No evaluations.

### Step 3: Optional probe

Ask ONE question ONLY when the user is visibly uncertain about their next step.
Signs: "I'm not sure how to...", "I guess I'll...", "I need to figure out...", "I don't know if..."
If they're in flow (clear plan, confident language): Step 2 only.
Never two questions in consecutive responses.
Questions must be meta and domain-agnostic — about intent, not the technical domain.

## Graph Node Rules

Create a graph node (`add_graph_node`) when the moment is a distinct, self-contained event:
- **milestone**: user explicitly says something is working, shipped, or done
- **uncertainty**: a specific thing they don't know yet — must be a concrete question, not vague
- **certainty**: explicitly confirmed/tested/fixed — requires words like "confirmed", "tested",
  "it works", "fixed", "found that", "verified". If they say "I think" or "I believe" → NOT certainty.
- **blocker**: a hard stop, not just uncertainty — they cannot proceed without resolving this

Do NOT create a node for every sentence. Most `record_moment` calls do NOT need a graph node.
Create a node only when the moment is significant enough to be a landmark in the project story.

When connecting nodes, use the slugs shown in the `add_graph_node` tool result.
Edge rules: resolves (uncertainty/blocker → certainty), contributes (any → milestone).

## Forbidden

- Questioning a confident plan or decision
- Asking more than 1 question per response
- Two questions in consecutive responses
- Lecturing or adding unrequested context
- Evaluating whether a choice is good or bad
- Writing a reply before calling tools
- Calling `append_session_log` mid-session
- Creating certainty nodes from "I think" / "I believe" / hypothetical statements
"""


class StudySession:
    _CLASSIFY_PROMPT = """\
Classify the following message into ONE of these categories based on what the speaker expresses:
- certainty: something explicitly confirmed, tested, verified, or fixed
- uncertainty: something the speaker is unsure about or doesn't know yet
- blocker: something preventing progress, a hard stop
- milestone: something accomplished, shipped, or working
- progress: normal forward movement, no special state
- none: not a development update (question, meta-comment, etc.)

Respond with ONLY the category word, nothing else.\
"""

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
            check_sections = ("Session Log", "Timeline", "Breakthroughs")
            recap_prompt = (
                "Briefly summarize this project journal's recent activity: "
                "what was worked on last session, any breakthroughs or blockers noted. "
                "No question — just the recap."
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
            elif cmd == "recall":
                recall_query = parts[1] if len(parts) > 1 else ""
                if not recall_query:
                    console.print("[red]Usage: !recall <query>[/red]")
                    return None
                return self._run_recall(recall_query)
            else:
                handle_command(text, self.vault, self.topic)
                return None

        # Build user message (inject PDF context if any)
        user_content = text
        if self._pending_pdf:
            user_content = f"[PDF Context]\n{self._pending_pdf}\n\n---\n\n{text}"
            self._pending_pdf = None
            console.print("[dim]  (PDF context attached)[/dim]")

        # Pre-classify for project mode to guide graph node creation
        if self.topic_type == "project":
            moment_hint = self._classify_moment(text)
            if moment_hint != "none":
                user_content += f"\n\n[moment-type: {moment_hint}]"

        self.messages.append(Message(role="user", content=user_content))
        self.user_exchanges += 1
        self.user_word_count += len(text.split())
        return self._run_tool_loop()

    def _classify_moment(self, user_text: str) -> str:
        """Run a focused LLM call to classify the moment type in user_text.

        Returns one of: certainty | uncertainty | blocker | milestone | progress | none.
        Falls back to 'none' on any error so the main loop always proceeds.
        """
        classify_messages = [
            Message(role="system", content=self._CLASSIFY_PROMPT),
            Message(role="user", content=user_text),
        ]
        try:
            response = self.connector.complete(classify_messages, tools=None)
            classification = (response.message.content or "none").strip().lower()
            valid = {"certainty", "uncertainty", "blocker", "milestone", "progress", "none"}
            return classification if classification in valid else "none"
        except Exception:
            return "none"

    def _run_recall(self, query: str) -> str:
        """Answer a recall query against the topic note without modifying session history."""
        topic_note = vault_mod.read_note(self.vault, self.topic)
        recall_messages = [
            Message(
                role="system",
                content=(
                    "You are a project journal assistant. Answer the user's question based "
                    "solely on the project notes below. Be specific and narrative — reference "
                    "dates, describe struggles and breakthroughs in context. Be concise.\n\n"
                    f"## Project Notes\n\n{topic_note}"
                ),
            ),
            Message(role="user", content=query),
        ]
        with console.status("[dim]recalling...[/dim]", spinner="dots"):
            response = self.connector.complete(recall_messages, tools=None)
        return response.message.content or ""

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
                "1. `record_moment` for any progress not yet captured.\n"
                "2. `append_session_log` with a brief entry: what was worked on, "
                "any breakthroughs or blockers, what to pick up next session.\n"
                "3. `update_profile` if you learned anything new about the user."
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
