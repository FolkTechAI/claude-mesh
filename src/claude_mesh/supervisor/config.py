"""Supervisor TOML configuration and validation."""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

from claude_mesh.config import NAME_PATTERN


class SupervisorConfigError(ValueError):
    """Raised when supervisor configuration is unsafe or incomplete."""


VALID_MODES = {"observe", "approval", "automatic"}
VALID_ROLES = {"worker", "critic", "verifier"}
VALID_VENDORS = {"claude", "codex", "grok", "hermes", "command"}


@dataclass(frozen=True)
class WorkerConfig:
    name: str
    vendor: str
    roles: tuple[str, ...]
    capabilities: tuple[str, ...]
    executable: str
    model: str | None = None
    enabled: bool = True
    timeout_seconds: int = 900
    max_output_bytes: int = 1_048_576
    argv: tuple[str, ...] = ()


@dataclass(frozen=True)
class SupervisorConfig:
    group: str
    peer: str
    mode: str
    allowed_workspace_roots: tuple[Path, ...]
    workers: dict[str, WorkerConfig]
    operator: str = "operator"
    poll_interval_seconds: float = 2.0
    lease_seconds: int = 1800
    max_review_rounds: int = 2
    max_concurrent_runs: int = 1
    max_run_cost_usd: float = 10.0
    require_cross_vendor_review: bool = True
    require_distinct_verifier: bool = True
    automatic_max_risk: str = "low"
    publish_receipts: bool = True


def default_config_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".claude-mesh" / "supervisor.toml"


def _resolve_executable(vendor: str, configured: str | None) -> str:
    if configured:
        path = Path(configured).expanduser()
        if path.is_absolute():
            return str(path)
        resolved = shutil.which(configured)
        if resolved:
            return resolved
        raise SupervisorConfigError(f"executable not found: {configured}")
    if vendor == "codex":
        app_binary = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
        if app_binary.is_file() and os.access(app_binary, os.X_OK):
            return str(app_binary)
    resolved = shutil.which(vendor)
    if not resolved:
        raise SupervisorConfigError(f"no executable found for vendor {vendor!r}")
    return resolved


def load_supervisor_config(path: Path) -> SupervisorConfig:
    if not path.is_file():
        raise SupervisorConfigError(f"supervisor config not found: {path}")
    if path.stat().st_size > 128 * 1024:
        raise SupervisorConfigError("supervisor config exceeds 128 KiB")
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    supervisor = data.get("supervisor")
    if not isinstance(supervisor, dict):
        raise SupervisorConfigError("missing [supervisor] table")
    group = str(supervisor.get("group", ""))
    peer = str(supervisor.get("peer", "supervisor"))
    operator = str(supervisor.get("operator", "operator"))
    mode = str(supervisor.get("mode", "observe"))
    if not NAME_PATTERN.fullmatch(group):
        raise SupervisorConfigError("supervisor.group must be a valid mesh name")
    if not NAME_PATTERN.fullmatch(peer):
        raise SupervisorConfigError("supervisor.peer must be a valid mesh peer")
    if not NAME_PATTERN.fullmatch(operator):
        raise SupervisorConfigError("supervisor.operator must be a valid mesh peer")
    if mode not in VALID_MODES:
        raise SupervisorConfigError(f"mode must be one of {sorted(VALID_MODES)}")

    roots_raw = supervisor.get("allowed_workspace_roots", [])
    if not isinstance(roots_raw, list) or not roots_raw:
        raise SupervisorConfigError("allowed_workspace_roots must be a non-empty list")
    roots: list[Path] = []
    for raw in roots_raw:
        root = Path(str(raw)).expanduser().resolve()
        if root == Path(root.anchor):
            raise SupervisorConfigError("filesystem root cannot be an allowed workspace root")
        if not root.is_dir():
            raise SupervisorConfigError(f"allowed workspace root does not exist: {root}")
        roots.append(root)

    worker_tables = data.get("workers")
    if not isinstance(worker_tables, dict) or not worker_tables:
        raise SupervisorConfigError("at least one [workers.<name>] table is required")
    workers: dict[str, WorkerConfig] = {}
    for name, raw in worker_tables.items():
        if not NAME_PATTERN.fullmatch(str(name)) or not isinstance(raw, dict):
            raise SupervisorConfigError(f"invalid worker entry {name!r}")
        vendor = str(raw.get("vendor", ""))
        if vendor not in VALID_VENDORS:
            raise SupervisorConfigError(
                f"worker {name!r} vendor must be one of {sorted(VALID_VENDORS)}"
            )
        roles = tuple(str(role) for role in raw.get("roles", []))
        if not roles or not set(roles).issubset(VALID_ROLES):
            raise SupervisorConfigError(f"worker {name!r} has invalid roles")
        capabilities = tuple(str(item) for item in raw.get("capabilities", []))
        if "worker" in roles and not capabilities:
            raise SupervisorConfigError(
                f"worker {name!r} needs at least one capability"
            )
        executable = _resolve_executable(vendor, raw.get("executable"))
        if not Path(executable).is_file() or not os.access(executable, os.X_OK):
            raise SupervisorConfigError(
                f"worker {name!r} executable is not runnable: {executable}"
            )
        argv_raw = raw.get("argv", [])
        if not isinstance(argv_raw, list):
            raise SupervisorConfigError(f"worker {name!r} argv must be a list")
        if vendor == "command" and not argv_raw:
            raise SupervisorConfigError(f"command worker {name!r} requires argv")
        timeout_seconds = int(raw.get("timeout_seconds", 900))
        max_output_bytes = int(raw.get("max_output_bytes", 1_048_576))
        if not 1 <= timeout_seconds <= 7_200:
            raise SupervisorConfigError(
                f"worker {name!r} timeout_seconds must be between 1 and 7200"
            )
        if not 1_024 <= max_output_bytes <= 16 * 1_048_576:
            raise SupervisorConfigError(
                f"worker {name!r} max_output_bytes must be between 1024 and 16777216"
            )
        workers[str(name)] = WorkerConfig(
            name=str(name),
            vendor=vendor,
            roles=roles,
            capabilities=capabilities,
            executable=executable,
            model=str(raw["model"]) if raw.get("model") else None,
            enabled=bool(raw.get("enabled", True)),
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
            argv=tuple(str(item) for item in argv_raw),
        )

    enabled = [worker for worker in workers.values() if worker.enabled]
    for role in VALID_ROLES:
        if not any(role in worker.roles for worker in enabled):
            raise SupervisorConfigError(f"no enabled worker has role {role!r}")

    max_rounds = int(supervisor.get("max_review_rounds", 2))
    if not 1 <= max_rounds <= 5:
        raise SupervisorConfigError("max_review_rounds must be between 1 and 5")
    poll_interval = float(supervisor.get("poll_interval_seconds", 2.0))
    lease_seconds = int(supervisor.get("lease_seconds", 1800))
    max_concurrent = int(supervisor.get("max_concurrent_runs", 1))
    max_cost = float(supervisor.get("max_run_cost_usd", 10.0))
    automatic_max_risk = str(supervisor.get("automatic_max_risk", "low"))
    if not 0.1 <= poll_interval <= 300:
        raise SupervisorConfigError("poll_interval_seconds must be between 0.1 and 300")
    if not 30 <= lease_seconds <= 86_400:
        raise SupervisorConfigError("lease_seconds must be between 30 and 86400")
    if not 1 <= max_concurrent <= 16:
        raise SupervisorConfigError("max_concurrent_runs must be between 1 and 16")
    if not 0.01 <= max_cost <= 1_000:
        raise SupervisorConfigError("max_run_cost_usd must be between 0.01 and 1000")
    if automatic_max_risk not in {"low", "medium", "high", "critical"}:
        raise SupervisorConfigError("automatic_max_risk is invalid")
    return SupervisorConfig(
        group=group,
        peer=peer,
        operator=operator,
        mode=mode,
        allowed_workspace_roots=tuple(roots),
        workers=workers,
        poll_interval_seconds=poll_interval,
        lease_seconds=lease_seconds,
        max_review_rounds=max_rounds,
        max_concurrent_runs=max_concurrent,
        max_run_cost_usd=max_cost,
        require_cross_vendor_review=bool(
            supervisor.get("require_cross_vendor_review", True)
        ),
        require_distinct_verifier=bool(
            supervisor.get("require_distinct_verifier", True)
        ),
        automatic_max_risk=automatic_max_risk,
        publish_receipts=bool(supervisor.get("publish_receipts", True)),
    )


def validate_workspace(path: str, roots: tuple[Path, ...]) -> Path:
    if not path:
        raise SupervisorConfigError("task has no workspace")
    workspace = Path(path).expanduser().resolve()
    if not workspace.is_dir():
        raise SupervisorConfigError(f"workspace does not exist: {workspace}")
    if not any(workspace == root or workspace.is_relative_to(root) for root in roots):
        raise SupervisorConfigError(
            f"workspace {workspace} is outside allowed roots {list(roots)}"
        )
    return workspace
