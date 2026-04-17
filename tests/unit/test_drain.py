# tests/unit/test_drain.py
from pathlib import Path

from claude_mesh.drain import drain_unread, mark_read, read_marker_path


def test_drain_returns_empty_when_no_file(tmp_path: Path):
    log = tmp_path / "knowledge.ftai"
    result = drain_unread(log, marker_path=read_marker_path(log))
    assert result == ""


def test_drain_returns_all_events_when_no_marker(tmp_path: Path):
    log = tmp_path / "knowledge.ftai"
    log.write_text(
        "@ftai v2.0\n"
        "\n@message\nfrom: a\ntimestamp: 2026-04-17T10:00:00Z\nbody: hi\n\n"
    )
    out = drain_unread(log, marker_path=read_marker_path(log))
    assert "@message" in out


def test_mark_read_then_drain_is_empty(tmp_path: Path):
    log = tmp_path / "knowledge.ftai"
    log.write_text(
        "@ftai v2.0\n"
        "\n@message\nfrom: a\ntimestamp: 2026-04-17T10:00:00Z\nbody: hi\n\n"
    )
    marker = read_marker_path(log)
    drain_unread(log, marker)
    mark_read(marker)
    out = drain_unread(log, marker)
    assert out == ""


def test_marker_never_moves_backwards(tmp_path: Path):
    marker = tmp_path / "mark"
    mark_read(marker, now="2026-04-17T12:00:00Z")
    mark_read(marker, now="2026-04-17T11:00:00Z")  # attempt to rewind
    assert marker.read_text().strip() == "2026-04-17T12:00:00Z"
