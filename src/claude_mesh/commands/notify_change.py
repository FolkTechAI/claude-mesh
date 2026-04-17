# src/claude_mesh/commands/notify_change.py
from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from claude_mesh.config import find_config, load_config
from claude_mesh.events import FileChangeEvent, render_event, header_block
from claude_mesh.mode import Mode, detect_mode
from claude_mesh.pathval import PathValidationError, path_matches_any_glob, validate_relative_path
from claude_mesh.sanitize import SensitiveDataFilter, sanitize_summary
from claude_mesh.storage import atomic_append, resolve_knowledge_path


def _git_diff_stat(path: str, cwd: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), "diff", "--stat", "--", path],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return r.stdout.strip().split("\n")[-1] if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _iso_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def notify_change(
    path: str,
    tool: str,
    summary_override: str | None,
    hook_payload: dict[str, Any],
    home: Path,
    cwd: Path,
) -> int:
    try:
        validate_relative_path(path)
    except PathValidationError as exc:
        print(f"claude-mesh notify-change: rejecting path: {exc}", file=sys.stderr)
        return 0  # hooks never block

    mode = detect_mode(hook_payload)

    if mode == Mode.STANDALONE:
        cfg_path = find_config(cwd)
        if cfg_path is None:
            return 0  # inactive
        cfg = load_config(cfg_path)
        if cfg.cross_cutting_paths and not path_matches_any_glob(path, cfg.cross_cutting_paths):
            return 0  # not cross-cutting
        # In standalone pairs v1, write to THE OTHER peer's inbox.
        # v1 simplification: if there are exactly 2 peers, the other peer's name is inferred
        # from the group name pattern "{peer_a}-{peer_b}"; otherwise require an explicit peers list
        # in config (deferred to v2).
        parts = cfg.mesh_group.split("-")
        if len(parts) != 2 or cfg.mesh_peer not in parts:
            print(
                "claude-mesh notify-change: cannot infer peer from group name; "
                f"group={cfg.mesh_group!r} must follow {{peer_a}}-{{peer_b}} convention",
                file=sys.stderr,
            )
            return 0
        other = parts[0] if parts[1] == cfg.mesh_peer else parts[1]
        target_path = resolve_knowledge_path(
            mode, hook_payload, config=cfg, home=home, writing_to_peer=other
        )
        from_ = cfg.mesh_peer
        group_or_team = cfg.mesh_group
        participants = parts
    else:
        target_path = resolve_knowledge_path(mode, hook_payload, config=None, home=home)
        from_ = str(hook_payload.get("teammate_name", "unknown"))
        group_or_team = str(hook_payload.get("team_name", "unknown"))
        participants = [from_]

    summary = summary_override or _git_diff_stat(path, cwd)
    clean_summary = sanitize_summary(SensitiveDataFilter().redact(summary))

    if not target_path.exists():
        atomic_append(target_path, header_block(group_or_team, participants))

    event = FileChangeEvent(
        from_=from_,
        timestamp=_iso_now(),
        path=path,
        tool=tool,
        summary=clean_summary or "(no git summary available)",
    )
    atomic_append(target_path, render_event(event))
    return 0


def _read_payload() -> dict[str, Any]:
    if sys.stdin.isatty():
        return {}
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def run(path: str, tool: str) -> int:
    return notify_change(
        path=path,
        tool=tool,
        summary_override=None,
        hook_payload=_read_payload(),
        home=Path.home(),
        cwd=Path.cwd(),
    )
