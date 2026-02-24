"""
Behavioral eval tests — run real messages through StudySession and assert vault state.

These tests require ollama to be running with the configured model.
Run only these:   uv run --group dev pytest tests/test_eval.py -v
Skip these:       uv run --group dev pytest tests/test_vault.py -v
"""
from __future__ import annotations

import pytest

import study.config as config_mod
import study.vault as vault_mod
from study.connectors import get_connector
from study.session import StudySession


def _fresh_session(tmp_vault, topic="test-project"):
    """Build a StudySession after all vault state is set — so prior decisions appear in system prompt."""
    cfg = config_mod.load()
    connector = get_connector(cfg["llm"]["connector"], cfg["llm"]["model"])
    return StudySession(topic, tmp_vault, connector)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_section(session, section: str) -> str:
    path = vault_mod.topic_path(session.vault, session.topic)
    return vault_mod.get_section(path.read_text(), section)


def _set_section(session, section: str, content: str) -> None:
    path = vault_mod.topic_path(session.vault, session.topic)
    vault_mod.update_section(path, section, content)


# ---------------------------------------------------------------------------
# 1. Goal statement → ## Goal, NOT ## Decisions
# ---------------------------------------------------------------------------

def test_goal_routes_to_goal_section_not_decisions(project_session):
    """A top-level objective should land in Goal, leaving Decisions empty."""
    project_session.send(
        "I want to build a fast inference engine that maximizes tokens per second."
    )

    goal = _read_section(project_session, "Goal")
    decisions = _read_section(project_session, "Decisions")

    assert goal.strip() != "", "Goal section should not be empty after stating an objective"
    assert decisions.strip() == "", (
        f"Decisions should be empty for a goal statement, got:\n{decisions}"
    )


# ---------------------------------------------------------------------------
# 2. Technique decision → ## Decisions, no false conflict in ## Tensions
# ---------------------------------------------------------------------------

def test_technique_decision_no_false_conflict(project_session):
    """Implementing a technique that serves the goal must not fire a conflict."""
    _set_section(project_session, "Goal", "maximize tokens per second")

    project_session.send("I implemented KV cache to speed up the attention computation.")

    decisions = _read_section(project_session, "Decisions")
    tensions = _read_section(project_session, "Tensions")

    assert "kv" in decisions.lower() or "cache" in decisions.lower(), (
        f"Expected KV cache in Decisions, got:\n{decisions}"
    )
    assert tensions.strip() == "", (
        f"False conflict fired — Tensions should be empty, got:\n{tensions}"
    )


# ---------------------------------------------------------------------------
# 3. Real conflict (mutually exclusive decisions) → ## Tensions
# ---------------------------------------------------------------------------

def test_real_conflict_fires_tension(tmp_vault):
    """Two mutually exclusive decoding strategies should produce a Tension."""
    vault_mod.ensure_topic(tmp_vault, "test-project", type="project")
    vault_mod.record_decision(
        tmp_vault, "test-project", "decoding", "use beam search", "better output quality"
    )
    # Build session AFTER prior decision is written — so it appears in system prompt context
    session = _fresh_session(tmp_vault)

    session.send(
        "Actually I'm scrapping beam search — I'll use greedy decoding instead, "
        "it's faster and simpler."
    )

    tensions = _read_section(session, "Tensions")
    assert tensions.strip() != "", (
        "Expected a conflict to be logged in Tensions for beam search vs greedy decoding"
    )


# ---------------------------------------------------------------------------
# 4. Cross-topic: concept with existing vault note → link recorded
# ---------------------------------------------------------------------------

def test_cross_topic_link_when_note_exists(project_session):
    """When user mentions a concept that has a vault note, a wikilink should appear."""
    vault_mod.ensure_topic(project_session.vault, "beam-search")

    project_session.send(
        "I'm thinking about using beam search for the decoding step."
    )

    path = vault_mod.topic_path(project_session.vault, project_session.topic)
    content = path.read_text()
    assert "[[beam-search]]" in content, (
        "Expected [[beam-search]] wikilink in project note after mentioning the concept"
    )


# ---------------------------------------------------------------------------
# 5. Cross-topic: concept without vault note → no crash
# ---------------------------------------------------------------------------

def test_no_crash_when_concept_has_no_note(project_session):
    """Mentioning a concept that has no vault note should not raise an error."""
    reply = project_session.send(
        "I might use flash attention to speed up the transformer layers."
    )
    # Just needs to complete without exception and return a string
    assert reply is not None
