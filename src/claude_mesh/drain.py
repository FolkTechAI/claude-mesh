# src/claude_mesh/drain.py
from __future__ import annotations

import datetime as _dt
import os
import tempfile
from pathlib import Path

from claude_mesh.ftai import Tag, parse_file


def read_marker_path(knowledge_file: Path) -> Path:
    return knowledge_file.with_suffix(knowledge_file.suffix + ".read")


def _iso_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def drain_unread(knowledge_file: Path, marker_path: Path) -> str:
    if not knowledge_file.exists():
        return ""
    tags = parse_file(knowledge_file)

    last_read = None
    if marker_path.exists():
        try:
            last_read = marker_path.read_text(encoding="utf-8").strip()
        except OSError:
            last_read = None

    unread_parts: list[str] = []
    for tag in tags:
        if tag.name in {"document", "schema", "channel"}:
            continue
        ts = tag.fields.get("timestamp")
        if ts is None or last_read is None or ts > last_read:
            block = _render_tag(tag)
            unread_parts.append(block)
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
    # Monotonic guarantee: never move backwards
    if existing is not None and existing > now:
        return
    marker_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=marker_path.parent, delete=False
    )
    tmp.write(now + "\n")
    tmp.close()
    os.replace(tmp.name, marker_path)
