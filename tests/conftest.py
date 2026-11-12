"""Shared test setup."""

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_from_outer_git(monkeypatch):
    """Under `git commit` the pre-commit hook inherits GIT_DIR, GIT_INDEX_FILE and friends.
    Tests that create their own repositories must not operate on the outer one."""
    for name in [n for n in os.environ if n.startswith("GIT_")]:
        monkeypatch.delenv(name)
