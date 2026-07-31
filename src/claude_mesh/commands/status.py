# src/claude_mesh/commands/status.py
from __future__ import annotations

from pathlib import Path

from claude_mesh.commands.drain import count_events
from claude_mesh.config import ConfigError, find_config, load_config
from claude_mesh.drain import drain_unread, read_marker_path
from claude_mesh.ftai import FTAIParseError
from claude_mesh.mode import Mode
from claude_mesh.storage import resolve_knowledge_path


def run() -> int:
    home = Path.home()
    cwd = Path.cwd()
    cfg_path = find_config(cwd)
    if cfg_path is None:
        print("claude-mesh: inactive — no .claude-mesh config found from this directory.")
        return 0
    try:
        cfg = load_config(cfg_path)
    except ConfigError as exc:
        print(f"claude-mesh: config error at {cfg_path}: {exc}")
        return 1
    log = resolve_knowledge_path(Mode.STANDALONE, {}, cfg, home)
    marker = read_marker_path(log)
    try:
        unread = drain_unread(log, marker, participant=cfg.mesh_peer)
    except (FTAIParseError, OSError) as exc:
        print(f"claude-mesh: inbox error at {log}: {exc}")
        return 1
    unread_count = count_events(unread)
    roster = ",".join(cfg.mesh_peers) if cfg.mesh_peers else "(legacy inferred pair)"
    print(
        f"claude-mesh: group={cfg.mesh_group} peer={cfg.mesh_peer} "
        f"peers={roster} unread={unread_count} inbox={log}"
    )
    return 0
