"""Remote peer sync via SSH and rsync."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from claude_mesh.config import MeshConfig, RemotePeerConfig


class RemoteSyncError(RuntimeError):
    """Raised when remote sync operation fails."""


def is_remote_peer(peer_name: str, config: MeshConfig) -> bool:
    """Check if a peer is configured as remote."""
    return peer_name in config.remote_peers


def validate_ssh_connectivity(remote_config: RemotePeerConfig) -> tuple[bool, str]:
    """Test SSH connection to remote peer.

    Returns (success, message).
    """
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
             f"{remote_config['user']}@{remote_config['host']}", "echo", "ok"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, "SSH connection successful"
        return False, f"SSH failed: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "SSH connection timed out"
    except FileNotFoundError:
        return False, "ssh command not found"
    except Exception as exc:
        return False, f"SSH test failed: {exc}"


def push_inbox_to_remote(
    local_inbox: Path,
    peer_name: str,
    remote_config: RemotePeerConfig,
    group_name: str,
) -> None:
    """Push a local inbox file to the remote peer's machine via rsync.

    Args:
        local_inbox: Path to the local inbox file
        peer_name: Name of the peer whose inbox we're pushing
        remote_config: Remote peer configuration
        group_name: Mesh group name (for remote path)
    """
    if not local_inbox.exists():
        # Nothing to push
        return

    remote_inbox_path = f"{remote_config['inbox_path']}/{peer_name}.ftai"
    remote_target = f"{remote_config['user']}@{remote_config['host']}:{remote_inbox_path}"

    try:
        # Ensure remote directory exists first
        subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5",
             f"{remote_config['user']}@{remote_config['host']}",
             "mkdir", "-p", remote_config['inbox_path']],
            check=True,
            capture_output=True,
            timeout=10,
        )

        # rsync the inbox file
        result = subprocess.run(
            ["rsync", "-az", "--timeout=10", str(local_inbox), remote_target],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RemoteSyncError(
                f"rsync push failed for {peer_name}: {result.stderr.strip()}"
            )
    except subprocess.TimeoutExpired as exc:
        raise RemoteSyncError(f"rsync push timed out for {peer_name}") from exc
    except subprocess.CalledProcessError as exc:
        raise RemoteSyncError(
            f"SSH/rsync failed for {peer_name}: {exc.stderr}"
        ) from exc
    except FileNotFoundError as exc:
        raise RemoteSyncError("rsync or ssh command not found") from exc


def pull_inbox_from_remote(
    local_inbox: Path,
    local_peer_name: str,
    remote_config: RemotePeerConfig,
    group_name: str,
) -> None:
    """Pull the local peer's inbox from a remote machine via rsync.

    Remote peers may have written to our inbox; fetch it.

    Args:
        local_inbox: Path to our local inbox file
        local_peer_name: Our own peer name
        remote_config: Remote peer configuration
        group_name: Mesh group name (for remote path)
    """
    remote_inbox_path = f"{remote_config['inbox_path']}/{local_peer_name}.ftai"
    remote_source = f"{remote_config['user']}@{remote_config['host']}:{remote_inbox_path}"

    # Ensure local directory exists
    local_inbox.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    try:
        result = subprocess.run(
            ["rsync", "-az", "--timeout=10", "--ignore-missing-args", 
             remote_source, str(local_inbox)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # rsync returns 23 if source file is missing (no inbox yet) — that's OK
        if result.returncode not in (0, 23):
            raise RemoteSyncError(
                f"rsync pull failed for {local_peer_name}: {result.stderr.strip()}"
            )
    except subprocess.TimeoutExpired as exc:
        raise RemoteSyncError(f"rsync pull timed out for {local_peer_name}") from exc
    except subprocess.CalledProcessError as exc:
        raise RemoteSyncError(
            f"rsync pull failed for {local_peer_name}: {exc.stderr}"
        ) from exc
    except FileNotFoundError as exc:
        raise RemoteSyncError("rsync command not found") from exc


def sync_peer(
    peer_name: str,
    config: MeshConfig,
    home: Path,
    direction: str = "both",
) -> None:
    """Sync with one remote peer (push, pull, or both).

    Args:
        peer_name: Name of the peer to sync with
        config: Mesh configuration
        home: Home directory path
        direction: "push", "pull", or "both"
    """
    if peer_name not in config.remote_peers:
        raise RemoteSyncError(f"Peer {peer_name} is not configured as remote")

    remote_config = config.remote_peers[peer_name]
    group_dir = home / ".claude-mesh" / "groups" / config.mesh_group

    if direction in ("push", "both"):
        # Push: write to remote peer's inbox
        local_inbox_for_remote = group_dir / f"{peer_name}.ftai"
        push_inbox_to_remote(
            local_inbox_for_remote, peer_name, remote_config, config.mesh_group
        )

    if direction in ("pull", "both"):
        # Pull: fetch our own inbox from remote
        our_inbox = group_dir / f"{config.mesh_peer}.ftai"
        pull_inbox_from_remote(
            our_inbox, config.mesh_peer, remote_config, config.mesh_group
        )


def sync_all_remote_peers(config: MeshConfig, home: Path) -> dict[str, Any]:
    """Sync with all configured remote peers.

    Returns a dict of peer_name -> result status.
    """
    results: dict[str, Any] = {}
    
    for peer_name in config.remote_peers:
        try:
            sync_peer(peer_name, config, home, direction="both")
            results[peer_name] = {"success": True}
        except RemoteSyncError as exc:
            results[peer_name] = {"success": False, "error": str(exc)}
    
    return results
