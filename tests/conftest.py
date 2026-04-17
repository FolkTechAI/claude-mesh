"""Shared pytest fixtures for claude-mesh tests."""

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide an isolated HOME for each test to prevent collision with real ~/.claude."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude-mesh").mkdir()
    return tmp_path


@pytest.fixture
def hook_payload_single() -> dict[str, object]:
    """Sample hook payload with NO team_name (single-session mode)."""
    return {
        "session_id": "test-session-abc",
        "hook_event_name": "UserPromptSubmit",
        "cwd": "/tmp/test-project",
        "prompt": "hello",
    }


@pytest.fixture
def hook_payload_team() -> dict[str, object]:
    """Sample hook payload WITH team_name (team mode)."""
    return {
        "session_id": "test-session-xyz",
        "hook_event_name": "TeammateIdle",
        "cwd": "/tmp/test-project",
        "teammate_name": "alpha",
        "team_name": "spike",
    }


@pytest.fixture
def project_with_mesh_config(tmp_home: Path) -> Path:
    """Create a project dir with a valid .claude-mesh config."""
    proj = tmp_home / "project"
    proj.mkdir()
    config_text = (
        "mesh_group: vault-brain\n"
        "mesh_peer: vault\n"
        "cross_cutting_paths:\n"
        "  - src/api/**\n"
    )
    (proj / ".claude-mesh").write_text(config_text)
    return proj
