# src/claude_mesh/events.py
"""Event dataclasses and FTAI rendering."""

from __future__ import annotations

from dataclasses import dataclass, field

from claude_mesh.ftai import emit_tag


@dataclass(frozen=True)
class MessageEvent:
    from_: str
    timestamp: str
    body: str
    to: str | None = None
    thread: str | None = None
    event_id: str | None = None


@dataclass(frozen=True)
class FileChangeEvent:
    from_: str
    timestamp: str
    path: str
    tool: str
    summary: str
    event_id: str | None = None


@dataclass(frozen=True)
class TaskEvent:
    from_: str
    timestamp: str
    id: str
    subject: str
    status: str
    description: str | None = None
    to: str | None = None
    owner: str | None = None
    priority: str | None = None
    risk: str | None = None
    lease_until: str | None = None
    attempt: int | None = None
    evidence: str | None = None
    error: str | None = None
    verified_by: str | None = None
    verification: str | None = None
    event_id: str | None = None
    workspace: str | None = None
    capability: str | None = None
    acceptance_criteria: str | None = None
    approval_required: bool | None = None


@dataclass(frozen=True)
class DecisionEvent:
    from_: str
    timestamp: str
    id: str
    title: str
    content: str
    impact: str | None = None
    event_id: str | None = None


@dataclass(frozen=True)
class NoteEvent:
    from_: str
    timestamp: str
    content: str
    tags: list[str] = field(default_factory=list)
    event_id: str | None = None


@dataclass(frozen=True)
class VerificationEvent:
    from_: str
    timestamp: str
    id: str
    task_id: str
    verdict: str
    evidence: str
    checks: str | None = None
    to: str | None = None
    event_id: str | None = None


@dataclass(frozen=True)
class ExperienceEvent:
    from_: str
    timestamp: str
    id: str
    task_id: str
    outcome: str
    lesson: str
    evidence: str
    verified_by: str
    tags: list[str] = field(default_factory=list)
    to: str | None = None
    event_id: str | None = None


@dataclass(frozen=True)
class CapabilityEvent:
    from_: str
    timestamp: str
    name: str
    description: str
    risk: str
    status: str
    constraints: str | None = None
    event_id: str | None = None


@dataclass(frozen=True)
class HeartbeatEvent:
    from_: str
    timestamp: str
    state: str
    task_id: str | None = None
    event_id: str | None = None


Event = (
    MessageEvent
    | FileChangeEvent
    | TaskEvent
    | DecisionEvent
    | NoteEvent
    | VerificationEvent
    | ExperienceEvent
    | CapabilityEvent
    | HeartbeatEvent
)


def _inline(value: str) -> str:
    """Keep single-tag fields parseable without silently dropping later lines."""
    return " ⏎ ".join(part.strip() for part in value.splitlines())


def render_event(event: Event) -> str:
    """Emit the FTAI text for a single event."""
    if isinstance(event, MessageEvent):
        fields: dict[str, object] = {"from": event.from_}
        if event.event_id:
            fields["event_id"] = event.event_id
        if event.to:
            fields["to"] = event.to
        fields["timestamp"] = event.timestamp
        if event.thread:
            fields["thread"] = event.thread
        fields["body"] = _inline(event.body)
        return emit_tag("message", fields, block=False)

    if isinstance(event, FileChangeEvent):
        fields = {"from": event.from_}
        if event.event_id:
            fields["event_id"] = event.event_id
        fields.update(
            {
                "timestamp": event.timestamp,
                "path": event.path,
                "tool": event.tool,
                "summary": _inline(event.summary),
            }
        )
        return emit_tag("file_change", fields, block=False)

    if isinstance(event, TaskEvent):
        fields = {
            "id": event.id,
            "from": event.from_,
            "timestamp": event.timestamp,
            "subject": event.subject,
            "status": event.status,
        }
        if event.event_id:
            fields["event_id"] = event.event_id
        if event.to:
            fields["to"] = event.to
        if event.description:
            fields["description"] = event.description
        optional = {
            "owner": event.owner,
            "priority": event.priority,
            "risk": event.risk,
            "lease_until": event.lease_until,
            "attempt": event.attempt,
            "evidence": event.evidence,
            "error": event.error,
            "verified_by": event.verified_by,
            "verification": event.verification,
            "workspace": event.workspace,
            "capability": event.capability,
            "acceptance_criteria": event.acceptance_criteria,
            "approval_required": (
                str(event.approval_required).lower()
                if event.approval_required is not None
                else None
            ),
        }
        fields.update({key: value for key, value in optional.items() if value is not None})
        return emit_tag("task", fields, block=True)

    if isinstance(event, DecisionEvent):
        fields = {
            "id": event.id,
            "from": event.from_,
            "timestamp": event.timestamp,
            "title": event.title,
            "content": event.content,
        }
        if event.event_id:
            fields["event_id"] = event.event_id
        if event.impact:
            fields["impact"] = event.impact
        return emit_tag("decision", fields, block=True)

    if isinstance(event, NoteEvent):
        fields = {
            "from": event.from_,
            "timestamp": event.timestamp,
            "content": _inline(event.content),
        }
        if event.event_id:
            fields["event_id"] = event.event_id
        if event.tags:
            fields["tags"] = "[" + ", ".join(event.tags) + "]"
        return emit_tag("note", fields, block=False)

    if isinstance(event, VerificationEvent):
        fields = {
            "id": event.id,
            "from": event.from_,
            "timestamp": event.timestamp,
            "task_id": event.task_id,
            "verdict": event.verdict,
            "evidence": event.evidence,
        }
        if event.event_id:
            fields["event_id"] = event.event_id
        if event.to:
            fields["to"] = event.to
        if event.checks:
            fields["checks"] = event.checks
        return emit_tag("verification", fields, block=True)

    if isinstance(event, ExperienceEvent):
        fields = {
            "id": event.id,
            "from": event.from_,
            "timestamp": event.timestamp,
            "task_id": event.task_id,
            "outcome": event.outcome,
            "lesson": event.lesson,
            "evidence": event.evidence,
            "verified_by": event.verified_by,
        }
        if event.event_id:
            fields["event_id"] = event.event_id
        if event.to:
            fields["to"] = event.to
        if event.tags:
            fields["tags"] = "[" + ", ".join(event.tags) + "]"
        return emit_tag("experience", fields, block=True)

    if isinstance(event, CapabilityEvent):
        fields = {
            "from": event.from_,
            "timestamp": event.timestamp,
            "name": event.name,
            "description": event.description,
            "risk": event.risk,
            "status": event.status,
        }
        if event.event_id:
            fields["event_id"] = event.event_id
        if event.constraints:
            fields["constraints"] = event.constraints
        return emit_tag("capability", fields, block=True)

    if isinstance(event, HeartbeatEvent):
        fields = {
            "from": event.from_,
            "timestamp": event.timestamp,
            "state": _inline(event.state),
        }
        if event.event_id:
            fields["event_id"] = event.event_id
        if event.task_id:
            fields["task_id"] = event.task_id
        return emit_tag("heartbeat", fields, block=False)

    raise TypeError(f"Unknown event type: {type(event).__name__}")


def header_block(group_or_team: str, participants: list[str]) -> str:
    """Build the standard FTAI file header for a fresh knowledge file."""
    header_parts = [
        "@ftai v2.0\n",
        emit_tag(
            "document",
            {
                "title": f"Claude Mesh knowledge log — {group_or_team}",
                "author": "claude-mesh skill",
                "schema": "claude_mesh_v1",
            },
            block=False,
        ),
        emit_tag(
            "schema",
            {
                "name": "claude_mesh_v1",
                "required_tags": '["@document", "@channel"]',
                "optional_tags": (
                    '["@message", "@file_change", "@task", "@decision", "@note", '
                    '"@verification", "@experience", "@capability", "@heartbeat"]'
                ),
            },
            block=True,
        ),
        emit_tag(
            "channel",
            {
                "participants": "[" + ", ".join(participants) + "]",
                "purpose": "Persistent shared knowledge between Claude Code sessions",
            },
            block=False,
        ),
    ]
    return "".join(header_parts)
