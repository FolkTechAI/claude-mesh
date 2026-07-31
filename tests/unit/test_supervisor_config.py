from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from claude_mesh.commands.supervisor import run as supervisor_run
from claude_mesh.supervisor.config import (
    SupervisorConfigError,
    load_supervisor_config,
    validate_workspace,
)
from claude_mesh.supervisor.store import SupervisorStore, supervisor_db_path
from claude_mesh.task_store import TaskStore, task_db_path


def _config(root: Path, *, mode: str = "approval", extra: str = "") -> str:
    executable = sys.executable.replace("\\", "\\\\")
    return f'''[supervisor]
group = "test-group"
peer = "supervisor"
mode = "{mode}"
allowed_workspace_roots = ["{root}"]
max_review_rounds = 2
require_cross_vendor_review = false
{extra}

[workers.worker]
vendor = "command"
executable = "{executable}"
argv = ["worker.py"]
roles = ["worker"]
capabilities = ["coding"]

[workers.critic]
vendor = "command"
executable = "{executable}"
argv = ["critic.py"]
roles = ["critic"]

[workers.verifier]
vendor = "command"
executable = "{executable}"
argv = ["verifier.py"]
roles = ["verifier"]
'''


def test_loads_complete_approval_config(tmp_path: Path):
    root = tmp_path / "workspaces"
    root.mkdir()
    path = tmp_path / "supervisor.toml"
    path.write_text(_config(root), encoding="utf-8")

    config = load_supervisor_config(path)

    assert config.mode == "approval"
    assert config.allowed_workspace_roots == (root.resolve(),)
    assert set(config.workers) == {"worker", "critic", "verifier"}


@pytest.mark.parametrize("mode", ["reckless", "", "admin"])
def test_rejects_invalid_mode(tmp_path: Path, mode: str):
    root = tmp_path / "workspaces"
    root.mkdir()
    path = tmp_path / "supervisor.toml"
    path.write_text(_config(root, mode=mode), encoding="utf-8")

    with pytest.raises(SupervisorConfigError, match="mode"):
        load_supervisor_config(path)


def test_rejects_missing_or_filesystem_root(tmp_path: Path):
    missing = tmp_path / "missing"
    path = tmp_path / "missing.toml"
    path.write_text(_config(missing), encoding="utf-8")
    with pytest.raises(SupervisorConfigError, match="does not exist"):
        load_supervisor_config(path)

    fs_root = Path(os.path.abspath(os.sep))
    path.write_text(_config(fs_root), encoding="utf-8")
    with pytest.raises(SupervisorConfigError, match="filesystem root"):
        load_supervisor_config(path)


def test_workspace_must_be_inside_allowlist(tmp_path: Path):
    allowed = tmp_path / "allowed"
    child = allowed / "project"
    outside = tmp_path / "outside"
    child.mkdir(parents=True)
    outside.mkdir()

    assert validate_workspace(str(child), (allowed,)) == child.resolve()
    with pytest.raises(SupervisorConfigError, match="outside allowed roots"):
        validate_workspace(str(outside), (allowed,))


def test_rejects_unsafe_numeric_bounds(tmp_path: Path):
    root = tmp_path / "workspaces"
    root.mkdir()
    path = tmp_path / "supervisor.toml"
    path.write_text(
        _config(root, extra="poll_interval_seconds = 0"), encoding="utf-8"
    )
    with pytest.raises(SupervisorConfigError, match="poll_interval"):
        load_supervisor_config(path)


def test_submit_creates_task_and_approval_gated_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    home = tmp_path / "home"
    root = tmp_path / "workspaces"
    workspace = root / "project"
    workspace.mkdir(parents=True)
    home.mkdir()
    path = tmp_path / "supervisor.toml"
    path.write_text(_config(root), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    result = supervisor_run(
        "submit",
        config_path=path,
        task_id="T-SUBMIT",
        subject="Implement a bounded change",
        description="Use the existing interface",
        workspace=str(workspace),
        acceptance_criteria="Tests pass",
    )

    assert result == 0
    assert "state=awaiting-approval" in capsys.readouterr().out
    with TaskStore(task_db_path(home, "test-group")) as tasks:
        task = tasks.get("T-SUBMIT")
        assert task is not None and task.assigned_to == "worker"
    with SupervisorStore(supervisor_db_path(home, "test-group")) as runs:
        planned = runs.list_runs()
        assert len(planned) == 1 and planned[0].state == "awaiting-approval"
