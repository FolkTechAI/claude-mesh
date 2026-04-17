# src/claude_mesh/commands/subagent_turn.py
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

from claude_mesh.events import MessageEvent, render_event, header_block
from claude_mesh.mode import Mode, detect_mode
from claude_mesh.sanitize import MAX_SUMMARY_CHARS, sanitize_summary
from claude_mesh.storage import atomic_append, resolve_knowledge_path

BOILERPLATE_PATTERNS = {"done", "done.", "ok", "ok.", "acknowledged"}
MIN_LOG_LENGTH = 50


def run() -> int:
    if sys.stdin.isatty():
        return 0
    try:
        payload: dict[str, Any] = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
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
    if not path.exists():
        atomic_append(path, header_block(team, [from_]))
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    event = MessageEvent(from_=from_, timestamp=ts, body=clean)
    atomic_append(path, render_event(event))
    return 0
