# src/claude_mesh/commands/task_event.py
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

from claude_mesh.config import find_config, load_config
from claude_mesh.events import TaskEvent, render_event, header_block
from claude_mesh.mode import Mode, detect_mode
from claude_mesh.storage import atomic_append, resolve_knowledge_path


def _iso_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(task_id: str, subject: str, status: str) -> int:
    if sys.stdin.isatty():
        payload: dict[str, Any] = {}
    else:
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            payload = {}

    mode = detect_mode(payload)
    home = Path.home()
    cwd = Path.cwd()

    if mode == Mode.TEAM:
        from_ = str(payload.get("teammate_name", "unknown"))
        team_name = str(payload.get("team_name", ""))
        path = resolve_knowledge_path(mode, payload, None, home)
        group_or_team = team_name
        participants = [from_]
    else:
        cfg_path = find_config(cwd)
        if cfg_path is None:
            return 0
        cfg = load_config(cfg_path)
        parts = cfg.mesh_group.split("-")
        other = parts[0] if parts[1] == cfg.mesh_peer else parts[1]
        path = resolve_knowledge_path(mode, payload, cfg, home, writing_to_peer=other)
        from_ = cfg.mesh_peer
        group_or_team = cfg.mesh_group
        participants = parts

    if not path.exists():
        atomic_append(path, header_block(group_or_team, participants))
    event = TaskEvent(from_=from_, timestamp=_iso_now(), id=task_id, subject=subject, status=status)
    atomic_append(path, render_event(event))
    return 0
