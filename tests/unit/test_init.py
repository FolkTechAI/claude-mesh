# tests/unit/test_init.py
import os
from pathlib import Path

from claude_mesh.commands.init import run as init_run


def test_init_non_interactive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Simulate group name via env
    monkeypatch.setenv("CLAUDE_MESH_GROUP", "vault-brain")
    monkeypatch.setenv("CLAUDE_MESH_OTHER", "brain")
    rc = init_run(peer="vault")
    assert rc == 0
    cfg = tmp_path / ".claude-mesh"
    assert cfg.exists()
    text = cfg.read_text()
    assert "mesh_group: vault-brain" in text
    assert "mesh_peer: vault" in text
    # Bug #1 fix: explicit mesh_peers list is always written
    assert "mesh_peers:" in text
    assert "- vault" in text
    assert "- brain" in text


def test_init_default_other_is_peer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAUDE_MESH_GROUP", raising=False)
    monkeypatch.delenv("CLAUDE_MESH_OTHER", raising=False)
    rc = init_run(peer="alpha")
    assert rc == 0
    text = (tmp_path / ".claude-mesh").read_text()
    assert "mesh_group: alpha-peer" in text
    assert "mesh_peer: alpha" in text


def test_init_rejects_same_peer_and_other(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = init_run(peer="alpha", other="alpha")
    assert rc == 2
    assert not (tmp_path / ".claude-mesh").exists()


def test_init_rejects_group_missing_both_peers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = init_run(peer="alpha", other="beta", group="gamma-delta")
    assert rc == 2
    assert not (tmp_path / ".claude-mesh").exists()


def test_init_peer_with_hyphen_accepted(tmp_path, monkeypatch):
    """Bug #2 regression: peer names containing hyphens must work end-to-end."""
    monkeypatch.chdir(tmp_path)
    rc = init_run(peer="mesh-test", other="peer")
    assert rc == 0
    text = (tmp_path / ".claude-mesh").read_text()
    assert "mesh_peer: mesh-test" in text
    assert "mesh_group: mesh-test-peer" in text
