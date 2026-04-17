# src/claude_mesh/commands/drain.py
from __future__ import annotations

import json
import sys
from pathlib import Path

from claude_mesh.config import find_config, load_config
from claude_mesh.drain import drain_unread, read_marker_path
from claude_mesh.mode import Mode, detect_mode
from claude_mesh.storage import resolve_knowledge_path


def _payload() -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def run_prompt_mode(log: Path) -> int:
    """Print unread events formatted as a prompt-friendly summary."""
    from claude_mesh.drain import drain_unread, read_marker_path
    marker = read_marker_path(log)
    out = drain_unread(log, marker)
    if out:
        sys.stdout.write("## Unread mesh events\n\n")
        sys.stdout.write(out + "\n")
    return 0


def run(fmt: str = "ftai") -> int:
    payload = _payload()
    mode = detect_mode(payload)
    home = Path.home()
    cwd = Path.cwd()
    if mode == Mode.STANDALONE:
        cfg_path = find_config(cwd)
        if cfg_path is None:
            return 0
        cfg = load_config(cfg_path)
        log = resolve_knowledge_path(mode, payload, cfg, home)
    else:
        log = resolve_knowledge_path(mode, payload, None, home)

    if fmt == "prompt":
        return run_prompt_mode(log)

    marker = read_marker_path(log)
    out = drain_unread(log, marker)
    if out:
        sys.stdout.write(out + "\n")
    return 0
