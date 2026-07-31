"""Low-cost inbox wake signal.

This command watches local metadata only. It does not call a model, consume an
event, or mark anything read. Adapters can block on it and wake their own agent
runtime only when unread work actually exists.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from claude_mesh.commands.drain import count_events
from claude_mesh.drain import drain_unread, read_marker_path
from claude_mesh.ftai import FTAIParseError
from claude_mesh.mode import Mode
from claude_mesh.publish import PublishError, load_current_config
from claude_mesh.storage import resolve_knowledge_path


def run(timeout: float = 30.0, interval: float = 0.25, as_json: bool = False) -> int:
    if timeout < 0:
        print("claude-mesh watch: timeout must be >= 0", file=sys.stderr)
        return 2
    if interval < 0.05 or interval > 10:
        print("claude-mesh watch: interval must be between 0.05 and 10", file=sys.stderr)
        return 2
    try:
        cfg = load_current_config(Path.cwd())
        inbox = resolve_knowledge_path(Mode.STANDALONE, {}, cfg, Path.home())
        marker = read_marker_path(inbox)
        deadline = None if timeout == 0 else time.monotonic() + timeout
        last_signature: tuple[int, int] | None = None
        while deadline is None or time.monotonic() < deadline:
            try:
                stat = inbox.stat()
                signature = (stat.st_size, stat.st_mtime_ns)
            except FileNotFoundError:
                signature = (0, 0)
            if signature != last_signature:
                last_signature = signature
                unread = drain_unread(inbox, marker, participant=cfg.mesh_peer)
                count = count_events(unread)
                if count:
                    if as_json:
                        print(
                            json.dumps(
                                {
                                    "group": cfg.mesh_group,
                                    "peer": cfg.mesh_peer,
                                    "unread": count,
                                    "inbox": str(inbox),
                                },
                                sort_keys=True,
                            )
                        )
                    else:
                        print(
                            f"mesh-wake group={cfg.mesh_group} "
                            f"peer={cfg.mesh_peer} unread={count}"
                        )
                    return 0
            time.sleep(interval)
        return 0
    except (PublishError, FTAIParseError, OSError) as exc:
        print(f"claude-mesh watch: {exc}", file=sys.stderr)
        return 1
