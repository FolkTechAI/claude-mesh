# src/claude_mesh/commands/mark_read.py
from __future__ import annotations

import json
import sys
from pathlib import Path

from claude_mesh.config import find_config, load_config
from claude_mesh.drain import mark_read, pending_marker_path, read_marker_path
from claude_mesh.mode import Mode, detect_mode
from claude_mesh.storage import resolve_knowledge_path
from claude_mesh.stdin_util import read_hook_payload


def _payload() -> dict:
    return read_hook_payload()


def run() -> int:
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

    marker = read_marker_path(log)

    # Advance to the high-water mark of the last drain when we have one, so a
    # message that arrived mid-turn is not consumed without ever being shown.
    # Falling back to wall-clock now is correct only for an explicit
    # "mark everything read" with no preceding drain.
    through = None
    pending = pending_marker_path(marker)
    try:
        if pending.exists():
            through = pending.read_text(encoding="utf-8").strip() or None
    except OSError:
        through = None

    mark_read(marker, now=through)

    try:
        pending.unlink(missing_ok=True)
    except OSError:
        pass
    return 0
