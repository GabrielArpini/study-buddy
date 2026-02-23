from __future__ import annotations

import re
import sys
from pathlib import Path

import click
import questionary
from rich.console import Console

import study.config as config_mod
import study.vault as vault_mod
from study.connectors import get_connector
from study.git_ops import ensure_vault_git
from study.session import StudySession
from study.repl import run_repl

console = Console()


def _sanitize_topic(name: str) -> str:
    """Convert arbitrary string to kebab-case topic name."""
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    return name or "untitled"


@click.group(invoke_without_command=True)
@click.option("--topic", "-t", default=None, help="Topic name (skip picker)")
@click.pass_context
def main(ctx: click.Context, topic: str | None) -> None:
    """study-buddy: Socratic CLI study companion."""
    if ctx.invoked_subcommand is not None:
        return

    cfg = config_mod.load()
    vault = config_mod.vault_path(cfg)

    if not vault.exists():
        console.print(f"[yellow]Vault not found at {vault}. Run 'study config' to set it up.[/yellow]")
        sys.exit(1)

    vault_mod.ensure_vault_structure(vault)
    ensure_vault_git(vault)

    # Write framework and profile templates if absent
    _ensure_vault_templates(vault)

    if topic:
        chosen_topic = _sanitize_topic(topic)
    else:
        chosen_topic = _topic_picker(vault, cfg)
        if not chosen_topic:
            return

    vault_mod.ensure_topic(vault, chosen_topic)

    connector_name = cfg["llm"]["connector"]
    model = cfg["llm"]["model"]
    connector = get_connector(connector_name, model)
    model_label = f"{connector_name}/{model}"

    session = StudySession(
        topic=chosen_topic,
        vault=vault,
        connector=connector,
    )
    run_repl(session, model_label)


@main.command("ls")
def cmd_ls() -> None:
    """List all topics in the vault."""
    cfg = config_mod.load()
    vault = config_mod.vault_path(cfg)
    vault_mod.ensure_vault_structure(vault)
    from study.renderer import render_topics
    render_topics(vault)


@main.command("reset")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def cmd_reset(yes: bool) -> None:
    """Reset vault data (topics, daily logs, profile, or everything)."""
    cfg = config_mod.load()
    vault = config_mod.vault_path(cfg)

    if not vault.exists():
        console.print(f"[yellow]Vault not found at {vault}.[/yellow]")
        return

    scope = questionary.select(
        "What do you want to reset?",
        choices=[
            questionary.Choice("Everything  (all topics + daily logs + profile)", value="all"),
            questionary.Choice("All topics", value="topics"),
            questionary.Choice("One specific topic", value="topic"),
            questionary.Choice("Daily logs", value="daily"),
            questionary.Choice("Learner profile", value="profile"),
        ],
    ).ask()

    if scope is None:
        console.print("[yellow]Reset cancelled.[/yellow]")
        return

    # For single-topic scope, ask which one
    chosen_topic: str | None = None
    if scope == "topic":
        topics = vault_mod.list_topics(vault)
        if not topics:
            console.print("[yellow]No topics found in vault.[/yellow]")
            return
        chosen_topic = questionary.select(
            "Which topic?",
            choices=topics,
        ).ask()
        if chosen_topic is None:
            console.print("[yellow]Reset cancelled.[/yellow]")
            return

    # Confirmation
    if not yes:
        label = {
            "all": "the entire vault (all topics, daily logs, and profile)",
            "topics": "all topics",
            "topic": f"topic '{chosen_topic}'",
            "daily": "all daily logs",
            "profile": "the learner profile",
        }[scope]
        confirmed = questionary.confirm(
            f"This will permanently delete {label}. Continue?",
            default=False,
        ).ask()
        if not confirmed:
            console.print("[yellow]Reset cancelled.[/yellow]")
            return

    # Execute reset
    if scope == "all":
        n_topics = vault_mod.reset_all_topics(vault)
        n_daily = vault_mod.reset_daily_logs(vault)
        vault_mod.reset_profile(vault)
        console.print(
            f"[green]Reset complete:[/green] {n_topics} topic(s), "
            f"{n_daily} daily log(s) deleted, profile cleared."
        )

    elif scope == "topics":
        n = vault_mod.reset_all_topics(vault)
        console.print(f"[green]Deleted {n} topic file(s).[/green]")

    elif scope == "topic":
        assert chosen_topic is not None
        vault_mod.reset_topic(vault, chosen_topic)
        console.print(f"[green]Topic '{chosen_topic}' reset to blank template.[/green]")

    elif scope == "daily":
        n = vault_mod.reset_daily_logs(vault)
        console.print(f"[green]Deleted {n} daily log(s).[/green]")

    elif scope == "profile":
        vault_mod.reset_profile(vault)
        console.print("[green]Learner profile reset.[/green]")


@main.command("config")
def cmd_config() -> None:
    """Interactive configuration wizard."""
    cfg = config_mod.load()

    console.print("[bold cyan]study-buddy configuration[/bold cyan]\n")

    connector = questionary.select(
        "LLM connector:",
        choices=["ollama", "anthropic", "openai"],
        default=cfg["llm"]["connector"],
    ).ask()

    model = questionary.text(
        "Model name:",
        default=cfg["llm"]["model"],
    ).ask()

    vault_path_str = questionary.text(
        "Vault path:",
        default=cfg["vault"]["path"],
    ).ask()

    if connector is None or model is None or vault_path_str is None:
        console.print("[yellow]Configuration cancelled.[/yellow]")
        return

    cfg["llm"]["connector"] = connector
    cfg["llm"]["model"] = model
    cfg["vault"]["path"] = vault_path_str

    config_mod.save(cfg)

    vault = Path(vault_path_str).expanduser()
    vault_mod.ensure_vault_structure(vault)
    _ensure_vault_templates(vault)

    console.print(f"\n[green]Config saved to {config_mod.CONFIG_FILE}[/green]")
    console.print(f"[green]Vault: {vault}[/green]")

    if connector == "ollama":
        console.print(
            "\n[dim]Make sure Ollama is running:[/dim]\n"
            "  ollama serve\n"
            f"  ollama pull {model}\n"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _topic_picker(vault: Path, cfg: dict) -> str | None:
    """Interactive topic picker with questionary."""
    topics = vault_mod.list_topics(vault)

    choices = []
    for t in topics:
        last = vault_mod.get_last_session(vault, t) or "—"
        parts = t.split("/")
        depth = len(parts) - 1
        indent = "  " * depth
        name = parts[-1]
        prefix = "└─ " if depth > 0 else ""
        choices.append(questionary.Choice(
            title=f"{indent}{prefix}{name:<25} last: {last}",
            value=t,
        ))
    choices.append(questionary.Choice(title="+ new topic", value="__new__"))

    answer = questionary.select(
        "Select topic (↑↓ Enter to confirm):",
        choices=choices,
    ).ask()

    if answer is None:
        return None

    if answer == "__new__":
        name = questionary.text("New topic name:").ask()
        if not name:
            return None
        return _sanitize_topic(name)

    return answer


def _ensure_vault_templates(vault: Path) -> None:
    """Write _framework.md and _profile.md if they don't exist."""
    fw = vault_mod.framework_path(vault)
    if not fw.exists():
        fw.write_text(_FRAMEWORK_TEMPLATE)

    profile = vault_mod.profile_path(vault)
    if not profile.exists():
        profile.write_text(_PROFILE_TEMPLATE)


_FRAMEWORK_TEMPLATE = """\
# Study Buddy Framework

You are a Socratic study companion. Your role is to help the learner deeply understand
topics through dialogue — not by explaining things to them, but by asking questions
that help them discover understanding themselves.

## Vault Structure

The vault contains these files:
- `_framework.md` — your instructions (this file)
- `_profile.md` — learner profile and metacognitive notes
- `_daily/YYYY-MM-DD.md` — daily activity logs
- `topics/<topic-name>.md` — one file per study topic

Each topic note has fixed sections:
- **Sources** — references and materials
- **Core Concepts** — key concepts as wikilinks
- **Understanding** — three subsections:
  - **Solid** — concepts the learner can explain and apply
  - **Shaky** — partial understanding, needs reinforcement
  - **Not Yet Engaged** — introduced but not yet worked on
- **My Synthesis** — learner's own explanation in their own words
- **Session Log** — dated session summaries

## Wikilink Conventions

- Use noun phrases in consistent title case: `[[Gradient Descent]]`, `[[Loss Function]]`
- Cross-topic links use the topic kebab-case name: `[[linear-algebra]]`
- Link generously — wikilinks build the knowledge graph

## Understanding Level Criteria

**Solid**: Learner can:
- Explain the concept without prompting
- Apply it to novel examples
- Identify edge cases or failure modes
- Connect it to other concepts naturally

**Shaky**: Learner:
- Recognizes the concept when named
- Has partial or confused understanding
- Cannot reliably apply it
- Needs more dialogue before it becomes solid

**Not Yet Engaged**: Concept has appeared in conversation or materials
but the learner hasn't demonstrated any active engagement with it yet.

## Question Rules

1. Ask at most 5 questions per response
2. Start with easier recall questions, progress to application/synthesis
3. Prioritize questions over explanations (Socratic priority)
4. Never give away the answer before the learner attempts it
5. If learner is stuck, give a hint, then a smaller question, not the answer

## Tool Usage Guidelines

Call tools to keep the vault accurate:
- `update_understanding` — whenever mastery level changes
- `add_concept` — when a new concept is introduced
- `append_session_log` — at natural session endpoints
- `add_source` — ONLY when the learner explicitly names a source they have used (book title, paper, course). Never add URLs.
- `remove_source` — immediately if you added a source by mistake or the learner didn't ask for it
- `update_profile` — when you learn something important about the learner's background or preferences
- `link_to_topic` — when a concept clearly connects to another topic

## What NOT To Do

- Do not lecture unprompted
- Do not invent sources, citations, or URLs — you cannot verify web links exist
- Do NOT generate URLs or hyperlinks of any kind in your responses
- Do not stray into unrelated topics unless the learner explicitly asks
- Do not mark concepts as Solid unless the learner has genuinely demonstrated mastery
- Do not update the vault with every single exchange — batch updates intelligently
- Do not call `add_source` speculatively — wait for the learner to mention a specific source
"""

_PROFILE_TEMPLATE = """\
# Learner Profile

*This file is updated by the model as it learns about you.*

## Background

(unknown — will be filled in as we talk)

## Learning Preferences

(unknown)

## Metacognitive Notes

(unknown)
"""
