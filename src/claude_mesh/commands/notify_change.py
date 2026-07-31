# src/claude_mesh/commands/notify_change.py
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from claude_mesh.config import find_config, load_config
from claude_mesh.events import FileChangeEvent, header_block, render_event
from claude_mesh.identity import new_event_id, utc_now
from claude_mesh.mode import Mode, detect_mode
from claude_mesh.pathval import PathValidationError, path_matches_any_glob, validate_relative_path
from claude_mesh.sanitize import SensitiveDataFilter, sanitize_summary
from claude_mesh.stdin_util import read_hook_payload
from claude_mesh.storage import append_event, resolve_knowledge_path


def _git_diff_stat(path: str, cwd: Path) -> str:
    git = shutil.which("git")
    if git is None:
        return ""
    try:
        r = subprocess.run(  # noqa: S603 - fixed executable and argv; no shell
            [git, "-C", str(cwd), "diff", "--stat", "--", path],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return r.stdout.strip().split("\n")[-1] if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


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

        # N-way: publish to EVERY other participant's inbox. The v1 code called
        # other_peer(), which returned None for 3+ peers and dropped the event
        # silently — a mesh that looked wired and published nothing.
        others = cfg.other_peers()
        if not others:
            print(
                "claude-mesh notify-change: no other peers resolved; "
                f"declare the roster as `mesh_peers: [{cfg.mesh_peer}, <other>]` "
                "in .claude-mesh",
                file=sys.stderr,
            )
            return 0
        targets = [
            resolve_knowledge_path(
                mode, hook_payload, config=cfg, home=home, writing_to_peer=peer
            )
            for peer in others
        ]
        from_ = cfg.mesh_peer
        group_or_team = cfg.mesh_group
        participants = cfg.mesh_peers or [cfg.mesh_peer, *others]
    else:
        targets = [resolve_knowledge_path(mode, hook_payload, config=None, home=home)]
        from_ = str(hook_payload.get("teammate_name", "unknown"))
        group_or_team = str(hook_payload.get("team_name", "unknown"))
        participants = [from_]

    summary = summary_override or _git_diff_stat(path, cwd)
    clean_summary = sanitize_summary(SensitiveDataFilter().redact(summary))

    event = FileChangeEvent(
        from_=from_,
        timestamp=utc_now(),
        path=path,
        tool=tool,
        summary=clean_summary or "(no git summary available)",
        event_id=new_event_id(),
    )
    rendered = render_event(event)

    for target_path in targets:
        append_event(
            target_path,
            header_block(group_or_team, participants),
            rendered,
        )
    return 0


def run(path: str, tool: str) -> int:
    return notify_change(
        path=path,
        tool=tool,
        summary_override=None,
        hook_payload=read_hook_payload(),
        home=Path.home(),
        cwd=Path.cwd(),
    )
