"""Unit tests for file-drop transport."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_mesh.events import MessageEvent
from claude_mesh.file_drop import (
    ensure_staging_dirs,
    get_copy_instructions,
    prepare_inbox_fetch,
    publish_to_staging,
    read_inbox_from_staging,
)
from claude_mesh.identity import new_event_id, utc_now


def test_ensure_staging_dirs(tmp_path):
    """Test staging directory creation."""
    staging_root = tmp_path / "staging"
    ensure_staging_dirs(staging_root)
    
    assert (staging_root / "outgoing").exists()
    assert (staging_root / "incoming").exists()
    assert (staging_root / "outgoing").stat().st_mode & 0o777 == 0o700


def test_publish_to_staging_new_file(tmp_path):
    """Test publishing to new staging file."""
    staging_root = tmp_path / "staging"
    
    event = MessageEvent(
        from_="neuro-grokbot",
        timestamp=utc_now(),
        body="Test message",
        to="claude-mac",
        event_id=new_event_id(),
    )
    
    staging_file = publish_to_staging(
        event,
        target_peer="claude-mac",
        staging_root=staging_root,
        group_name="test-group",
        participants=["claude-mac", "neuro-grokbot"],
    )
    
    assert staging_file.exists()
    assert staging_file == staging_root / "outgoing" / "claude-mac.ftai"
    
    content = staging_file.read_text()
    assert "@ftai v2.0" in content
    assert "@document" in content
    assert "@message" in content
    assert "from: neuro-grokbot" in content
    assert "Test message" in content


def test_publish_to_staging_append(tmp_path):
    """Test appending to existing staging file."""
    staging_root = tmp_path / "staging"
    
    event1 = MessageEvent(
        from_="neuro-grokbot",
        timestamp="2026-09-01T10:00:00Z",
        body="First message",
        event_id=new_event_id(),
    )
    
    event2 = MessageEvent(
        from_="neuro-grokbot",
        timestamp="2026-09-01T10:05:00Z",
        body="Second message",
        event_id=new_event_id(),
    )
    
    publish_to_staging(event1, "claude-mac", staging_root, "test-group", ["claude-mac", "neuro-grokbot"])
    staging_file = publish_to_staging(event2, "claude-mac", staging_root, "test-group", ["claude-mac", "neuro-grokbot"])
    
    content = staging_file.read_text()
    # Count actual @message event blocks (not mentions in schema)
    assert content.count("\n@message\n") == 2
    assert "First message" in content
    assert "Second message" in content


def test_prepare_inbox_fetch(tmp_path):
    """Test preparing inbox fetch path."""
    staging_root = tmp_path / "staging"
    
    inbox_path = prepare_inbox_fetch("neuro-grokbot", staging_root)
    
    assert inbox_path == staging_root / "incoming" / "neuro-grokbot.ftai"
    assert inbox_path.parent.exists()


def test_read_inbox_from_staging_no_file(tmp_path):
    """Test reading inbox when file doesn't exist."""
    staging_root = tmp_path / "staging"
    ensure_staging_dirs(staging_root)
    
    events = read_inbox_from_staging("neuro-grokbot", staging_root)
    
    assert events == []


def test_read_inbox_from_staging_with_events(tmp_path):
    """Test reading inbox with events."""
    staging_root = tmp_path / "staging"
    ensure_staging_dirs(staging_root)
    
    inbox_file = staging_root / "incoming" / "neuro-grokbot.ftai"
    inbox_file.write_text("""@ftai v2.0

@document
title: Test inbox
schema: claude_mesh_v1

@message
from: claude-mac
timestamp: 2026-09-01T10:00:00Z
body: Test from Claude

@file_change
from: hermes-mac
timestamp: 2026-09-01T10:05:00Z
path: src/api/auth.rs
tool: Edit
summary: 2 files changed
""")
    
    events = read_inbox_from_staging("neuro-grokbot", staging_root)
    
    assert len(events) == 2
    assert events[0]["tag"] == "message"
    assert events[0]["from"] == "claude-mac"
    assert events[0]["body"] == "Test from Claude"
    
    assert events[1]["tag"] == "file_change"
    assert events[1]["from"] == "hermes-mac"
    assert events[1]["path"] == "src/api/auth.rs"


def test_read_inbox_filters_self_authored(tmp_path):
    """Test that inbox reading filters out self-authored events."""
    staging_root = tmp_path / "staging"
    ensure_staging_dirs(staging_root)
    
    inbox_file = staging_root / "incoming" / "neuro-grokbot.ftai"
    inbox_file.write_text("""@ftai v2.0

@message
from: neuro-grokbot
timestamp: 2026-09-01T10:00:00Z
body: Self message

@message
from: claude-mac
timestamp: 2026-09-01T10:05:00Z
body: Other message
""")
    
    events = read_inbox_from_staging("neuro-grokbot", staging_root)
    
    # Should only see claude-mac's message, not self
    assert len(events) == 1
    assert events[0]["from"] == "claude-mac"


def test_read_inbox_respects_read_marker(tmp_path):
    """Test that read marker filters old events."""
    staging_root = tmp_path / "staging"
    ensure_staging_dirs(staging_root)
    
    inbox_file = staging_root / "incoming" / "neuro-grokbot.ftai"
    inbox_file.write_text("""@ftai v2.0

@message
from: claude-mac
timestamp: 2026-09-01T09:00:00Z
body: Old message

@message
from: claude-mac
timestamp: 2026-09-01T10:00:00Z
body: New message
""")
    
    events = read_inbox_from_staging(
        "neuro-grokbot",
        staging_root,
        last_read_marker="2026-09-01T09:30:00Z",
    )
    
    # Should only see message after marker
    assert len(events) == 1
    assert events[0]["body"] == "New message"


def test_get_copy_instructions_publish(tmp_path):
    """Test getting copy instructions for publish operation."""
    staging_root = tmp_path / "staging"
    
    instructions = get_copy_instructions(
        "publish",
        peer_name="claude-mac",
        group_name="test-group",
        staging_root=staging_root,
    )
    
    assert instructions["operation"] == "copy_to_mac"
    assert instructions["source"] == str(staging_root / "outgoing" / "claude-mac.ftai")
    assert instructions["dest"] == "/Users/michaelfolk/.claude-mesh/groups/test-group/claude-mac.ftai"
    assert "Write" in instructions["tool"]


def test_get_copy_instructions_fetch(tmp_path):
    """Test getting copy instructions for fetch operation."""
    staging_root = tmp_path / "staging"
    
    instructions = get_copy_instructions(
        "fetch",
        peer_name="neuro-grokbot",
        group_name="test-group",
        staging_root=staging_root,
    )
    
    assert instructions["operation"] == "copy_from_mac"
    assert instructions["source"] == "/Users/michaelfolk/.claude-mesh/groups/test-group/neuro-grokbot.ftai"
    assert instructions["dest"] == str(staging_root / "incoming" / "neuro-grokbot.ftai")
    assert "Read" in instructions["tool"]


def test_get_copy_instructions_invalid_operation(tmp_path):
    """Test error handling for invalid operation."""
    staging_root = tmp_path / "staging"
    
    with pytest.raises(ValueError, match="Unknown operation"):
        get_copy_instructions(
            "invalid",
            peer_name="claude-mac",
            group_name="test-group",
            staging_root=staging_root,
        )
