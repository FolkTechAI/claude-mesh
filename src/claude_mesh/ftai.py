# src/claude_mesh/ftai.py
"""Minimal FTAI v2.0 emit/parse surface for claude-mesh.

Only the subset of tags we use:
- @document, @schema, @channel (headers)
- @message, @file_change, @note (single-line tags)
- @task, @decision (block tags, require @end)

See https://github.com/FolkTechAI/ftai-spec for the full format.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class FTAIParseError(ValueError):
    """Raised when an FTAI file cannot be parsed safely."""


@dataclass(frozen=True)
class Tag:
    name: str
    fields: dict[str, str]
    is_block: bool


def emit_tag(name: str, fields: dict[str, Any], block: bool) -> str:
    """Emit a single @tag with fields. Returns a string with trailing blank line."""
    lines = [f"@{name}"]
    for key, value in fields.items():
        lines.append(f"{key}: {value}")
    if block:
        lines.append("@end")
    lines.append("")  # trailing blank for readability
    return "\n".join(lines) + "\n"


SINGLE_LINE_TAGS = {"message", "file_change", "note", "document", "channel"}
BLOCK_TAGS = {"task", "decision", "schema"}
ALL_TAGS = SINGLE_LINE_TAGS | BLOCK_TAGS

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB ceiling


def parse_file(path: Path) -> list[Tag]:
    """Parse an FTAI file and return a list of Tag objects.

    Fails closed on malformed input. Respects the 10 MB ceiling.
    """
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise FTAIParseError(f"File exceeds {MAX_FILE_BYTES} byte ceiling: {size}")

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    if not any(line.strip().startswith("@ftai") for line in lines[:5]):
        raise FTAIParseError("Missing @ftai version header in first 5 lines")

    tags: list[Tag] = []
    current: dict[str, str] | None = None
    current_name: str | None = None
    current_is_block: bool = False

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if current is not None and not current_is_block:
                tags.append(Tag(current_name or "", current, False))
                current, current_name, current_is_block = None, None, False
            continue

        if stripped.startswith("@"):
            tag_name = stripped[1:].split(" ", 1)[0].split("\t", 1)[0]

            if tag_name == "end":
                if current is None or not current_is_block:
                    raise FTAIParseError(f"Line {lineno}: @end without matching block tag")
                tags.append(Tag(current_name or "", current, True))
                current, current_name, current_is_block = None, None, False
                continue

            if tag_name == "ftai":
                continue  # version header, skip

            if current is not None and not current_is_block:
                tags.append(Tag(current_name or "", current, False))

            if tag_name not in ALL_TAGS:
                # Unknown tag — preserve but mark as unknown; do not fail
                current = {}
                current_name = tag_name
                current_is_block = False
            else:
                current = {}
                current_name = tag_name
                current_is_block = tag_name in BLOCK_TAGS
            continue

        if current is None:
            continue  # skip stray content outside tag

        if ":" in line:
            key, _, value = line.partition(":")
            current[key.strip()] = value.strip()

    if current is not None:
        if current_is_block:
            raise FTAIParseError("Unclosed block tag at end of file")
        tags.append(Tag(current_name or "", current, False))

    if not tags:
        raise FTAIParseError("No parseable tags found")

    return tags
