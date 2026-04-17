# src/claude_mesh/commands/init.py
from __future__ import annotations

import os
import sys
from pathlib import Path


def run(peer: str | None = None) -> int:
    cwd = Path.cwd()
    target = cwd / ".claude-mesh"
    if target.exists():
        print(f"claude-mesh init: {target} already exists. Not overwriting.", file=sys.stderr)
        return 1

    group = os.environ.get("CLAUDE_MESH_GROUP")
    if group is None and sys.stdin.isatty():
        group = input("Group name (e.g. vault-brain): ").strip()
    if not group:
        print("claude-mesh init: no group name provided.", file=sys.stderr)
        return 1

    peer_name = peer
    if peer_name is None and sys.stdin.isatty():
        peer_name = input(f"Peer name (default {cwd.name}): ").strip() or cwd.name
    if not peer_name:
        peer_name = cwd.name

    target.write_text(
        f"mesh_group: {group}\n"
        f"mesh_peer: {peer_name}\n"
        "cross_cutting_paths:\n"
        "  - src/**\n"
    )
    print(f"claude-mesh: wrote {target}")
    print(f"  group={group} peer={peer_name}")
    print("  edit cross_cutting_paths to narrow the scope.")
    return 0
