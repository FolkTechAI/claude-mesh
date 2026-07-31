"""Publish capability, verification, experience, and presence records."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from claude_mesh.events import (
    CapabilityEvent,
    ExperienceEvent,
    HeartbeatEvent,
    VerificationEvent,
)
from claude_mesh.identity import new_event_id, utc_now
from claude_mesh.publish import PublishError, load_current_config, publish_event
from claude_mesh.sanitize import SensitiveDataFilter, sanitize_body, sanitize_summary
from claude_mesh.task_store import TaskStore, task_db_path

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _clean(value: str) -> str:
    return sanitize_body(SensitiveDataFilter().redact(value))


def run(
    kind: str,
    *,
    to: str | None = None,
    record_id: str | None = None,
    task_id: str | None = None,
    verdict: str | None = None,
    evidence: str | None = None,
    checks: str | None = None,
    outcome: str | None = None,
    lesson: str | None = None,
    verified_by: str | None = None,
    tags: list[str] | None = None,
    name: str | None = None,
    description: str | None = None,
    risk: str | None = None,
    status: str | None = None,
    constraints: str | None = None,
    state: str | None = None,
) -> int:
    try:
        config = load_current_config(Path.cwd())
        now = utc_now()
        event_id = new_event_id()
        for value, label in ((record_id, "record ID"), (task_id, "task ID")):
            if value and not SAFE_ID.fullmatch(value):
                raise PublishError(f"{label} contains unsupported characters")

        if kind == "verification":
            if not all((record_id, task_id, verdict, evidence)):
                raise PublishError(
                    "verification requires --id, --task-id, --verdict, and --evidence"
                )
            event = VerificationEvent(
                from_=config.mesh_peer,
                timestamp=now,
                id=record_id or "",
                task_id=task_id or "",
                verdict=verdict or "",
                evidence=_clean(evidence or ""),
                checks=_clean(checks) if checks else None,
                to=to,
                event_id=event_id,
            )
        elif kind == "experience":
            if not all((record_id, task_id, outcome, lesson, evidence, verified_by)):
                raise PublishError(
                    "experience requires --id, --task-id, --outcome, --lesson, "
                    "--evidence, and --verified-by"
                )
            with TaskStore(task_db_path(Path.home(), config.mesh_group)) as store:
                task = store.get(task_id or "")
            if task is None or task.status != "verified":
                raise PublishError(
                    "experience publication requires a verified task in the mesh ledger"
                )
            if task.verified_by != verified_by:
                raise PublishError(
                    f"--verified-by must match ledger verifier {task.verified_by!r}"
                )
            event = ExperienceEvent(
                from_=config.mesh_peer,
                timestamp=now,
                id=record_id or "",
                task_id=task_id or "",
                outcome=_clean(outcome or ""),
                lesson=_clean(lesson or ""),
                evidence=_clean(evidence or ""),
                verified_by=sanitize_summary(verified_by or ""),
                tags=[sanitize_summary(tag) for tag in (tags or [])],
                to=to,
                event_id=event_id,
            )
        elif kind == "capability":
            if not all((name, description, risk, status)):
                raise PublishError(
                    "capability requires --name, --description, --risk, and --status"
                )
            event = CapabilityEvent(
                from_=config.mesh_peer,
                timestamp=now,
                name=sanitize_summary(name or ""),
                description=_clean(description or ""),
                risk=risk or "",
                status=status or "",
                constraints=_clean(constraints) if constraints else None,
                event_id=event_id,
            )
        elif kind == "heartbeat":
            if not state:
                raise PublishError("heartbeat requires --state")
            event = HeartbeatEvent(
                from_=config.mesh_peer,
                timestamp=now,
                state=state,
                task_id=task_id,
                event_id=event_id,
            )
        else:
            raise PublishError(f"unknown control event {kind!r}")

        paths = publish_event(event, config=config, home=Path.home(), to=to)
        print(f"published {kind} {event_id} to {len(paths)} peer inbox(es)")
        return 0
    except (PublishError, OSError) as exc:
        print(f"claude-mesh {kind}: {exc}", file=sys.stderr)
        return 1
