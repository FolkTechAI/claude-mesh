"""Sync command: push and pull inbox files with remote peers."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from claude_mesh.config import ConfigError, find_config, load_config
from claude_mesh.remote import RemoteSyncError, sync_all_remote_peers, sync_peer


def run_sync(
    peer: str | None = None,
    watch: bool = False,
    interval: int = 30,
) -> int:
    """Sync inbox files with remote peers.

    Args:
        peer: Specific peer to sync with (or None for all)
        watch: Keep running and sync periodically
        interval: Seconds between syncs in watch mode

    Returns:
        Exit code (0 = success)
    """
    cwd = Path.cwd()
    home = Path.home()

    cfg_path = find_config(cwd)
    if cfg_path is None:
        print("claude-mesh sync: no .claude-mesh config found", file=sys.stderr)
        return 1

    try:
        config = load_config(cfg_path)
    except ConfigError as exc:
        print(f"claude-mesh sync: config error: {exc}", file=sys.stderr)
        return 1

    if not config.remote_peers:
        print("claude-mesh sync: no remote peers configured", file=sys.stderr)
        return 0

    if peer and peer not in config.remote_peers:
        print(
            f"claude-mesh sync: peer {peer!r} is not a remote peer",
            file=sys.stderr,
        )
        return 1

    while True:
        try:
            if peer:
                # Sync one specific peer
                sync_peer(peer, config, home)
                if not watch:
                    print(f"Synced with {peer}")
            else:
                # Sync all remote peers
                results = sync_all_remote_peers(config, home)
                failures = [p for p, r in results.items() if not r["success"]]
                
                if not watch:
                    if failures:
                        print(f"Sync completed with errors: {', '.join(failures)}")
                        for p in failures:
                            print(f"  {p}: {results[p]['error']}", file=sys.stderr)
                        return 1
                    else:
                        print(f"Synced with all remote peers: {', '.join(results.keys())}")
                elif failures:
                    print(
                        f"[{time.strftime('%H:%M:%S')}] Sync errors: {', '.join(failures)}",
                        file=sys.stderr,
                    )

        except RemoteSyncError as exc:
            print(f"claude-mesh sync: {exc}", file=sys.stderr)
            if not watch:
                return 1

        if not watch:
            break

        time.sleep(interval)

    return 0
