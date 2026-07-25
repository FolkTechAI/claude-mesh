# src/claude_mesh/stdin_util.py
"""Non-blocking stdin payload reader.

Hook wrappers pipe a JSON event envelope on stdin. The naive
`sys.stdin.read()` blocks forever when stdin is an inherited pipe that
never reaches EOF (backgrounded shells, some harness spawn paths), which
hangs the CLI and — through it — the agent turn.

Every command reads its payload through `read_hook_payload`, which is
bounded by a wall-clock deadline and always returns.
"""

from __future__ import annotations

import io
import json
import os
import select
import sys
import time
from typing import Any

# Hook envelopes are small; anything larger is truncated rather than buffered.
MAX_PAYLOAD_BYTES = 1024 * 1024
DEFAULT_TIMEOUT_S = 0.25


def read_stdin_bounded(timeout: float = DEFAULT_TIMEOUT_S) -> str:
    """Read whatever is available on stdin, giving up after `timeout` seconds.

    Returns "" when stdin is a TTY, closed, unreadable, or produces nothing
    before the deadline. Never raises, never blocks indefinitely.
    """
    stream = sys.stdin
    if stream is None:
        return ""
    try:
        if stream.closed or stream.isatty():
            return ""
        fd = stream.fileno()
    except (AttributeError, ValueError, OSError, io.UnsupportedOperation):
        return ""

    deadline = time.monotonic() + max(0.0, timeout)
    chunks: list[bytes] = []
    total = 0

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            ready, _, _ = select.select([fd], [], [], remaining)
        except (OSError, ValueError):
            break
        if not ready:
            break  # nothing pending — treat as "no payload"
        try:
            chunk = os.read(fd, 65536)
        except (BlockingIOError, InterruptedError):
            continue
        except OSError:
            break
        if not chunk:
            break  # EOF
        chunks.append(chunk)
        total += len(chunk)
        if total >= MAX_PAYLOAD_BYTES:
            break

    if not chunks:
        return ""
    return b"".join(chunks).decode("utf-8", errors="replace")


def read_hook_payload(timeout: float = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """Read and parse a JSON hook envelope from stdin. Always returns a dict."""
    raw = read_stdin_bounded(timeout).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
