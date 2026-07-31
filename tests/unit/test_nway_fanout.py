"""Regression tests for N-way write-side routing and the stdin hang.

Each test here pins a bug found by live probing of the shipped v1 CLI:
  1. broadcast wrote to the SENDER'S own inbox instead of fanning out
  2. notify-change dropped events silently on 3+ peers (other_peer() -> None)
  3. drain's unread counter ignored @note / @decision
  4. commands blocked forever on a stdin pipe that never reached EOF
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from claude_mesh.commands.drain import count_events
from claude_mesh.commands.notify_change import notify_change
from claude_mesh.commands.send import send_event
from claude_mesh.commands.task_event import run as task_event
from claude_mesh.config import MeshConfig
from claude_mesh.stdin_util import read_hook_payload

ROSTER = ["alpha", "beta", "grok"]


def _project(tmp_path: Path, peer: str, peers: list[str] = ROSTER) -> Path:
    d = tmp_path / peer
    (d / "src").mkdir(parents=True)
    body = (
        "mesh_group: g\nmesh_peer: {}\nmesh_peers:\n{}"
        "cross_cutting_paths:\n  - src/**\n"
    ).format(peer, "".join(f"  - {p}\n" for p in peers))
    (d / ".claude-mesh").write_text(body)
    return d


def _inbox(home: Path, peer: str) -> Path:
    return home / ".claude-mesh" / "groups" / "g" / f"{peer}.ftai"


# --- 1. broadcast fan-out -------------------------------------------------

def test_broadcast_reaches_every_other_peer(tmp_path):
    home = tmp_path / "home"
    cwd = _project(tmp_path, "grok")
    rc = send_event("hello all", "note", None, {}, home, cwd)
    assert rc == 0
    assert "hello all" in _inbox(home, "alpha").read_text()
    assert "hello all" in _inbox(home, "beta").read_text()


def test_broadcast_never_writes_to_own_inbox(tmp_path):
    """The v1 bug: no --to fell through to resolve_knowledge_path's own-peer default."""
    home = tmp_path / "home"
    cwd = _project(tmp_path, "grok")
    send_event("hello all", "note", None, {}, home, cwd)
    assert not _inbox(home, "grok").exists()


def test_directed_send_reaches_only_the_target(tmp_path):
    home = tmp_path / "home"
    cwd = _project(tmp_path, "grok")
    send_event("just for alpha", "decision", "alpha", {}, home, cwd)
    assert "just for alpha" in _inbox(home, "alpha").read_text()
    assert not _inbox(home, "beta").exists()


def test_send_to_unknown_peer_is_loud(tmp_path):
    home = tmp_path / "home"
    cwd = _project(tmp_path, "grok")
    assert send_event("typo", "note", "alfa", {}, home, cwd) == 1
    assert not _inbox(home, "alfa").exists()


def test_directed_send_rejects_path_like_peer_without_roster(tmp_path):
    home = tmp_path / "home"
    cwd = _project(tmp_path, "grok", peers=[])
    assert send_event("escape", "note", "../../outside", {}, home, cwd) == 1
    assert not (home / ".claude-mesh" / "outside.ftai").exists()


def test_send_to_self_is_refused(tmp_path):
    home = tmp_path / "home"
    cwd = _project(tmp_path, "grok")
    assert send_event("echo", "note", "grok", {}, home, cwd) == 1


# --- 2. notify-change on 3+ peers ----------------------------------------

def test_notify_change_fans_out_on_three_peers(tmp_path):
    """The v1 bug: other_peer() returned None for 3 peers and dropped the event."""
    home = tmp_path / "home"
    cwd = _project(tmp_path, "grok")
    rc = notify_change("src/auth.rs", "search_replace", "summary", {}, home, cwd)
    assert rc == 0
    for peer in ("alpha", "beta"):
        text = _inbox(home, peer).read_text()
        assert "src/auth.rs" in text
        assert "search_replace" in text
    assert not _inbox(home, "grok").exists()


def test_notify_change_still_works_on_two_peers(tmp_path):
    home = tmp_path / "home"
    cwd = _project(tmp_path, "grok", peers=["grok", "alpha"])
    assert notify_change("src/a.rs", "write_file", "s", {}, home, cwd) == 0
    assert "src/a.rs" in _inbox(home, "alpha").read_text()


def test_notify_change_ignores_non_cross_cutting_paths(tmp_path):
    home = tmp_path / "home"
    cwd = _project(tmp_path, "grok")
    assert notify_change("docs/readme.md", "write_file", "s", {}, home, cwd) == 0
    assert not _inbox(home, "alpha").exists()


def test_task_event_fans_out_on_three_peers(tmp_path, monkeypatch):
    home = tmp_path / "home"
    cwd = _project(tmp_path, "grok")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(cwd)
    assert task_event("T-42", "Coordinate release", "pending") == 0
    for peer in ("alpha", "beta"):
        text = _inbox(home, peer).read_text()
        assert "id: T-42" in text
        assert "subject: Coordinate release" in text
    assert not _inbox(home, "grok").exists()


def test_task_event_directed_to_one_of_three_peers(tmp_path, monkeypatch):
    home = tmp_path / "home"
    cwd = _project(tmp_path, "grok")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(cwd)
    assert task_event(
        "T-43", "Verify result", "pending", to="beta", description="Run AKE"
    ) == 0
    text = _inbox(home, "beta").read_text()
    assert "to: beta" in text
    assert "description: Run AKE" in text
    assert not _inbox(home, "alpha").exists()


# --- 3. other_peers() ------------------------------------------------------

@pytest.mark.parametrize(
    "peer,peers,expected",
    [
        ("grok", ROSTER, ["alpha", "beta"]),
        ("alpha", ROSTER, ["beta", "grok"]),
        ("a", ["a", "b"], ["b"]),
        ("solo", ["solo"], []),
    ],
)
def test_other_peers_generalizes_past_two(peer, peers, expected):
    cfg = MeshConfig(mesh_group="g", mesh_peer=peer, mesh_peers=peers)
    assert cfg.other_peers() == expected


def test_other_peers_falls_back_to_group_name_inference():
    cfg = MeshConfig(mesh_group="alpha-beta", mesh_peer="alpha", mesh_peers=[])
    assert cfg.other_peers() == ["beta"]


# --- 4. unread counter -----------------------------------------------------

def test_count_events_counts_note_and_decision():
    """The v1 counter hardcoded @message/@file_change/@task, so notes read as 0."""
    rendered = "@note\nfrom: a\n@decision\nfrom: b\n@end"
    assert count_events(rendered) == 2


def test_count_events_ignores_end_markers():
    assert count_events("@decision\nfrom: a\ncontent: x\n@end") == 1


def test_count_events_empty():
    assert count_events("") == 0


# --- 5. stdin never blocks -------------------------------------------------

def test_read_stdin_bounded_returns_on_never_closing_pipe():
    """A pipe held open with no EOF must not hang the CLI (or the agent turn).

    The parent keeps the write end open for the whole test, so the child's
    stdin never reaches EOF — precisely the condition that hung the v1 CLI.
    Only the child is timed, so a shell pipeline's own lifetime can't mask it.
    """
    src_dir = str(Path(__file__).resolve().parents[2] / "src")
    script = textwrap.dedent(
        f"""
        import sys, time
        sys.path.insert(0, {src_dir!r})
        from claude_mesh.stdin_util import read_stdin_bounded
        t0 = time.monotonic()
        read_stdin_bounded(0.25)
        print("%.2f" % (time.monotonic() - t0))
        """
    )
    read_fd, write_fd = os.pipe()
    try:
        proc = subprocess.Popen(  # noqa: S603 - sys.executable with fixed test code
            [sys.executable, "-c", script],
            stdin=read_fd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        os.close(read_fd)
        read_fd = -1
        out, err = proc.communicate(timeout=15)  # raises if it hangs
        assert proc.returncode == 0, err
        assert float(out.strip()) < 5.0
    finally:
        if read_fd != -1:
            os.close(read_fd)
        os.close(write_fd)


def test_read_hook_payload_tolerates_garbage(monkeypatch, tmp_path):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert read_hook_payload() == {}


def test_read_hook_payload_rejects_non_dict(monkeypatch):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("[1,2,3]"))
    assert read_hook_payload() == {}
