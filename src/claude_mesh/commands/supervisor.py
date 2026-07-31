"""CLI surface for the deterministic adversarial supervisor."""

from __future__ import annotations

import getpass
import json
import os
import re
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

from claude_mesh.sanitize import SensitiveDataFilter, sanitize_body, sanitize_summary
from claude_mesh.supervisor.config import (
    SupervisorConfigError,
    default_config_path,
    load_supervisor_config,
    validate_workspace,
)
from claude_mesh.supervisor.engine import Supervisor, SupervisorError
from claude_mesh.supervisor.store import RunConflict, SupervisorStore, supervisor_db_path
from claude_mesh.task_store import TaskStore, task_db_path

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def init_config(
    path: Path, group: str, workspace_root: Path, operator: str | None = None
) -> int:
    if path.exists():
        print(f"claude-mesh supervisor: {path} already exists", file=sys.stderr)
        return 1
    root = workspace_root.expanduser().resolve()
    if not root.is_dir() or root == Path(root.anchor):
        print("claude-mesh supervisor: workspace root is invalid", file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    codex = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    operator_name = operator or re.sub(r"[^a-z0-9-]", "-", getpass.getuser().lower())
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", operator_name):
        print("claude-mesh supervisor: operator name is invalid", file=sys.stderr)
        return 1
    text = f'''[supervisor]
group = "{group}"
peer = "supervisor"
operator = "{operator_name}"
mode = "approval"
allowed_workspace_roots = ["{root}"]
poll_interval_seconds = 2.0
lease_seconds = 1800
max_review_rounds = 2
max_concurrent_runs = 1
max_run_cost_usd = 10.0
require_cross_vendor_review = true
require_distinct_verifier = true
automatic_max_risk = "low"
publish_receipts = true

[workers.claude-worker]
vendor = "claude"
roles = ["worker"]
capabilities = ["coding"]
timeout_seconds = 1200

[workers.grok-critic]
vendor = "grok"
roles = ["critic"]
capabilities = ["coding-review"]
timeout_seconds = 900

[workers.codex-verifier]
vendor = "codex"
executable = "{codex}"
roles = ["verifier"]
capabilities = ["coding-verification"]
timeout_seconds = 900
'''
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)
    print(f"claude-mesh: wrote supervisor config {path}")
    print("mode=approval; no model process runs until an operator approves a run")
    return 0


def run(
    action: str,
    *,
    config_path: Path | None = None,
    group: str | None = None,
    workspace_root: Path | None = None,
    task_id: str | None = None,
    run_id: str | None = None,
    approved_by: str | None = None,
    operator: str | None = None,
    subject: str | None = None,
    description: str = "",
    workspace: str | None = None,
    acceptance_criteria: str = "",
    risk: str = "low",
    capability: str = "coding",
    worker: str | None = None,
    idempotency_key: str | None = None,
    approval_required: bool = True,
    stop_after: float | None = None,
    as_json: bool = False,
) -> int:
    path = config_path or default_config_path()
    if action == "init":
        if not group or workspace_root is None:
            print("supervisor init requires --group and --workspace-root", file=sys.stderr)
            return 2
        return init_config(path, group, workspace_root, operator)
    try:
        config = load_supervisor_config(path)
        with (
            TaskStore(task_db_path(Path.home(), config.group)) as tasks,
            SupervisorStore(supervisor_db_path(Path.home(), config.group)) as runs,
        ):
            supervisor = Supervisor(config, tasks, runs)
            if action == "submit":
                if not subject or not workspace:
                    raise SupervisorError("submit requires --subject and --workspace")
                workspace_path = validate_workspace(
                    workspace, config.allowed_workspace_roots
                )
                eligible = [
                    item
                    for item in config.workers.values()
                    if item.enabled
                    and "worker" in item.roles
                    and capability in item.capabilities
                ]
                if worker:
                    eligible = [item for item in eligible if item.name == worker]
                if len(eligible) != 1:
                    raise SupervisorError(
                        "submit requires exactly one eligible worker; use --worker"
                    )
                generated_id = task_id or f"TASK-{uuid.uuid4()}"
                if not SAFE_ID.fullmatch(generated_id):
                    raise SupervisorError("task ID contains unsupported characters")
                clean = SensitiveDataFilter()
                record, _ = tasks.create(
                    task_id=generated_id,
                    subject=sanitize_summary(clean.redact(subject)),
                    description=sanitize_body(clean.redact(description)),
                    created_by=config.operator,
                    assigned_to=eligible[0].name,
                    priority="normal",
                    risk=risk,
                    max_attempts=3,
                    idempotency_key=idempotency_key or generated_id,
                    workspace=str(workspace_path),
                    capability=capability,
                    acceptance_criteria=sanitize_body(
                        clean.redact(acceptance_criteria)
                    ),
                    approval_required=approval_required,
                )
                result = supervisor.run_task(record.id)
                _print(result, as_json)
            elif action == "plan":
                if not task_id:
                    raise SupervisorError("plan requires --task-id")
                result = supervisor.plan(task_id)
                _print(result, as_json)
            elif action == "run":
                if not task_id:
                    raise SupervisorError("run requires --task-id")
                result = supervisor.run_task(task_id)
                _print(result, as_json)
            elif action == "approve":
                if not run_id or not approved_by:
                    raise SupervisorError("approve requires --run-id and --by")
                result = supervisor.approve(run_id, approved_by)
                _print(result, as_json)
            elif action == "execute":
                if not run_id:
                    raise SupervisorError("execute requires --run-id")
                result = supervisor.execute(run_id)
                _print(result, as_json)
            elif action == "once":
                _print_many(supervisor.run_once(), as_json)
            elif action == "serve":
                supervisor.serve(stop_after=stop_after)
            elif action == "recover":
                _print_many(supervisor.recover(), as_json)
            elif action == "list":
                _print_many(runs.list_runs(), as_json)
            elif action == "artifacts":
                if not run_id:
                    raise SupervisorError("artifacts requires --run-id")
                _print_many(runs.artifacts(run_id), as_json)
            else:
                raise SupervisorError(f"unknown supervisor action {action!r}")
        return 0
    except (
        OSError,
        RunConflict,
        SupervisorConfigError,
        SupervisorError,
    ) as exc:
        print(f"claude-mesh supervisor: {exc}", file=sys.stderr)
        return 1


def _print(record: object, as_json: bool) -> None:
    data = asdict(record)  # type: ignore[arg-type]
    if as_json:
        print(json.dumps(data, sort_keys=True))
        return
    print(
        " ".join(
            f"{key}={value}"
            for key, value in data.items()
            if value is not None and value != ""
        )
    )


def _print_many(records: list[object], as_json: bool) -> None:
    if as_json:
        print(json.dumps([asdict(record) for record in records], sort_keys=True))  # type: ignore[arg-type]
        return
    if not records:
        print("no records")
        return
    for record in records:
        _print(record, False)
