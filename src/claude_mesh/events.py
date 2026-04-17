# src/claude_mesh/events.py
"""Event dataclasses and FTAI rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from claude_mesh.ftai import emit_tag


@dataclass(frozen=True)
class MessageEvent:
    from_: str
    timestamp: str
    body: str
    to: str | None = None
    thread: str | None = None


@dataclass(frozen=True)
class FileChangeEvent:
    from_: str
    timestamp: str
    path: str
    tool: str
    summary: str


@dataclass(frozen=True)
class TaskEvent:
    from_: str
    timestamp: str
    id: str
    subject: str
    status: str
    description: str | None = None


@dataclass(frozen=True)
class DecisionEvent:
    from_: str
    timestamp: str
    id: str
    title: str
    content: str
    impact: str | None = None


@dataclass(frozen=True)
class NoteEvent:
    from_: str
    timestamp: str
    content: str
    tags: list[str] = field(default_factory=list)


Event = Union[MessageEvent, FileChangeEvent, TaskEvent, DecisionEvent, NoteEvent]


def render_event(event: Event) -> str:
    """Emit the FTAI text for a single event."""
    if isinstance(event, MessageEvent):
        fields: dict[str, object] = {"from": event.from_}
        if event.to:
            fields["to"] = event.to
        fields["timestamp"] = event.timestamp
        if event.thread:
            fields["thread"] = event.thread
        fields["body"] = event.body
        return emit_tag("message", fields, block=False)

    if isinstance(event, FileChangeEvent):
        return emit_tag(
            "file_change",
            {
                "from": event.from_,
                "timestamp": event.timestamp,
                "path": event.path,
                "tool": event.tool,
                "summary": event.summary,
            },
            block=False,
        )

    if isinstance(event, TaskEvent):
        fields = {
            "id": event.id,
            "from": event.from_,
            "timestamp": event.timestamp,
            "subject": event.subject,
            "status": event.status,
        }
        if event.description:
            fields["description"] = event.description
        return emit_tag("task", fields, block=True)

    if isinstance(event, DecisionEvent):
        fields = {
            "id": event.id,
            "from": event.from_,
            "timestamp": event.timestamp,
            "title": event.title,
            "content": event.content,
        }
        if event.impact:
            fields["impact"] = event.impact
        return emit_tag("decision", fields, block=True)

    if isinstance(event, NoteEvent):
        fields = {
            "from": event.from_,
            "timestamp": event.timestamp,
            "content": event.content,
        }
        if event.tags:
            fields["tags"] = "[" + ", ".join(event.tags) + "]"
        return emit_tag("note", fields, block=False)

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
                "optional_tags": '["@message", "@file_change", "@task", "@decision", "@note"]',
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
