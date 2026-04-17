# src/claude_mesh/commands/send.py
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from claude_mesh.config import ConfigError, find_config, load_config
from claude_mesh.events import (
    DecisionEvent,
    MessageEvent,
    NoteEvent,
    render_event,
    header_block,
)
from claude_mesh.mode import Mode, detect_mode
from claude_mesh.sanitize import SensitiveDataFilter, sanitize_body
from claude_mesh.storage import atomic_append, resolve_knowledge_path


def _read_hook_payload_from_stdin() -> dict[str, Any]:
    if sys.stdin.isatty():
        return {}
    try:
        data = sys.stdin.read()
        return json.loads(data) if data else {}
    except json.JSONDecodeError:
        return {}


def _iso_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def send_event(
    text: str,
    kind: str,
    to: str | None,
    hook_payload: dict[str, Any],
    home: Path,
    cwd: Path,
) -> int:
    mode = detect_mode(hook_payload)
    filter_ = SensitiveDataFilter()
    clean = sanitize_body(filter_.redact(text))
    ts = _iso_now()

    if mode == Mode.TEAM:
        team = str(hook_payload.get("team_name", ""))
        teammate = str(hook_payload.get("teammate_name", "unknown"))
        path = resolve_knowledge_path(mode, hook_payload, config=None, home=home)
        participants_from = teammate
    else:
        cfg_path = find_config(cwd)
        if cfg_path is None:
            print("claude-mesh send: no .claude-mesh config found", file=sys.stderr)
            return 1
        try:
            cfg = load_config(cfg_path)
        except ConfigError as exc:
            print(f"claude-mesh send: config error: {exc}", file=sys.stderr)
            return 1
        path = resolve_knowledge_path(
            mode, hook_payload, config=cfg, home=home, writing_to_peer=to
        )
        participants_from = cfg.mesh_peer

    if not path.exists():
        group_or_team = (
            str(hook_payload.get("team_name", ""))
            if mode == Mode.TEAM
            else getattr(cfg, "mesh_group", "unknown")
        )
        participants = (
            [str(hook_payload.get("teammate_name", ""))] if mode == Mode.TEAM else [cfg.mesh_peer]
        )
        atomic_append(path, header_block(group_or_team, participants))

    if kind == "message":
        event = MessageEvent(from_=participants_from, timestamp=ts, body=clean, to=to)
    elif kind == "note":
        event = NoteEvent(from_=participants_from, timestamp=ts, content=clean)
    elif kind == "decision":
        event = DecisionEvent(
            from_=participants_from, timestamp=ts, id="", title="", content=clean
        )
    else:
        print(f"claude-mesh send: unknown kind {kind}", file=sys.stderr)
        return 1

    atomic_append(path, render_event(event))
    return 0


def run(text: str, kind: str, to: str | None) -> int:
    payload = _read_hook_payload_from_stdin()
    home = Path.home()
    cwd = Path.cwd()
    return send_event(text=text, kind=kind, to=to, hook_payload=payload, home=home, cwd=cwd)
