# src/claude_mesh/commands/task_event.py
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from claude_mesh.config import NAME_PATTERN, find_config, load_config
from claude_mesh.events import TaskEvent, header_block, render_event
from claude_mesh.identity import new_event_id, utc_now
from claude_mesh.mode import Mode, detect_mode
from claude_mesh.stdin_util import read_hook_payload
from claude_mesh.storage import append_event, resolve_knowledge_path


def run(
    task_id: str,
    subject: str,
    status: str,
    to: str | None = None,
    description: str | None = None,
) -> int:
    payload: dict[str, Any] = read_hook_payload()

    mode = detect_mode(payload)
    home = Path.home()
    cwd = Path.cwd()

    if mode == Mode.TEAM:
        from_ = str(payload.get("teammate_name", "unknown"))
        team_name = str(payload.get("team_name", ""))
        paths = [resolve_knowledge_path(mode, payload, None, home)]
        group_or_team = team_name
        participants = [from_]
    else:
        cfg_path = find_config(cwd)
        if cfg_path is None:
            return 0
        cfg = load_config(cfg_path)
        if to is not None:
            if not NAME_PATTERN.fullmatch(to):
                print(
                    f"claude-mesh task-event: invalid peer name {to!r}",
                    file=sys.stderr,
                )
                return 1
            if cfg.mesh_peers and to not in cfg.mesh_peers:
                print(
                    f"claude-mesh task-event: unknown peer {to!r}; "
                    f"mesh_peers is {cfg.mesh_peers!r}",
                    file=sys.stderr,
                )
                return 1
            if to == cfg.mesh_peer:
                print("claude-mesh task-event: refusing to send to self", file=sys.stderr)
                return 1
            recipients = [to]
        else:
            recipients = cfg.other_peers()
        if not recipients:
            print(
                "claude-mesh task-event: no other peers resolved; declare mesh_peers",
                file=sys.stderr,
            )
            return 1
        paths = [
            resolve_knowledge_path(mode, payload, cfg, home, writing_to_peer=peer)
            for peer in recipients
        ]
        from_ = cfg.mesh_peer
        group_or_team = cfg.mesh_group
        participants = cfg.mesh_peers or [cfg.mesh_peer, *recipients]

    event = TaskEvent(
        from_=from_,
        timestamp=utc_now(),
        id=task_id,
        subject=subject,
        status=status,
        description=description,
        to=to,
        event_id=new_event_id(),
    )
    rendered = render_event(event)
    for path in paths:
        append_event(path, header_block(group_or_team, participants), rendered)
    return 0
