# tests/unit/test_drain_nway.py
"""N-way mesh drain filtering (SPEC-002).

In the unified shared-log model, a single `knowledge.ftai` holds events for the
whole group. Each participant drains only the events relevant to it:
  - broadcast (no `to:`) -> everyone except the sender
  - directed (`to: peer`) -> only the named peer(s)
  - never your own (`from: == participant`)
"""

from pathlib import Path

from claude_mesh.drain import drain_unread, mark_read, read_marker_path


def _write_log(path: Path, *blocks: str) -> None:
    path.write_text("@ftai v2.0\n" + "".join(blocks))


def _msg(frm: str, body: str, ts: str, to: str | None = None) -> str:
    head = f"\n@message\nfrom: {frm}\n"
    if to is not None:
        head += f"to: {to}\n"
    return head + f"timestamp: {ts}\nbody: {body}\n\n"


def test_directed_message_not_drained_to_non_addressee(tmp_path: Path):
    log = tmp_path / "knowledge.ftai"
    _write_log(
        log,
        _msg("alpha", "broadcast-hi", "2026-06-25T10:00:00Z"),
        _msg("alpha", "for-beta-only", "2026-06-25T10:01:00Z", to="beta"),
    )
    out = drain_unread(log, read_marker_path(log), participant="gamma")
    assert "broadcast-hi" in out
    assert "for-beta-only" not in out


def test_own_messages_not_drained_to_self(tmp_path: Path):
    log = tmp_path / "knowledge.ftai"
    _write_log(
        log,
        _msg("alpha", "from-me", "2026-06-25T10:00:00Z"),
        _msg("beta", "from-beta", "2026-06-25T10:01:00Z"),
    )
    out = drain_unread(log, read_marker_path(log), participant="alpha")
    assert "from-me" not in out      # never echo your own broadcast
    assert "from-beta" in out         # but a peer's broadcast still arrives


def test_read_markers_are_per_participant(tmp_path: Path):
    log = tmp_path / "knowledge.ftai"
    _write_log(log, _msg("alpha", "hello-all", "2026-06-25T10:00:00Z"))

    beta_marker = read_marker_path(log, "beta")
    gamma_marker = read_marker_path(log, "gamma")
    assert beta_marker != gamma_marker  # independent marker files

    # beta drains and marks read
    assert "hello-all" in drain_unread(log, beta_marker, participant="beta")
    mark_read(beta_marker, now="2026-06-25T23:59:59Z")
    assert drain_unread(log, beta_marker, participant="beta") == ""

    # gamma's marker is untouched — it still sees the event
    assert "hello-all" in drain_unread(log, gamma_marker, participant="gamma")
