"""Transactional task lifecycle commands."""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

from claude_mesh.events import TaskEvent, VerificationEvent
from claude_mesh.config import NAME_PATTERN
from claude_mesh.identity import new_event_id, utc_now
from claude_mesh.publish import PublishError, load_current_config, publish_event
from claude_mesh.sanitize import SensitiveDataFilter, sanitize_body, sanitize_summary
from claude_mesh.task_store import TaskConflict, TaskRecord, TaskStore, task_db_path

TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _lease_deadline(seconds: int) -> str:
    if seconds < 30 or seconds > 86400:
        raise TaskConflict("lease seconds must be between 30 and 86400")
    return (
        dt.datetime.now(dt.UTC) + dt.timedelta(seconds=seconds)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _clean(value: str) -> str:
    return sanitize_body(SensitiveDataFilter().redact(value))


def _task_event(record: TaskRecord, actor: str, to: str) -> TaskEvent:
    return TaskEvent(
        from_=actor,
        timestamp=utc_now(),
        id=record.id,
        subject=record.subject,
        status=record.status,
        description=record.description or None,
        to=to,
        owner=record.lease_owner or record.assigned_to,
        priority=record.priority,
        risk=record.risk,
        lease_until=record.lease_until,
        attempt=record.attempt,
        evidence=record.evidence,
        error=record.last_error,
        verified_by=record.verified_by,
        verification=record.verification,
        event_id=new_event_id(),
        workspace=record.workspace or None,
        capability=record.capability,
        acceptance_criteria=record.acceptance_criteria or None,
        approval_required=bool(record.approval_required),
    )


def _publish_record(record: TaskRecord, actor: str, to: str, config, home: Path) -> None:
    publish_event(_task_event(record, actor, to), config=config, home=home, to=to)


def run(
    action: str,
    *,
    task_id: str | None = None,
    subject: str | None = None,
    description: str = "",
    to: str | None = None,
    priority: str = "normal",
    risk: str = "low",
    max_attempts: int = 3,
    idempotency_key: str | None = None,
    lease_seconds: int = 900,
    evidence: str | None = None,
    error: str | None = None,
    verdict: str | None = None,
    statuses: list[str] | None = None,
    as_json: bool = False,
    workspace: str = "",
    capability: str = "coding",
    acceptance_criteria: str = "",
    approval_required: bool = True,
) -> int:
    try:
        config = load_current_config(Path.cwd())
        home = Path.home()
        if task_id is not None and not TASK_ID.fullmatch(task_id):
            raise TaskConflict(
                "task ID must be 1-128 characters from letters, numbers, . _ : -"
            )
        with TaskStore(task_db_path(home, config.mesh_group)) as store:
            if action == "create":
                if not task_id or not subject or not to:
                    raise TaskConflict("create requires --id, --subject, and --to")
                if not NAME_PATTERN.fullmatch(to):
                    raise TaskConflict(f"invalid assignee name {to!r}")
                if config.mesh_peers and to not in config.mesh_peers:
                    raise TaskConflict(f"unknown assignee {to!r}")
                if to == config.mesh_peer:
                    raise TaskConflict("cannot assign a mesh task to self")
                if not 1 <= max_attempts <= 20:
                    raise TaskConflict("max attempts must be between 1 and 20")
                record, created = store.create(
                    task_id=task_id,
                    subject=sanitize_summary(_clean(subject)),
                    description=_clean(description),
                    created_by=config.mesh_peer,
                    assigned_to=to,
                    priority=priority,
                    risk=risk,
                    max_attempts=max_attempts,
                    idempotency_key=idempotency_key or task_id,
                    workspace=workspace,
                    capability=capability,
                    acceptance_criteria=_clean(acceptance_criteria),
                    approval_required=approval_required,
                )
                if created:
                    _publish_record(record, config.mesh_peer, to, config, home)
                _print_record(record, as_json, prefix="created" if created else "existing")
                return 0

            if action == "list":
                expired = store.requeue_expired()
                for record in expired:
                    target = (
                        record.created_by
                        if record.assigned_to == config.mesh_peer
                        else record.assigned_to
                    )
                    _publish_record(
                        record, config.mesh_peer, target, config, home
                    )
                records = store.list(set(statuses) if statuses else None)
                _print_records(records, as_json)
                return 0

            if action == "sweep":
                expired = store.requeue_expired()
                for record in expired:
                    target = (
                        record.created_by
                        if record.assigned_to == config.mesh_peer
                        else record.assigned_to
                    )
                    _publish_record(record, config.mesh_peer, target, config, home)
                _print_records(expired, as_json)
                return 0

            if not task_id:
                raise TaskConflict(f"{action} requires --id")
            current = store.get(task_id)
            if current is None:
                raise TaskConflict(f"unknown task {task_id!r}")

            if action == "claim":
                record = store.claim(
                    task_id, config.mesh_peer, _lease_deadline(lease_seconds)
                )
                target = record.created_by
            elif action == "start":
                record = store.start(
                    task_id, config.mesh_peer, _lease_deadline(lease_seconds)
                )
                target = record.created_by
            elif action == "complete":
                record = store.complete(task_id, config.mesh_peer, _clean(evidence or ""))
                target = record.created_by
            elif action == "fail":
                record = store.fail(task_id, config.mesh_peer, _clean(error or ""))
                target = record.created_by
            elif action == "verify":
                record = store.verify(
                    task_id,
                    config.mesh_peer,
                    verdict or "",
                    _clean(evidence or ""),
                )
                target = record.assigned_to
                verification = VerificationEvent(
                    from_=config.mesh_peer,
                    timestamp=utc_now(),
                    id=f"verify-{task_id}-{record.attempt}",
                    task_id=task_id,
                    verdict=verdict or "",
                    evidence=_clean(evidence or ""),
                    to=target,
                    event_id=new_event_id(),
                )
                publish_event(verification, config=config, home=home, to=target)
            else:
                raise TaskConflict(f"unknown task action {action!r}")

            _publish_record(record, config.mesh_peer, target, config, home)
            _print_record(record, as_json, prefix=action)
            return 0
    except (PublishError, TaskConflict, OSError) as exc:
        print(f"claude-mesh task: {exc}", file=sys.stderr)
        return 1


def _print_record(record: TaskRecord, as_json: bool, prefix: str = "") -> None:
    if as_json:
        print(json.dumps(asdict(record), sort_keys=True))
        return
    lead = f"{prefix}: " if prefix else ""
    print(
        f"{lead}{record.id} status={record.status} assignee={record.assigned_to} "
        f"attempt={record.attempt}/{record.max_attempts} risk={record.risk}"
    )


def _print_records(records: list[TaskRecord], as_json: bool) -> None:
    if as_json:
        print(json.dumps([asdict(record) for record in records], sort_keys=True))
        return
    if not records:
        print("no tasks")
        return
    for record in records:
        _print_record(record, False)
