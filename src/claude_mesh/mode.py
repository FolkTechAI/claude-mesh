# src/claude_mesh/mode.py
"""Mode detection from Claude Code hook payloads."""

from __future__ import annotations

from enum import Enum
from typing import Any


class Mode(Enum):
    TEAM = "team"
    STANDALONE = "standalone"


def detect_mode(payload: dict[str, Any]) -> Mode:
    """If payload carries team_name, we're in Agent Teams mode. Otherwise standalone."""
    if payload.get("team_name"):
        return Mode.TEAM
    return Mode.STANDALONE
