# src/claude_mesh/commands/send.py
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from claude_mesh.config import NAME_PATTERN, ConfigError, find_config, load_config
from claude_mesh.events import (
    DecisionEvent,
    MessageEvent,
    NoteEvent,
    header_block,
    render_event,
)
from claude_mesh.identity import new_event_id, utc_now
from claude_mesh.mode import Mode, detect_mode
from claude_mesh.sanitize import SensitiveDataFilter, sanitize_body
from claude_mesh.stdin_util import read_hook_payload
from claude_mesh.storage import append_event, resolve_knowledge_path


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
    ts = utc_now()
    event_id = new_event_id()

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
            if not NAME_PATTERN.fullmatch(to):
                print(
                    f"claude-mesh send: invalid peer name {to!r}",
                    file=sys.stderr,
                )
                return 1
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
        event = MessageEvent(
            from_=participants_from,
            timestamp=ts,
            body=clean,
            to=to,
            event_id=event_id,
        )
    elif kind == "note":
        event = NoteEvent(
            from_=participants_from,
            timestamp=ts,
            content=clean,
            event_id=event_id,
        )
    elif kind == "decision":
        event = DecisionEvent(
            from_=participants_from,
            timestamp=ts,
            id="",
            title="",
            content=clean,
            event_id=event_id,
        )
    else:
        print(f"claude-mesh send: unknown kind {kind}", file=sys.stderr)
        return 1

    rendered = render_event(event)
    for path in targets:
        append_event(path, header_block(group_or_team, participants), rendered)
    return 0


def run(text: str, kind: str, to: str | None) -> int:
    payload = read_hook_payload()
    home = Path.home()
    cwd = Path.cwd()
    return send_event(text=text, kind=kind, to=to, hook_payload=payload, home=home, cwd=cwd)
