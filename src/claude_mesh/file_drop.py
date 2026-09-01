"""File-drop transport for peers without direct filesystem access to the hub.

Used by Neuro on Grok Bot box to publish/drain events via staging directory
+ copy operations to Mac hub, without SSH.

Hub model:
- Mac mini (/Users/michaelfolk/.claude-mesh) is source of truth
- Neuro on Grok Bot box writes to /home/box/.claude-mesh-staging/
- Copy operations use Grok Bot registered-computer tools (not SSH)
"""

from __future__ import annotations

from pathlib import Path

from claude_mesh.events import Event, header_block, render_event
from claude_mesh.ftai import parse_file


def ensure_staging_dirs(staging_root: Path) -> None:
    """Create staging directories if they don't exist."""
    (staging_root / "outgoing").mkdir(parents=True, exist_ok=True, mode=0o700)
    (staging_root / "incoming").mkdir(parents=True, exist_ok=True, mode=0o700)


def publish_to_staging(
    event: Event,
    target_peer: str,
    staging_root: Path,
    group_name: str,
    participants: list[str],
) -> Path:
    """Write event to staging/outgoing/{peer}.ftai for later copy to Mac hub.

    Returns the path to the staging file that should be copied to Mac.

    Copy contract:
    Source: {staging_root}/outgoing/{target_peer}.ftai
    Dest:   /Users/michaelfolk/.claude-mesh/groups/{group_name}/{target_peer}.ftai

    The caller (Neuro on Grok Bot box) must copy the returned file to Mac hub
    using Grok Bot registered-computer Write tools.
    """
    ensure_staging_dirs(staging_root)
    
    outgoing_file = staging_root / "outgoing" / f"{target_peer}.ftai"
    header = header_block(group_name, participants)
    rendered = render_event(event)
    
    # Write to staging (will be copied to Mac hub)
    if not outgoing_file.exists():
        outgoing_file.write_text(header + rendered, encoding="utf-8")
    else:
        # Append to existing staging file
        with outgoing_file.open("a", encoding="utf-8") as f:
            f.write(rendered)
    
    return outgoing_file


def prepare_inbox_fetch(
    peer_name: str,
    staging_root: Path,
) -> Path:
    """Return the staging path where inbox should be copied from Mac hub.

    Copy contract:
    Source: /Users/michaelfolk/.claude-mesh/groups/{group_name}/{peer_name}.ftai
    Dest:   {staging_root}/incoming/{peer_name}.ftai

    The caller (Neuro on Grok Bot box) must copy from Mac hub to the returned
    path using Grok Bot registered-computer Read tools.

    After copy, call read_inbox_from_staging() to parse events.
    """
    ensure_staging_dirs(staging_root)
    return staging_root / "incoming" / f"{peer_name}.ftai"


def read_inbox_from_staging(
    peer_name: str,
    staging_root: Path,
    last_read_marker: str | None = None,
) -> list[dict[str, str]]:
    """Read and parse inbox from staging/incoming/ after copy from Mac hub.

    Returns list of unread events (dicts with tag name and fields).

    Caller should maintain last_read_marker (timestamp) to track position.
    """
    incoming_file = staging_root / "incoming" / f"{peer_name}.ftai"
    
    if not incoming_file.exists():
        return []
    
    tags = parse_file(incoming_file)
    
    unread = []
    for tag in tags:
        if tag.name in {"document", "schema", "channel"}:
            continue
        
        ts = tag.fields.get("timestamp")
        if last_read_marker and ts and ts <= last_read_marker:
            continue
        
        # Skip self-authored events (Neuro shouldn't read its own messages)
        if tag.fields.get("from") == peer_name:
            continue
        
        event_dict = {"tag": tag.name, **tag.fields}
        if tag.is_block:
            event_dict["is_block"] = True
        unread.append(event_dict)
    
    return unread


def get_copy_instructions(
    operation: str,
    peer_name: str,
    group_name: str,
    staging_root: Path,
) -> dict[str, str]:
    """Get copy instructions for Grok Bot registered-computer tools.

    Args:
        operation: "publish" or "fetch"
        peer_name: Target peer (for publish) or own peer name (for fetch)
        group_name: Mesh group name
        staging_root: Staging directory on Grok Bot box

    Returns dict with source and dest paths for copy operation.
    """
    if operation == "publish":
        return {
            "source": str(staging_root / "outgoing" / f"{peer_name}.ftai"),
            "dest": f"/Users/michaelfolk/.claude-mesh/groups/{group_name}/{peer_name}.ftai",
            "operation": "copy_to_mac",
            "tool": "Write (append or replace)",
        }
    elif operation == "fetch":
        return {
            "source": f"/Users/michaelfolk/.claude-mesh/groups/{group_name}/{peer_name}.ftai",
            "dest": str(staging_root / "incoming" / f"{peer_name}.ftai"),
            "operation": "copy_from_mac",
            "tool": "Read (entire file)",
        }
    else:
        raise ValueError(f"Unknown operation: {operation}")
