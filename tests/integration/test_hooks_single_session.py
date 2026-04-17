"""Integration tests for claude-mesh hook wrappers — single-session scenarios."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_session_start_hook_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude-mesh").mkdir()
    hook = Path(__file__).parent.parent.parent / "hooks" / "session_start.sh"
    r = subprocess.run(
        ["bash", str(hook)],
        capture_output=True, text=True, check=False,
        input=json.dumps({"hook_event_name": "SessionStart", "cwd": str(tmp_path)}),
    )
    assert r.returncode == 0


def test_user_prompt_submit_injects_unread(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    # Setup project with mesh and pre-populate inbox
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".claude-mesh").write_text(
        "mesh_group: a-b\nmesh_peer: a\n"
    )
    inbox = tmp_path / ".claude-mesh" / "groups" / "a-b" / "a.ftai"
    inbox.parent.mkdir(parents=True)
    inbox.write_text(
        "@ftai v2.0\n\n"
        "@message\nfrom: b\ntimestamp: 2026-04-17T10:00Z\nbody: hello\n\n"
    )
    hook = Path(__file__).parent.parent.parent / "hooks" / "user_prompt_submit.sh"
    r = subprocess.run(
        ["bash", str(hook)],
        cwd=proj,
        capture_output=True, text=True, check=False,
        input=json.dumps({
            "hook_event_name": "UserPromptSubmit",
            "prompt": "real user prompt",
            "cwd": str(proj),
        }),
    )
    assert r.returncode == 0
    assert "mesh_context" in r.stdout or "hello" in r.stdout


def test_post_tool_use_edit_matches_cross_cutting(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".claude-mesh").write_text(
        "mesh_group: vault-brain\nmesh_peer: vault\ncross_cutting_paths:\n  - src/api/**\n"
    )
    hook = Path(__file__).parent.parent.parent / "hooks" / "post_tool_use_edit.sh"
    r = subprocess.run(
        ["bash", str(hook)],
        cwd=proj,
        capture_output=True, text=True, check=False,
        input=json.dumps({
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": str(proj / "src" / "api" / "x.rs")},
        }),
    )
    assert r.returncode == 0
    inbox = tmp_path / ".claude-mesh" / "groups" / "vault-brain" / "brain.ftai"
    assert inbox.exists()
    assert "@file_change" in inbox.read_text()
    assert "src/api/x.rs" in inbox.read_text()


def test_task_created_hook_writes_task_event(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".claude-mesh").write_text(
        "mesh_group: vault-brain\nmesh_peer: vault\n"
    )
    hook = Path(__file__).parent.parent.parent / "hooks" / "task_created.sh"
    r = subprocess.run(
        ["bash", str(hook)],
        cwd=proj,
        capture_output=True, text=True, check=False,
        input=json.dumps({
            "hook_event_name": "TaskCreated",
            "task_id": "T-001",
            "task_subject": "Implement auth",
            "cwd": str(proj),
        }),
    )
    assert r.returncode == 0
    inbox = tmp_path / ".claude-mesh" / "groups" / "vault-brain" / "brain.ftai"
    assert inbox.exists()
    content = inbox.read_text()
    assert "@task" in content
    assert "T-001" in content
    assert "pending" in content


def test_task_completed_hook_writes_completed_task(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".claude-mesh").write_text(
        "mesh_group: vault-brain\nmesh_peer: vault\n"
    )
    hook = Path(__file__).parent.parent.parent / "hooks" / "task_completed.sh"
    r = subprocess.run(
        ["bash", str(hook)],
        cwd=proj,
        capture_output=True, text=True, check=False,
        input=json.dumps({
            "hook_event_name": "TaskCompleted",
            "task_id": "T-002",
            "task_subject": "Deploy service",
            "cwd": str(proj),
        }),
    )
    assert r.returncode == 0
    inbox = tmp_path / ".claude-mesh" / "groups" / "vault-brain" / "brain.ftai"
    assert inbox.exists()
    content = inbox.read_text()
    assert "@task" in content
    assert "T-002" in content
    assert "completed" in content


def test_subagent_stop_hook_logs_turn_in_team_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    hook = Path(__file__).parent.parent.parent / "hooks" / "subagent_stop.sh"
    long_message = "This is a detailed summary of what happened during this turn. " * 3
    r = subprocess.run(
        ["bash", str(hook)],
        capture_output=True, text=True, check=False,
        input=json.dumps({
            "hook_event_name": "SubagentStop",
            "team_name": "mesh-team",
            "teammate_name": "frontend",
            "last_assistant_message": long_message,
        }),
    )
    assert r.returncode == 0
    log = tmp_path / ".claude" / "teams" / "mesh-team" / "knowledge.ftai"
    assert log.exists()
    assert "@message" in log.read_text()


def test_teammate_idle_hook_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    hook = Path(__file__).parent.parent.parent / "hooks" / "teammate_idle.sh"
    r = subprocess.run(
        ["bash", str(hook)],
        capture_output=True, text=True, check=False,
        input=json.dumps({"hook_event_name": "TeammateIdle"}),
    )
    assert r.returncode == 0
    assert r.stdout == ""


def test_post_tool_use_team_creates_team_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    hook = Path(__file__).parent.parent.parent / "hooks" / "post_tool_use_team.sh"
    r = subprocess.run(
        ["bash", str(hook)],
        capture_output=True, text=True, check=False,
        input=json.dumps({
            "hook_event_name": "PostToolUse",
            "tool_name": "TeamCreate",
            "tool_input": {"team_name": "my-team"},
        }),
    )
    assert r.returncode == 0
    team_dir = tmp_path / ".claude" / "teams" / "my-team"
    assert team_dir.exists()
