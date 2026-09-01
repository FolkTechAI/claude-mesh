"""Unit tests for remote sync operations."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_mesh.config import MeshConfig, RemotePeerConfig
from claude_mesh.remote import (
    RemoteSyncError,
    is_remote_peer,
    pull_inbox_from_remote,
    push_inbox_to_remote,
    sync_all_remote_peers,
    sync_peer,
    validate_ssh_connectivity,
)


@pytest.fixture
def config_with_remote():
    return MeshConfig(
        mesh_group="test-group",
        mesh_peer="local-peer",
        mesh_peers=["local-peer", "remote-peer"],
        remote_peers={
            "remote-peer": RemotePeerConfig(
                host="remote.local",
                user="testuser",
                inbox_path="/remote/path/.claude-mesh/groups/test-group",
            )
        },
    )


def test_is_remote_peer(config_with_remote):
    assert is_remote_peer("remote-peer", config_with_remote)
    assert not is_remote_peer("local-peer", config_with_remote)
    assert not is_remote_peer("unknown", config_with_remote)


@patch("claude_mesh.remote.subprocess.run")
def test_validate_ssh_connectivity_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stderr="")
    
    remote_config = RemotePeerConfig(
        host="test.local",
        user="testuser",
        inbox_path="/path",
    )
    
    success, message = validate_ssh_connectivity(remote_config)
    
    assert success
    assert "successful" in message.lower()
    mock_run.assert_called_once()
    assert "ssh" in mock_run.call_args[0][0]
    assert "testuser@test.local" in mock_run.call_args[0][0]


@patch("claude_mesh.remote.subprocess.run")
def test_validate_ssh_connectivity_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=255, stderr="Connection refused")
    
    remote_config = RemotePeerConfig(
        host="test.local",
        user="testuser",
        inbox_path="/path",
    )
    
    success, message = validate_ssh_connectivity(remote_config)
    
    assert not success
    assert "failed" in message.lower()


@patch("claude_mesh.remote.subprocess.run")
def test_push_inbox_to_remote(mock_run, tmp_path, config_with_remote):
    """Test pushing local inbox to remote peer."""
    mock_run.return_value = MagicMock(returncode=0)
    
    local_inbox = tmp_path / "remote-peer.ftai"
    local_inbox.write_text("@message\nfrom: local-peer\n")
    
    push_inbox_to_remote(
        local_inbox,
        "remote-peer",
        config_with_remote.remote_peers["remote-peer"],
        "test-group",
    )
    
    # Should call ssh to create directory, then rsync
    assert mock_run.call_count == 2
    
    # First call: mkdir via SSH
    assert "ssh" in mock_run.call_args_list[0][0][0]
    assert "mkdir" in mock_run.call_args_list[0][0][0]
    
    # Second call: rsync
    assert "rsync" in mock_run.call_args_list[1][0][0]
    assert str(local_inbox) in mock_run.call_args_list[1][0][0]


@patch("claude_mesh.remote.subprocess.run")
def test_push_inbox_nonexistent_file(mock_run, tmp_path, config_with_remote):
    """Push should do nothing if local inbox doesn't exist."""
    nonexistent = tmp_path / "nonexistent.ftai"
    
    push_inbox_to_remote(
        nonexistent,
        "remote-peer",
        config_with_remote.remote_peers["remote-peer"],
        "test-group",
    )
    
    # Should not call any subprocess
    mock_run.assert_not_called()


@patch("claude_mesh.remote.subprocess.run")
def test_push_inbox_rsync_failure(mock_run, tmp_path, config_with_remote):
    """Test rsync failure handling."""
    mock_run.side_effect = [
        MagicMock(returncode=0),  # ssh mkdir succeeds
        MagicMock(returncode=1, stderr="rsync error"),  # rsync fails
    ]
    
    local_inbox = tmp_path / "remote-peer.ftai"
    local_inbox.write_text("@message\n")
    
    with pytest.raises(RemoteSyncError, match="rsync push failed"):
        push_inbox_to_remote(
            local_inbox,
            "remote-peer",
            config_with_remote.remote_peers["remote-peer"],
            "test-group",
        )


@patch("claude_mesh.remote.subprocess.run")
def test_pull_inbox_from_remote(mock_run, tmp_path, config_with_remote):
    """Test pulling inbox from remote peer."""
    mock_run.return_value = MagicMock(returncode=0)
    
    local_inbox = tmp_path / "local-peer.ftai"
    
    pull_inbox_from_remote(
        local_inbox,
        "local-peer",
        config_with_remote.remote_peers["remote-peer"],
        "test-group",
    )
    
    # Should call rsync
    mock_run.assert_called_once()
    assert "rsync" in mock_run.call_args[0][0]
    assert str(local_inbox) in mock_run.call_args[0][0]


@patch("claude_mesh.remote.subprocess.run")
def test_pull_inbox_remote_missing_ok(mock_run, tmp_path, config_with_remote):
    """Pull should succeed even if remote inbox doesn't exist (rsync exit 23)."""
    mock_run.return_value = MagicMock(returncode=23)  # File missing
    
    local_inbox = tmp_path / "local-peer.ftai"
    
    # Should not raise
    pull_inbox_from_remote(
        local_inbox,
        "local-peer",
        config_with_remote.remote_peers["remote-peer"],
        "test-group",
    )


@patch("claude_mesh.remote.subprocess.run")
def test_sync_peer_both_directions(mock_run, tmp_path, config_with_remote):
    """Test syncing both push and pull."""
    mock_run.return_value = MagicMock(returncode=0)
    
    home = tmp_path / "home"
    group_dir = home / ".claude-mesh" / "groups" / "test-group"
    group_dir.mkdir(parents=True)
    
    # Create a local inbox for remote peer (to push)
    (group_dir / "remote-peer.ftai").write_text("@message\n")
    
    sync_peer("remote-peer", config_with_remote, home, direction="both")
    
    # Should call ssh mkdir + rsync push + rsync pull = 3 calls
    assert mock_run.call_count == 3


@patch("claude_mesh.remote.sync_peer")
def test_sync_all_remote_peers(mock_sync_peer, config_with_remote):
    """Test syncing all remote peers."""
    mock_sync_peer.return_value = None
    
    results = sync_all_remote_peers(config_with_remote, Path("/tmp"))
    
    assert "remote-peer" in results
    assert results["remote-peer"]["success"]
    mock_sync_peer.assert_called_once()


@patch("claude_mesh.remote.sync_peer")
def test_sync_all_remote_peers_with_error(mock_sync_peer, config_with_remote):
    """Test syncing with one peer failing."""
    mock_sync_peer.side_effect = RemoteSyncError("Connection failed")
    
    results = sync_all_remote_peers(config_with_remote, Path("/tmp"))
    
    assert "remote-peer" in results
    assert not results["remote-peer"]["success"]
    assert "Connection failed" in results["remote-peer"]["error"]
