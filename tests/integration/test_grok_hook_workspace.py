"""Grok adapter: publish must survive a session workspace that isn't the project.

Reported from a live Grok Build session: "Auto hooks only work if that project
is the session workspace (not home)." Grok launches frequently with
workspaceRoot=$HOME, and the v1 adapter anchored config discovery and path
relativization on workspaceRoot alone — so every edit was silently dropped.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks-grok" / "post_tool_use_edit.sh"
ROSTER = ["grok", "claudepeer"]


@pytest.fixture
def mesh(tmp_path):
    """A mesh-enabled project plus an isolated HOME for the mailbox."""
    home = tmp_path / "home"
    home.mkdir()
    proj = tmp_path / "work" / "myproj"
    (proj / "src" / "deep").mkdir(parents=True)
    (proj / ".claude-mesh").write_text(
        "mesh_group: wsfb\nmesh_peer: grok\n"
        "mesh_peers:\n  - grok\n  - claudepeer\n"
        "cross_cutting_paths:\n  - src/**\n"
    )
    return home, proj


def _run(hook_env_home: Path, payload: dict, cwd: Path):
    env = dict(os.environ)
    env["HOME"] = str(hook_env_home)
    env.pop("CLAUDE_MESH_ROOT", None)
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True, cwd=str(cwd), env=env, timeout=30,
    )


def _inbox(home: Path, peer: str) -> Path:
    return home / ".claude-mesh" / "groups" / "wsfb" / f"{peer}.ftai"


@pytest.mark.skipif(not HOOK.exists(), reason="grok adapter not present")
def test_publishes_when_workspace_root_is_home(mesh):
    """The reported failure: workspace is $HOME, project lives elsewhere."""
    home, proj = mesh
    payload = {
        "hookEventName": "post_tool_use",
        "cwd": str(home),
        "workspaceRoot": str(home),
        "toolName": "search_replace",
        "toolInput": {"file_path": str(proj / "src" / "deep" / "mod.rs")},
        "toolResult": "ok",
    }
    r = _run(home, payload, cwd=home)
    assert r.returncode == 0, r.stderr

    text = _inbox(home, "claudepeer").read_text()
    # Relativized against the PROJECT, not $HOME — a home-anchored path would
    # read like work/myproj/src/deep/mod.rs and fail cross-cutting matching.
    assert "path: src/deep/mod.rs" in text
    assert "tool: search_replace" in text
    assert not _inbox(home, "grok").exists()  # no self-echo


@pytest.mark.skipif(not HOOK.exists(), reason="grok adapter not present")
def test_still_publishes_when_workspace_root_is_the_project(mesh):
    home, proj = mesh
    payload = {
        "hookEventName": "post_tool_use",
        "cwd": str(proj),
        "workspaceRoot": str(proj),
        "toolName": "write_file",
        "toolInput": {"file_path": str(proj / "src" / "a.rs")},
    }
    r = _run(home, payload, cwd=proj)
    assert r.returncode == 0, r.stderr
    assert "path: src/a.rs" in _inbox(home, "claudepeer").read_text()


@pytest.mark.skipif(not HOOK.exists(), reason="grok adapter not present")
def test_edit_outside_any_mesh_project_is_ignored(mesh, tmp_path):
    """No .claude-mesh anywhere above the file: stay silent, never crash."""
    home, _ = mesh
    stray = tmp_path / "elsewhere" / "src"
    stray.mkdir(parents=True)
    payload = {
        "hookEventName": "post_tool_use",
        "cwd": str(home),
        "workspaceRoot": str(home),
        "toolName": "search_replace",
        "toolInput": {"file_path": str(stray / "x.rs")},
    }
    r = _run(home, payload, cwd=home)
    assert r.returncode == 0, r.stderr
    assert not (home / ".claude-mesh" / "groups" / "wsfb").exists()


@pytest.mark.skipif(not HOOK.exists(), reason="grok adapter not present")
def test_non_edit_tool_is_ignored(mesh):
    home, proj = mesh
    payload = {
        "hookEventName": "post_tool_use",
        "cwd": str(proj),
        "workspaceRoot": str(proj),
        "toolName": "run_terminal_command",
        "toolInput": {"file_path": str(proj / "src" / "a.rs")},
    }
    r = _run(home, payload, cwd=proj)
    assert r.returncode == 0, r.stderr
    assert not _inbox(home, "claudepeer").exists()
