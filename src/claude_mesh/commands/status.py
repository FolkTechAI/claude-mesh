# src/claude_mesh/commands/status.py
from __future__ import annotations

from pathlib import Path

from claude_mesh.config import ConfigError, find_config, load_config
from claude_mesh.drain import drain_unread, read_marker_path
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
    unread = drain_unread(log, marker)
    unread_count = unread.count("@message") + unread.count("@file_change") + unread.count("@task")
    print(
        f"claude-mesh: group={cfg.mesh_group} peer={cfg.mesh_peer} unread={unread_count}"
    )
    return 0
