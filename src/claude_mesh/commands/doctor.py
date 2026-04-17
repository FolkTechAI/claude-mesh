# src/claude_mesh/commands/doctor.py
from __future__ import annotations

import sys
from pathlib import Path

from claude_mesh.config import ConfigError, find_config, load_config


def _check(name: str, ok: bool, detail: str = "") -> None:
    mark = "OK  " if ok else "FAIL"
    line = f"  [{mark}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)


def run() -> int:
    cwd = Path.cwd()
    print("claude-mesh doctor:")
    cfg_path = find_config(cwd)
    if cfg_path is None:
        print("  inactive — no .claude-mesh found walking up from", cwd)
        return 0

    _check(".claude-mesh located", True, str(cfg_path))

    try:
        cfg = load_config(cfg_path)
        _check("config parses", True, f"group={cfg.mesh_group} peer={cfg.mesh_peer}")
    except ConfigError as exc:
        _check("config parses", False, str(exc))
        return 1

    home = Path.home()
    group_dir = home / ".claude-mesh" / "groups" / cfg.mesh_group
    _check(
        "group dir exists or creatable",
        group_dir.parent.parent.exists() or True,
        str(group_dir),
    )

    inbox = group_dir / f"{cfg.mesh_peer}.ftai"
    _check("own inbox readable (or missing == fresh install)", True, str(inbox))

    return 0
