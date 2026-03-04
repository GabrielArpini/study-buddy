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


def test_ensure_topic_project_has_new_sections(tmp_vault):
    path = v.ensure_topic(tmp_vault, "my-project", type="project")
    content = path.read_text()
    for section in ("## Goal", "## Timeline", "## Breakthroughs",
                    "## Blockers", "## Decisions", "## Sources", "## Session Log"):
        assert section in content
    assert "### Nodes" in content
    assert "### Edges" in content


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


def test_record_moment_progress_goes_to_timeline_only(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    v.record_moment(tmp_vault, "proj", "progress", "got the tokenizer working")
    content = v.topic_path(tmp_vault, "proj").read_text()
    assert "got the tokenizer working" in v.get_section(content, "Timeline")
    assert "[progress]" in v.get_section(content, "Timeline")
    assert v.get_section(content, "Breakthroughs").strip() == ""
    assert v.get_section(content, "Blockers").strip() == ""


def test_record_moment_breakthrough_populates_both_sections(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    v.record_moment(tmp_vault, "proj", "breakthrough", "attention masking clicked")
    content = v.topic_path(tmp_vault, "proj").read_text()
    assert "attention masking clicked" in v.get_section(content, "Timeline")
    assert "attention masking clicked" in v.get_section(content, "Breakthroughs")
    assert v.get_section(content, "Blockers").strip() == ""


def test_record_moment_blocker_populates_both_sections(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    v.record_moment(tmp_vault, "proj", "blocker", "stuck on warp divergence")
    content = v.topic_path(tmp_vault, "proj").read_text()
    assert "warp divergence" in v.get_section(content, "Timeline")
    assert "warp divergence" in v.get_section(content, "Blockers")
    assert v.get_section(content, "Breakthroughs").strip() == ""


def test_resolve_blocker_appends_resolution(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    v.record_moment(tmp_vault, "proj", "blocker", "stuck on warp divergence in reduction")
    found = v.resolve_blocker(tmp_vault, "proj", "warp divergence", "reordered mask ops")
    assert found is True
    blockers = v.get_section(v.topic_path(tmp_vault, "proj").read_text(), "Blockers")
    assert "resolved" in blockers.lower()
    assert "reordered mask ops" in blockers


def test_resolve_blocker_returns_false_when_not_found(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    assert v.resolve_blocker(tmp_vault, "proj", "nonexistent", "whatever") is False


def test_add_graph_node_writes_to_nodes_section(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    v.add_graph_node(tmp_vault, "proj", "uncertainty", "not sure if tiling fits in shared memory")
    nodes = v.get_graph_nodes(tmp_vault, "proj")
    assert "[uncertainty]" in nodes
    assert "not sure if tiling" in nodes


def test_add_graph_node_with_resolves_writes_edge(tmp_vault):
    import re as _re
    v.ensure_topic(tmp_vault, "proj", type="project")
    v.add_graph_node(tmp_vault, "proj", "uncertainty", "not sure about tiling")
    nodes = v.get_graph_nodes(tmp_vault, "proj")
    match = _re.search(r'\[uncertainty\] ([\w-]+):', nodes)
    assert match is not None
    uncertainty_slug = match.group(1)
    v.add_graph_node(tmp_vault, "proj", "certainty", "tiling confirmed works", resolves_slug=uncertainty_slug)
    edges = v.get_graph_edges(tmp_vault, "proj")
    assert f"{uncertainty_slug} → resolves" in edges


def test_add_graph_node_returns_current_nodes(tmp_vault):
    v.ensure_topic(tmp_vault, "proj", type="project")
    result = v.add_graph_node(tmp_vault, "proj", "milestone", "kernel working")
    assert "Current nodes:" in result
    assert "kernel working" in result
