"""Unit tests for remote peer configuration parsing."""

from __future__ import annotations

import pytest

from claude_mesh.config import ConfigError, _parse_minimal_yaml, load_config


def test_parse_remote_peers_simple_map():
    yaml = """
mesh_group: test-group
mesh_peer: peer1
remote_peers:
    peer2:
        host: remote.local
        user: mike
        inbox_path: /home/mike/.claude-mesh/groups/test-group
"""
    parsed = _parse_minimal_yaml(yaml)
    assert "remote_peers" in parsed
    assert isinstance(parsed["remote_peers"], dict)
    assert "peer2" in parsed["remote_peers"]
    assert parsed["remote_peers"]["peer2"]["host"] == "remote.local"


def test_load_config_with_remote_peer(tmp_path):
    config_file = tmp_path / ".claude-mesh"
    config_file.write_text(
        "mesh_group: mac-grokbot\n"
        "mesh_peer: mac\n"
        "mesh_peers:\n"
        "  - mac\n"
        "  - grokbot\n"
        "remote_peers:\n"
        "    grokbot:\n"
        "        host: grokbot.local\n"
        "        user: mike\n"
        "        inbox_path: /home/mike/.claude-mesh/groups/mac-grokbot\n"
    )
    
    cfg = load_config(config_file)
    
    assert cfg.mesh_group == "mac-grokbot"
    assert cfg.mesh_peer == "mac"
    assert "grokbot" in cfg.remote_peers
    assert cfg.remote_peers["grokbot"]["host"] == "grokbot.local"
    assert cfg.remote_peers["grokbot"]["user"] == "mike"
    assert cfg.remote_peers["grokbot"]["inbox_path"] == "/home/mike/.claude-mesh/groups/mac-grokbot"


def test_remote_peer_missing_host(tmp_path):
    config_file = tmp_path / ".claude-mesh"
    config_file.write_text(
        "mesh_group: test\n"
        "mesh_peer: a\n"
        "remote_peers:\n"
        "    b:\n"
        "        user: mike\n"
        "        inbox_path: /path\n"
    )
    
    with pytest.raises(ConfigError, match="missing 'host'"):
        load_config(config_file)


def test_remote_peer_missing_user(tmp_path):
    config_file = tmp_path / ".claude-mesh"
    config_file.write_text(
        "mesh_group: test\n"
        "mesh_peer: a\n"
        "remote_peers:\n"
        "    b:\n"
        "        host: remote.local\n"
        "        inbox_path: /path\n"
    )
    
    with pytest.raises(ConfigError, match="missing 'user'"):
        load_config(config_file)


def test_remote_peer_missing_inbox_path(tmp_path):
    config_file = tmp_path / ".claude-mesh"
    config_file.write_text(
        "mesh_group: test\n"
        "mesh_peer: a\n"
        "remote_peers:\n"
        "    b:\n"
        "        host: remote.local\n"
        "        user: mike\n"
    )
    
    with pytest.raises(ConfigError, match="missing 'inbox_path'"):
        load_config(config_file)


def test_remote_peer_invalid_name(tmp_path):
    config_file = tmp_path / ".claude-mesh"
    config_file.write_text(
        "mesh_group: test\n"
        "mesh_peer: a\n"
        "remote_peers:\n"
        "    Bad_Name:\n"
        "        host: remote.local\n"
        "        user: mike\n"
        "        inbox_path: /path\n"
    )
    
    with pytest.raises(ConfigError, match="invalid characters"):
        load_config(config_file)


def test_config_without_remote_peers(tmp_path):
    """Config with no remote_peers should have empty dict."""
    config_file = tmp_path / ".claude-mesh"
    config_file.write_text(
        "mesh_group: test\n"
        "mesh_peer: a\n"
        "mesh_peers:\n"
        "  - a\n"
        "  - b\n"
    )
    
    cfg = load_config(config_file)
    assert cfg.remote_peers == {}
