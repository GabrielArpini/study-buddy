from __future__ import annotations

import pytest

import study.vault as vault_mod
import study.config as config_mod
from study.connectors import get_connector
from study.session import StudySession


@pytest.fixture
def tmp_vault(tmp_path):
    vault_mod.ensure_vault_structure(tmp_path)
    return tmp_path


@pytest.fixture
def project_session(tmp_vault):
    """Fresh project-type StudySession backed by a temp vault. Uses real configured connector."""
    vault_mod.ensure_topic(tmp_vault, "test-project", type="project")
    cfg = config_mod.load()
    connector = get_connector(cfg["llm"]["connector"], cfg["llm"]["model"])
    return StudySession("test-project", tmp_vault, connector)
