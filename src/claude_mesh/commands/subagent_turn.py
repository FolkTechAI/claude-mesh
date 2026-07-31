# src/claude_mesh/commands/subagent_turn.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_mesh.events import MessageEvent, header_block, render_event
from claude_mesh.identity import new_event_id, utc_now
from claude_mesh.mode import Mode, detect_mode
from claude_mesh.sanitize import sanitize_summary
from claude_mesh.stdin_util import read_hook_payload
from claude_mesh.storage import append_event, resolve_knowledge_path

BOILERPLATE_PATTERNS = {"done", "done.", "ok", "ok.", "acknowledged"}
MIN_LOG_LENGTH = 50


def run() -> int:
    payload: dict[str, Any] = read_hook_payload()
    if not payload:
        return 0

    mode = detect_mode(payload)
    if mode != Mode.TEAM:
        return 0  # SubagentStop only relevant in team mode for v1

    msg = str(payload.get("last_assistant_message", "")).strip()
    if not msg or len(msg) < MIN_LOG_LENGTH or msg.lower() in BOILERPLATE_PATTERNS:
        return 0

    home = Path.home()
    team = str(payload.get("team_name", ""))
    from_ = str(payload.get("teammate_name") or payload.get("agent_type") or "unknown")
    path = resolve_knowledge_path(mode, payload, None, home)

    clean = sanitize_summary(msg)
    event = MessageEvent(
        from_=from_,
        timestamp=utc_now(),
        body=clean,
        event_id=new_event_id(),
    )
    append_event(path, header_block(team, [from_]), render_event(event))
    return 0
