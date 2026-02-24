"""Unit tests for vault.py — no model, pure file I/O."""
from __future__ import annotations

from datetime import date

import study.vault as v


# ---------------------------------------------------------------------------
# Section get/update
# ---------------------------------------------------------------------------

def test_get_section_basic(tmp_vault):
    path = v.ensure_topic(tmp_vault, "t")
    v.update_section(path, "Sources", "- some paper")
    content = path.read_text()
    assert v.get_section(content, "Sources") == "- some paper"


def test_get_section_nested(tmp_vault):
    path = v.ensure_topic(tmp_vault, "t")
    v.update_section(path, "Understanding/Solid", "- [[Foo]]")
    content = path.read_text()
    assert "[[Foo]]" in v.get_section(content, "Understanding/Solid")


def test_get_section_missing_returns_empty(tmp_vault):
    path = v.ensure_topic(tmp_vault, "t")
    assert v.get_section(path.read_text(), "Nonexistent") == ""


def test_update_section_replaces(tmp_vault):
    path = v.ensure_topic(tmp_vault, "t")
    v.update_section(path, "Sources", "old content")
    v.update_section(path, "Sources", "new content")
    assert v.get_section(path.read_text(), "Sources") == "new content"


def test_update_section_creates_if_missing(tmp_vault):
    path = v.ensure_topic(tmp_vault, "t")
    v.update_section(path, "Brand New Section", "hello")
    assert "hello" in path.read_text()


# ---------------------------------------------------------------------------
# Topic management
# ---------------------------------------------------------------------------

def test_ensure_topic_concept_has_core_concepts(tmp_vault):
    path = v.ensure_topic(tmp_vault, "my-topic")
    assert "## Core Concepts" in path.read_text()


def test_ensure_topic_project_has_goal_and_decisions(tmp_vault):
    path = v.ensure_topic(tmp_vault, "my-project", type="project")
    content = path.read_text()
    assert "## Goal" in content
    assert "## Decisions" in content


def test_ensure_topic_idempotent(tmp_vault):
    path = v.ensure_topic(tmp_vault, "t")
    v.update_section(path, "Sources", "- sentinel")
    v.ensure_topic(tmp_vault, "t")  # second call should not overwrite
    assert "sentinel" in path.read_text()


def test_topic_type_concept(tmp_vault):
    v.ensure_topic(tmp_vault, "concept-topic")
    assert v.topic_type(tmp_vault, "concept-topic") == "concept"


def test_topic_type_project(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    assert v.topic_type(tmp_vault, "proj") == "project"


def test_list_topics(tmp_vault):
    v.ensure_topic(tmp_vault, "alpha")
    v.ensure_topic(tmp_vault, "beta")
    v.ensure_topic(tmp_vault, "nested/child")
    topics = v.list_topics(tmp_vault)
    assert "alpha" in topics
    assert "beta" in topics
    assert "nested/child" in topics


# ---------------------------------------------------------------------------
# Goal section is independent of Decisions
# ---------------------------------------------------------------------------

def test_goal_and_decisions_are_independent(tmp_vault):
    path = v.ensure_topic(tmp_vault, "proj", type="project")

    v.update_section(path, "Goal", "ship it fast")
    assert v.get_section(path.read_text(), "Decisions").strip() == ""

    v.record_decision(tmp_vault, "proj", "infra", "use sqlite", "")
    assert "ship it fast" in v.get_section(path.read_text(), "Goal")


# ---------------------------------------------------------------------------
# Concept mode ops
# ---------------------------------------------------------------------------

def test_add_concept_basic(tmp_vault):
    v.add_concept(tmp_vault, "t", "Attention", [])
    content = v.topic_path(tmp_vault, "t").read_text()
    assert "[[Attention]]" in v.get_section(content, "Core Concepts")


def test_add_concept_dedup(tmp_vault):
    v.add_concept(tmp_vault, "t", "Foo", [])
    v.add_concept(tmp_vault, "t", "Foo", [])
    section = v.get_section(v.topic_path(tmp_vault, "t").read_text(), "Core Concepts")
    assert section.count("[[Foo]]") == 1


def test_add_concept_no_self_link(tmp_vault):
    v.add_concept(tmp_vault, "mytopic", "Foo", ["mytopic", "Bar"])
    section = v.get_section(v.topic_path(tmp_vault, "mytopic").read_text(), "Core Concepts")
    assert "[[mytopic]]" not in section
    assert "[[Bar]]" in section


def test_add_and_remove_source(tmp_vault):
    v.add_source(tmp_vault, "t", "Attention Is All You Need")
    assert v.remove_source(tmp_vault, "t", "Attention Is All You Need") is True
    section = v.get_section(v.topic_path(tmp_vault, "t").read_text(), "Sources")
    assert "Attention Is All You Need" not in section


def test_remove_source_not_found(tmp_vault):
    v.ensure_topic(tmp_vault, "t")
    assert v.remove_source(tmp_vault, "t", "ghost paper") is False


def test_update_understanding_moves_between_levels(tmp_vault):
    v.update_understanding(tmp_vault, "t", "Shaky", "Backprop", "kind of get it")
    v.update_understanding(tmp_vault, "t", "Solid", "Backprop", "nailed it")
    content = v.topic_path(tmp_vault, "t").read_text()
    assert "[[Backprop]]" in v.get_section(content, "Understanding/Solid")
    assert "[[Backprop]]" not in v.get_section(content, "Understanding/Shaky")


def test_append_and_get_synthesis(tmp_vault):
    v.append_synthesis(tmp_vault, "t", "Softmax", "it squashes logits to probs", "")
    entry = v.get_synthesis_entry(tmp_vault, "t", "Softmax")
    assert entry is not None
    assert "squashes" in entry


def test_get_synthesis_entry_missing(tmp_vault):
    v.ensure_topic(tmp_vault, "t")
    assert v.get_synthesis_entry(tmp_vault, "t", "NeverMentioned") is None


def test_link_to_topic(tmp_vault):
    v.ensure_topic(tmp_vault, "proj")
    v.ensure_topic(tmp_vault, "beam-search")
    v.link_to_topic(tmp_vault, "Beam Search", "proj", "beam-search")
    section = v.get_section(v.topic_path(tmp_vault, "proj").read_text(), "Core Concepts")
    assert "[[beam-search]]" in section


# ---------------------------------------------------------------------------
# Project mode ops
# ---------------------------------------------------------------------------

def test_record_decision_appends(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    v.record_decision(tmp_vault, "proj", "storage", "use sqlite", "simple")
    decisions = v.get_decisions(tmp_vault, "proj")
    assert "sqlite" in decisions.lower()


def test_get_decisions_empty_initially(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    assert v.get_decisions(tmp_vault, "proj").strip() == ""


def test_update_architecture_upsert(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    v.update_architecture(tmp_vault, "proj", "Cache", "LRU eviction")
    v.update_architecture(tmp_vault, "proj", "Cache", "FIFO eviction")
    content = v.topic_path(tmp_vault, "proj").read_text()
    arch = v.get_section(content, "Architecture")
    assert "FIFO" in arch
    assert "LRU" not in arch


def test_add_and_resolve_open_question(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    v.add_open_question(tmp_vault, "proj", "Should we shard by user?")
    v.resolve_open_question(tmp_vault, "proj", "shard by user")
    content = v.topic_path(tmp_vault, "proj").read_text()
    assert "shard by user" not in v.get_section(content, "Open Questions").lower()


def test_add_and_resolve_tension(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    v.add_tension(tmp_vault, "proj", "stateless vs sessions")
    assert "stateless" in v.get_tensions(tmp_vault, "proj")
    v.resolve_tension(tmp_vault, "proj", "stateless vs sessions")
    assert v.get_tensions(tmp_vault, "proj").strip() == ""
