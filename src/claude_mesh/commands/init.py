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


def run(peer: str | None = None, group: str | None = None) -> int:
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

    # Resolve group: explicit > env > interactive prompt > default of {peer}-peer
    # Default pattern keeps the {peer_a}-{peer_b} convention so the other side is
    # unambiguous once a second session initializes with --peer peer or similar.
    if group is None:
        group = os.environ.get("CLAUDE_MESH_GROUP")
    if group is None and sys.stdin.isatty():
        try:
            group = input(
                f"Group name (e.g. backend-frontend) [default: {peer}-peer]: "
            ).strip()
        except EOFError:
            group = ""
    if not group:
        group = f"{peer}-peer"
    group = _slug(group)

    target.write_text(
        f"mesh_group: {group}\n"
        f"mesh_peer: {peer}\n"
        "cross_cutting_paths:\n"
        "  - src/**\n"
    )
    print(f"claude-mesh: wrote {target}")
    print(f"  group={group} peer={peer}")
    print("  edit cross_cutting_paths to narrow the scope.")
    return 0
