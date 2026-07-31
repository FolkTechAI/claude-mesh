# src/claude_mesh/drain.py
from __future__ import annotations

import datetime as _dt
import os
import tempfile
from pathlib import Path

from claude_mesh.ftai import Tag, parse_file, parse_text


def read_marker_path(knowledge_file: Path, participant: str | None = None) -> Path:
    """Read-marker path for a knowledge file.

    In the N-way shared-log model each participant owns its own marker so that
    one participant draining does not advance another's position. When no
    participant is given (e.g. team mode), the legacy single marker is used.
    """
    if participant is not None:
        return knowledge_file.with_suffix(f"{knowledge_file.suffix}.{participant}.read")
    return knowledge_file.with_suffix(knowledge_file.suffix + ".read")


def _iso_now() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_recipients(to_value: str | None) -> set[str] | None:
    """Parse a `to:` field into a recipient set, or None for a broadcast.

    Accepts `beta`, `[beta, gamma]`, or `beta, gamma`. Empty/absent -> broadcast.
    """
    if to_value is None:
        return None
    s = to_value.strip().strip("[]")
    recipients = {part.strip() for part in s.split(",") if part.strip()}
    return recipients or None


def pending_marker_path(marker_path: Path) -> Path:
    """Sidecar holding the high-water timestamp of the last drain.

    `mark-read` consumes this instead of stamping wall-clock now, so events
    that land between the drain and the mark-read stay unread.
    """
    return marker_path.with_suffix(marker_path.suffix + ".pending")


def drain_unread_with_high_water(
    knowledge_file: Path, marker_path: Path, participant: str | None = None
) -> tuple[str, str | None]:
    """Drain unread events and report the newest timestamp among them.

    The high-water value is what the marker must advance to. Using wall-clock
    now instead loses anything appended during the drain -> mark-read window:
    the event is newer than the marker, so it is never redelivered, and it was
    never rendered, so it was never seen. Observed live between two agents.
    """
    text = drain_unread(knowledge_file, marker_path, participant)
    if not text:
        return "", None
    stamps = [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.startswith("timestamp:")
    ]
    return text, (max(stamps) if stamps else None)


def drain_unread_with_cursor(
    knowledge_file: Path,
    marker_path: Path,
    participant: str | None = None,
) -> tuple[str, str | None, int | None]:
    """Drain unread events and capture the exact byte cursor covered.

    Timestamp-only markers lose events when two writes share a timestamp or a
    peer's clock moves backward. New drains therefore commit an inbox byte
    offset. Legacy timestamp markers remain readable for migration.
    """
    if not knowledge_file.exists():
        return "", None, None
    cursor = knowledge_file.stat().st_size
    text = drain_unread(knowledge_file, marker_path, participant)
    if not text:
        return "", None, cursor
    stamps = [
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.startswith("timestamp:")
    ]
    return text, (max(stamps) if stamps else None), cursor


def drain_unread(
    knowledge_file: Path, marker_path: Path, participant: str | None = None
) -> str:
    if not knowledge_file.exists():
        return ""
    last_read = None
    offset: int | None = None
    if marker_path.exists():
        try:
            last_read = marker_path.read_text(encoding="utf-8").strip()
        except OSError:
            last_read = None
    if last_read and last_read.startswith("offset:"):
        try:
            offset = int(last_read.partition(":")[2])
        except ValueError:
            offset = None
        size = knowledge_file.stat().st_size
        if offset is not None and 0 <= offset <= size:
            with knowledge_file.open("rb") as handle:
                handle.seek(offset)
                tail = handle.read().decode("utf-8", errors="replace")
            if not tail.strip():
                return ""
            tags = parse_text("@ftai v2.0\n\n" + tail)
            last_read = None
        else:
            tags = parse_file(knowledge_file)
            last_read = None
    else:
        tags = parse_file(knowledge_file)

    unread_parts: list[str] = []
    seen_event_ids: set[str] = set()
    for tag in tags:
        if tag.name in {"document", "schema", "channel"}:
            continue
        ts = tag.fields.get("timestamp")
        if not (ts is None or last_read is None or ts > last_read):
            continue
        # N-way routing: never echo your own events; directed events reach
        # only their named recipients.
        if participant is not None:
            if tag.fields.get("from") == participant:
                continue
            recipients = _parse_recipients(tag.fields.get("to"))
            if recipients is not None and participant not in recipients:
                continue
        event_id = tag.fields.get("event_id")
        if event_id and event_id in seen_event_ids:
            continue
        if event_id:
            seen_event_ids.add(event_id)
        unread_parts.append(_render_tag(tag))
    return "\n".join(unread_parts)


def _render_tag(tag: Tag) -> str:
    lines = [f"@{tag.name}"]
    for k, v in tag.fields.items():
        lines.append(f"{k}: {v}")
    if tag.is_block:
        lines.append("@end")
    return "\n".join(lines)


def mark_read(marker_path: Path, now: str | None = None) -> None:
    now = now or _iso_now()
    existing = None
    if marker_path.exists():
        try:
            existing = marker_path.read_text(encoding="utf-8").strip()
        except OSError:
            existing = None
    if existing is not None:
        if existing.startswith("offset:") and now.startswith("offset:"):
            try:
                if int(existing.partition(":")[2]) > int(now.partition(":")[2]):
                    return
            except ValueError:
                pass
        elif not existing.startswith("offset:") and not now.startswith("offset:"):
            if existing > now:
                return
    marker_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=marker_path.parent, delete=False
    )
    tmp.write(now + "\n")
    tmp.close()
    os.replace(tmp.name, marker_path)
