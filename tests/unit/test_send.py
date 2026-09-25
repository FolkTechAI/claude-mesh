# tests/unit/test_send.py
import os
from pathlib import Path

from claude_mesh.commands.send import send_event


def test_send_standalone_message(tmp_home: Path, project_with_mesh_config: Path):
    os.chdir(project_with_mesh_config)
    rc = send_event(
        text="hello brain",
        kind="message",
        to="brain",
        hook_payload={},  # no team_name => standalone
        home=tmp_home,
        cwd=project_with_mesh_config,
    )
    assert rc == 0
    inbox = tmp_home / ".claude-mesh" / "groups" / "vault-brain" / "brain.ftai"
    assert inbox.exists()
    content = inbox.read_text()
    assert "@message" in content
    assert "hello brain" in content


def test_send_team_mode_message(tmp_home: Path):
    rc = send_event(
        text="team hello",
        kind="message",
        to=None,
        hook_payload={"team_name": "spike", "teammate_name": "alpha"},
        home=tmp_home,
        cwd=tmp_home,
    )
    assert rc == 0
    log = tmp_home / ".claude" / "teams" / "spike" / "knowledge.ftai"
    assert log.exists()
    assert "@message" in log.read_text()
    assert "team hello" in log.read_text()


def test_send_rejects_traversing_team_name(tmp_home: Path):
    rc = send_event(
        text="should not land",
        kind="message",
        to=None,
        hook_payload={"team_name": "../../.ssh", "teammate_name": "alpha"},
        home=tmp_home,
        cwd=tmp_home,
    )
    assert rc == 1
    assert not (tmp_home / ".ssh" / "knowledge.ftai").exists()
    assert not (tmp_home / ".claude" / "teams" / "../../.ssh" / "knowledge.ftai").exists()


def test_send_sanitizes_body(tmp_home: Path):
    rc = send_event(
        text="hello\x00\x1b[31mred\x1b[0m",
        kind="message",
        to=None,
        hook_payload={"team_name": "t"},
        home=tmp_home,
        cwd=tmp_home,
    )
    assert rc == 0
    log = tmp_home / ".claude" / "teams" / "t" / "knowledge.ftai"
    content = log.read_text()
    assert "\x00" not in content
    assert "\x1b" not in content
