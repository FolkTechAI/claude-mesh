# tests/unit/test_storage.py
from pathlib import Path

import pytest

from claude_mesh.config import MeshConfig
from claude_mesh.mode import Mode
from claude_mesh.storage import (
    atomic_append,
    ensure_directory,
    resolve_knowledge_path,
)


def test_resolve_team_mode(tmp_home: Path):
    payload = {"team_name": "spike", "teammate_name": "alpha"}
    path = resolve_knowledge_path(Mode.TEAM, payload, config=None, home=tmp_home)
    assert path == tmp_home / ".claude" / "teams" / "spike" / "knowledge.ftai"


def test_resolve_standalone_mode(tmp_home: Path):
    config = MeshConfig(mesh_group="vault-brain", mesh_peer="vault")
    # When vault writes, it writes to the PEER's inbox (brain's inbox)
    # In standalone mode the caller passes the peer they are writing to
    path = resolve_knowledge_path(
        Mode.STANDALONE, payload={}, config=config, home=tmp_home, writing_to_peer="brain"
    )
    assert path == tmp_home / ".claude-mesh" / "groups" / "vault-brain" / "brain.ftai"


def test_ensure_directory_creates_with_0700(tmp_path: Path):
    d = tmp_path / "sub" / "nested"
    ensure_directory(d)
    assert d.exists()
    assert (d.stat().st_mode & 0o777) == 0o700


def test_atomic_append_writes_complete_data(tmp_path: Path):
    f = tmp_path / "log.ftai"
    atomic_append(f, "line 1\n")
    atomic_append(f, "line 2\n")
    assert f.read_text() == "line 1\nline 2\n"
