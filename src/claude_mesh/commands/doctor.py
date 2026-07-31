# src/claude_mesh/commands/doctor.py
from __future__ import annotations

import os
import shutil
from importlib import metadata
from pathlib import Path

from claude_mesh import __version__
from claude_mesh.config import ConfigError, find_config, load_config
from claude_mesh.ftai import FTAIParseError, parse_file
from claude_mesh.task_store import TaskStore, task_db_path


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

    failures = 0
    home = Path.home()
    group_dir = home / ".claude-mesh" / "groups" / cfg.mesh_group
    try:
        group_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(group_dir, 0o700)
        writable = os.access(group_dir, os.R_OK | os.W_OK | os.X_OK)
    except OSError as exc:
        writable = False
        _check("group dir accessible", False, f"{group_dir}: {exc}")
    else:
        _check("group dir accessible", writable, str(group_dir))
    failures += int(not writable)

    inbox = group_dir / f"{cfg.mesh_peer}.ftai"
    inbox_ok = not inbox.exists() or (inbox.is_file() and os.access(inbox, os.R_OK))
    detail = f"{inbox} ({'fresh' if not inbox.exists() else 'present'})"
    _check("own inbox readable", inbox_ok, detail)
    failures += int(not inbox_ok)

    if inbox.exists() and inbox_ok:
        try:
            parse_file(inbox)
        except (FTAIParseError, OSError) as exc:
            _check("own inbox parses", False, str(exc))
            failures += 1
        else:
            _check("own inbox parses", True)
        mode = inbox.stat().st_mode & 0o777
        secure_mode = mode & 0o077 == 0
        _check("own inbox permissions", secure_mode, f"{mode:04o}; expected 0600")
        failures += int(not secure_mode)

    roster_ok = bool(cfg.other_peers())
    _check(
        "peer routing resolves",
        roster_ok,
        f"self={cfg.mesh_peer} targets={cfg.other_peers()}",
    )
    failures += int(not roster_ok)

    cli = shutil.which("claude-mesh")
    _check("CLI available", cli is not None, cli or "not found on PATH")
    failures += int(cli is None)
    _check("source version", True, __version__)
    try:
        installed_version = metadata.version("claude-mesh")
    except metadata.PackageNotFoundError:
        installed_version = None
    distribution_ok = installed_version in {None, __version__}
    _check(
        "Python distribution version",
        distribution_ok,
        installed_version or "source checkout (not installed)",
    )
    failures += int(not distribution_ok)

    cache_root = home / ".claude" / "plugins" / "cache" / "folktechai" / "claude-mesh"
    cached_versions = sorted(
        p.name for p in cache_root.iterdir() if p.is_dir()
    ) if cache_root.is_dir() else []
    cache_ok = not cached_versions or __version__ in cached_versions
    _check(
        "Claude plugin version",
        cache_ok,
        f"running={__version__} cached={cached_versions or ['not installed']}",
    )
    failures += int(not cache_ok)

    database = task_db_path(home, cfg.mesh_group)
    if database.exists():
        try:
            with TaskStore(database) as store:
                integrity = store.conn.execute("PRAGMA integrity_check").fetchone()[0]
        except (OSError, ValueError) as exc:
            _check("task ledger integrity", False, str(exc))
            failures += 1
        else:
            ledger_ok = integrity == "ok"
            _check("task ledger integrity", ledger_ok, str(integrity))
            failures += int(not ledger_ok)

    return 1 if failures else 0
