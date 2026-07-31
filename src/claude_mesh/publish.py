"""Vendor-neutral standalone event publication."""

from __future__ import annotations

from pathlib import Path

from claude_mesh.config import (
    NAME_PATTERN,
    ConfigError,
    MeshConfig,
    find_config,
    load_config,
)
from claude_mesh.events import Event, header_block, render_event
from claude_mesh.mode import Mode
from claude_mesh.storage import append_event, resolve_knowledge_path


class PublishError(RuntimeError):
    """Raised when an event cannot be routed safely."""


def load_current_config(cwd: Path) -> MeshConfig:
    path = find_config(cwd)
    if path is None:
        raise PublishError("no .claude-mesh config found")
    try:
        return load_config(path)
    except ConfigError as exc:
        raise PublishError(f"config error: {exc}") from exc


def publish_event(
    event: Event,
    *,
    config: MeshConfig,
    home: Path,
    to: str | None = None,
) -> list[Path]:
    """Publish to one target or fan out to every peer except the sender."""
    if to is not None:
        if not NAME_PATTERN.fullmatch(to):
            raise PublishError(f"invalid peer name {to!r}")
        if config.mesh_peers and to not in config.mesh_peers:
            raise PublishError(
                f"unknown peer {to!r}; mesh_peers is {config.mesh_peers!r}"
            )
        if to == config.mesh_peer:
            raise PublishError(f"refusing to send to self ({to!r})")
        recipients = [to]
    else:
        recipients = config.other_peers()
    if not recipients:
        raise PublishError("no other peers resolved; declare mesh_peers")

    paths = [
        resolve_knowledge_path(
            Mode.STANDALONE,
            {},
            config,
            home,
            writing_to_peer=peer,
        )
        for peer in recipients
    ]
    participants = config.mesh_peers or [config.mesh_peer, *recipients]
    header = header_block(config.mesh_group, participants)
    rendered = render_event(event)
    for path in paths:
        append_event(path, header, rendered)
    return paths
