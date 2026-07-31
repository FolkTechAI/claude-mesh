"""mark-read must not consume mail that arrived after the drain it follows.

Observed live between a Claude Code peer and a Grok Build peer:

  23:36:12  claudepeer -> grok   message A
  ~23:4x    grok drains          (renders A only)
  23:42:00  claudepeer -> grok   message B   <-- lands mid-turn
  23:43:13  grok mark-read       marker := now() == 23:43:13

B is now older than the marker, so it is never redelivered — and it was never
rendered, so it was never seen. Silently lost. The docs promise at-least-once
delivery; stamping wall-clock now makes it at-most-once across that window.

The marker must advance to the newest event the drain actually covered.
"""

from __future__ import annotations

from pathlib import Path

from claude_mesh.commands.drain import run as drain_run
from claude_mesh.commands.mark_read import run as mark_read_run
from claude_mesh.drain import (
    drain_unread,
    drain_unread_with_cursor,
    drain_unread_with_high_water,
    mark_read,
    pending_marker_path,
    read_marker_path,
)

HEADER = "@ftai v2.0\n\n@document\ntitle: t\n\n@channel\nparticipants: [a, b]\n\n"


def _log(tmp_path: Path, *events: tuple[str, str]) -> Path:
    p = tmp_path / "peer.ftai"
    body = HEADER
    for ts, content in events:
        body += f"@note\nfrom: peer\ntimestamp: {ts}\ncontent: {content}\n\n"
    p.write_text(body)
    return p


def test_high_water_is_newest_drained_event(tmp_path):
    log = _log(tmp_path, ("2026-01-01T00:00:01Z", "one"), ("2026-01-01T00:00:02Z", "two"))
    marker = read_marker_path(log)
    text, hw = drain_unread_with_high_water(log, marker)
    assert "one" in text and "two" in text
    assert hw == "2026-01-01T00:00:02Z"


def test_high_water_is_none_when_nothing_unread(tmp_path):
    log = _log(tmp_path)
    text, hw = drain_unread_with_high_water(log, read_marker_path(log))
    assert text == "" and hw is None


def test_message_arriving_after_drain_survives_mark_read(tmp_path, monkeypatch):
    """The exact live failure, replayed."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".claude-mesh").write_text(
        "mesh_group: g\nmesh_peer: grok\nmesh_peers:\n  - grok\n  - claudepeer\n"
    )
    group = home / ".claude-mesh" / "groups" / "g"
    group.mkdir(parents=True)
    log = group / "grok.ftai"
    log.write_text(
        HEADER
        + "@note\nfrom: claudepeer\ntimestamp: 2026-01-01T00:00:10Z\n"
        "content: MESSAGE-A\n\n"
    )

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(proj)

    assert drain_run("prompt") == 0  # renders A, records high-water

    # B lands between the drain and the mark-read.
    with log.open("a") as fh:
        fh.write("@note\nfrom: claudepeer\ntimestamp: 2026-01-01T00:00:20Z\ncontent: MESSAGE-B\n\n")

    assert mark_read_run() == 0

    marker = read_marker_path(log)
    marker_value = marker.read_text().strip()
    assert marker_value.startswith("offset:"), "marker did not migrate to an exact cursor"
    assert int(marker_value.partition(":")[2]) < log.stat().st_size, "marker jumped past B"

    # B must still be deliverable.
    still_unread = drain_unread(log, marker)
    assert "MESSAGE-B" in still_unread
    assert "MESSAGE-A" not in still_unread


def test_pending_sidecar_is_cleared_after_mark_read(tmp_path, monkeypatch):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".claude-mesh").write_text(
        "mesh_group: g\nmesh_peer: grok\nmesh_peers:\n  - grok\n  - x\n"
    )
    group = home / ".claude-mesh" / "groups" / "g"
    group.mkdir(parents=True)
    log = group / "grok.ftai"
    log.write_text(HEADER + "@note\nfrom: x\ntimestamp: 2026-01-01T00:00:10Z\ncontent: A\n\n")

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(proj)

    drain_run("prompt")
    assert pending_marker_path(read_marker_path(log)).exists()
    mark_read_run()
    assert not pending_marker_path(read_marker_path(log)).exists()


def test_bare_mark_read_without_drain_still_marks_now(tmp_path, monkeypatch):
    """No preceding drain means 'mark everything read' — wall-clock is correct."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".claude-mesh").write_text(
        "mesh_group: g\nmesh_peer: grok\nmesh_peers:\n  - grok\n  - x\n"
    )
    group = home / ".claude-mesh" / "groups" / "g"
    group.mkdir(parents=True)
    log = group / "grok.ftai"
    log.write_text(HEADER + "@note\nfrom: x\ntimestamp: 2026-01-01T00:00:10Z\ncontent: A\n\n")

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(proj)

    assert mark_read_run() == 0
    assert drain_unread(log, read_marker_path(log)) == ""


def test_marker_never_moves_backwards(tmp_path):
    marker = tmp_path / "m.read"
    mark_read(marker, now="2026-01-01T00:00:20Z")
    mark_read(marker, now="2026-01-01T00:00:10Z")
    assert marker.read_text().strip() == "2026-01-01T00:00:20Z"


def test_offset_marker_delivers_later_event_with_identical_timestamp(tmp_path):
    timestamp = "2026-01-01T00:00:10Z"
    log = _log(tmp_path, (timestamp, "FIRST"))
    marker = read_marker_path(log)
    _, _, cursor = drain_unread_with_cursor(log, marker)
    assert cursor is not None
    mark_read(marker, now=f"offset:{cursor}")

    with log.open("a") as handle:
        handle.write(
            f"@note\nfrom: peer\ntimestamp: {timestamp}\ncontent: SECOND\n\n"
        )

    unread = drain_unread(log, marker)
    assert "SECOND" in unread
    assert "FIRST" not in unread
