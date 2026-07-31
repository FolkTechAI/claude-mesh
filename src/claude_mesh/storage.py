# src/claude_mesh/storage.py
"""Knowledge-file path resolution and atomic I/O."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import Any

from claude_mesh.config import MeshConfig
from claude_mesh.mode import Mode


def ensure_directory(path: Path) -> None:
    """Create directory with 0700 permissions if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def resolve_knowledge_path(
    mode: Mode,
    payload: dict[str, Any],
    config: MeshConfig | None,
    home: Path,
    writing_to_peer: str | None = None,
) -> Path:
    """Return the knowledge file path for this mode and context.

    In TEAM mode: `~/.claude/teams/{team_name}/knowledge.ftai`
    In STANDALONE mode when reading own inbox: `~/.claude-mesh/groups/{group}/{own_peer}.ftai`
    In STANDALONE mode when writing to peer: `~/.claude-mesh/groups/{group}/{peer}.ftai`
    """
    if mode == Mode.TEAM:
        team_name = str(payload.get("team_name", "")).strip()
        if not team_name:
            raise ValueError("Team mode but no team_name in payload")
        return home / ".claude" / "teams" / team_name / "knowledge.ftai"

    if config is None:
        raise ValueError("Standalone mode requires a MeshConfig")

    group_dir = home / ".claude-mesh" / "groups" / config.mesh_group
    peer = writing_to_peer if writing_to_peer else config.mesh_peer
    return group_dir / f"{peer}.ftai"


def atomic_append(path: Path, text: str) -> None:
    """Append a complete record under an advisory cross-process lock."""
    ensure_directory(path.parent)
    data = text.encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.chmod(path, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write while appending mesh event")
            view = view[written:]
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def append_event(path: Path, header: str, event: str) -> None:
    """Initialize an inbox once and append one complete event under one lock.

    Keeping the empty-file check, header write, and event write in one critical
    section prevents duplicate/interleaved headers when several agents publish
    to a fresh inbox concurrently.
    """
    ensure_directory(path.parent)
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.chmod(path, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        chunks = [event.encode("utf-8")]
        if os.fstat(fd).st_size == 0:
            chunks.insert(0, header.encode("utf-8"))
        for data in chunks:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short write while appending mesh event")
                view = view[written:]
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)
