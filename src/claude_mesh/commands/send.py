# src/claude_mesh/commands/send.py
from __future__ import annotations

import datetime as _dt
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
from claude_mesh.stdin_util import read_hook_payload
from claude_mesh.storage import atomic_append, resolve_knowledge_path


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
        teammate = str(hook_payload.get("teammate_name", "unknown"))
        targets = [resolve_knowledge_path(mode, hook_payload, config=None, home=home)]
        participants_from = teammate
        group_or_team = str(hook_payload.get("team_name", ""))
        participants = [teammate]
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

        others = cfg.other_peers()
        if to is not None:
            # Directed: validate against the declared roster so a typo is loud,
            # not a silently-created inbox nobody reads.
            if cfg.mesh_peers and to not in cfg.mesh_peers:
                print(
                    f"claude-mesh send: unknown peer {to!r}; "
                    f"mesh_peers is {cfg.mesh_peers!r}",
                    file=sys.stderr,
                )
                return 1
            if to == cfg.mesh_peer:
                print(
                    f"claude-mesh send: refusing to send to self ({to!r})",
                    file=sys.stderr,
                )
                return 1
            recipients = [to]
        else:
            # Broadcast: fan out to every other participant's inbox.
            recipients = others
            if not recipients:
                print(
                    "claude-mesh send: no other peers to send to; "
                    f"declare the roster as `mesh_peers: [{cfg.mesh_peer}, <other>]` "
                    "in .claude-mesh",
                    file=sys.stderr,
                )
                return 1

        targets = [
            resolve_knowledge_path(
                mode, hook_payload, config=cfg, home=home, writing_to_peer=peer
            )
            for peer in recipients
        ]
        participants_from = cfg.mesh_peer
        group_or_team = cfg.mesh_group
        participants = cfg.mesh_peers or [cfg.mesh_peer, *recipients]

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

    rendered = render_event(event)
    for path in targets:
        if not path.exists():
            atomic_append(path, header_block(group_or_team, participants))
        atomic_append(path, rendered)
    return 0


def run(text: str, kind: str, to: str | None) -> int:
    payload = read_hook_payload()
    home = Path.home()
    cwd = Path.cwd()
    return send_event(text=text, kind=kind, to=to, hook_payload=payload, home=home, cwd=cwd)
