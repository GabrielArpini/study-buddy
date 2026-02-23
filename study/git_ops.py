from __future__ import annotations

from datetime import date
from pathlib import Path

import git


def ensure_vault_git(vault: Path) -> git.Repo:
    """Initialize a git repo in vault if one doesn't exist. Return Repo."""
    try:
        repo = git.Repo(vault, search_parent_directories=True)
    except git.InvalidGitRepositoryError:
        repo = git.Repo.init(vault)
        gitignore = vault / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(".DS_Store\n*.pyc\n__pycache__/\n")
        repo.index.add([".gitignore"])
        repo.index.commit("init: initialize study vault")
    return repo


def commit_session(vault: Path, topic: str) -> bool:
    """
    Stage all changes in vault and create a session commit.
    Returns True if a commit was made, False if nothing to commit.
    """
    try:
        repo = ensure_vault_git(vault)
        repo.git.add(A=True)
        if not repo.index.diff("HEAD") and not repo.untracked_files:
            return False
        today = date.today().isoformat()
        repo.index.commit(f"session({topic}): {today}")
        return True
    except Exception:
        # If HEAD doesn't exist yet (no commits), handle initial commit
        try:
            repo = git.Repo(vault)
            repo.git.add(A=True)
            repo.index.commit(f"session({topic}): {date.today().isoformat()}")
            return True
        except Exception:
            return False
