# tests/unit/test_init.py
import os
from pathlib import Path

from claude_mesh.commands.init import run as init_run


def test_init_non_interactive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Simulate group name via env
    monkeypatch.setenv("CLAUDE_MESH_GROUP", "vault-brain")
    rc = init_run(peer="vault")
    assert rc == 0
    cfg = tmp_path / ".claude-mesh"
    assert cfg.exists()
    text = cfg.read_text()
    assert "mesh_group: vault-brain" in text
    assert "mesh_peer: vault" in text
