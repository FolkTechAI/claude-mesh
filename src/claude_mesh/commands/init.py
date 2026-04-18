# src/claude_mesh/commands/init.py
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def _slug(name: str) -> str:
    """Normalize a string into the [a-z0-9-] alphabet the config validator accepts."""
    s = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return s or "peer"


def run(
    peer: str | None = None,
    group: str | None = None,
    other: str | None = None,
) -> int:
    cwd = Path.cwd()
    target = cwd / ".claude-mesh"
    if target.exists():
        print(f"claude-mesh init: {target} already exists. Not overwriting.", file=sys.stderr)
        return 1

    # Resolve peer: explicit > interactive prompt > current dir name
    if peer is None and sys.stdin.isatty():
        try:
            peer = input(f"Peer name (default {cwd.name}): ").strip()
        except EOFError:
            peer = ""
    if not peer:
        peer = cwd.name
    peer = _slug(peer)

    # Resolve other peer: explicit > env > interactive prompt > default of 'peer'
    if other is None:
        other = os.environ.get("CLAUDE_MESH_OTHER")
    if other is None and sys.stdin.isatty():
        try:
            other = input(
                f"Other peer name (the session this one coordinates with) [default: peer]: "
            ).strip()
        except EOFError:
            other = ""
    if not other:
        other = "peer"
    other = _slug(other)
    if other == peer:
        print(
            f"claude-mesh init: --other ({other!r}) must differ from --peer ({peer!r})",
            file=sys.stderr,
        )
        return 2

    # Resolve group: explicit > env > interactive prompt > {peer}-{other}
    if group is None:
        group = os.environ.get("CLAUDE_MESH_GROUP")
    if group is None and sys.stdin.isatty():
        try:
            group = input(
                f"Group name [default: {peer}-{other}]: "
            ).strip()
        except EOFError:
            group = ""
    if not group:
        group = f"{peer}-{other}"
    group = _slug(group)

    # Validate: the explicit `mesh_peers` we write will always pair correctly with the group,
    # but we also want the legacy prefix/suffix-match path to work if someone removes the list.
    # Require group to start or end with one of the peer names, so both routes succeed.
    if not (
        group.startswith(f"{peer}-") or group.endswith(f"-{peer}")
        or group.startswith(f"{other}-") or group.endswith(f"-{other}")
    ):
        print(
            f"claude-mesh init: group {group!r} does not contain either peer name "
            f"({peer!r} or {other!r}). Choose a group like '{peer}-{other}'.",
            file=sys.stderr,
        )
        return 2

    target.write_text(
        f"mesh_group: {group}\n"
        f"mesh_peer: {peer}\n"
        "mesh_peers:\n"
        f"  - {peer}\n"
        f"  - {other}\n"
        "cross_cutting_paths:\n"
        "  - src/**\n"
    )
    print(f"claude-mesh: wrote {target}")
    print(f"  group={group} peer={peer} other={other}")
    print("  edit cross_cutting_paths to narrow the scope.")
    return 0
