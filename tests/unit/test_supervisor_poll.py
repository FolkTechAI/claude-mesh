from __future__ import annotations

from pathlib import Path

import pytest

from claude_mesh.commands.supervisor import run as supervisor_run
from claude_mesh.supervisor.config import SupervisorConfig, WorkerConfig
from claude_mesh.supervisor.engine import Supervisor
from claude_mesh.supervisor.store import SupervisorStore
from claude_mesh.task_store import TaskStore


def _workers() -> dict[str, WorkerConfig]:
    return {
        "worker": WorkerConfig("worker", "a", ("worker",), ("coding",), "/bin/true"),
        "critic": WorkerConfig("critic", "b", ("critic",), (), "/bin/true"),
        "verifier": WorkerConfig("verifier", "c", ("verifier",), (), "/bin/true"),
    }


def _config(tmp_path: Path) -> SupervisorConfig:
    return SupervisorConfig(
        group="test-group",
        peer="supervisor",
        mode="approval",
        allowed_workspace_roots=(tmp_path,),
        workers=_workers(),
        require_cross_vendor_review=False,
        max_concurrent_runs=2,
    )


def _create_task(
    tasks: TaskStore,
    *,
    task_id: str,
    workspace: str,
    assigned_to: str = "worker",
) -> None:
    tasks.create(
        task_id=task_id,
        subject=task_id,
        description="",
        created_by="mike",
        assigned_to=assigned_to,
        priority="normal",
        risk="low",
        max_attempts=1,
        idempotency_key=task_id,
        workspace=workspace,
    )


def test_run_once_surfaces_planning_failures_once(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    with (
        TaskStore(tmp_path / "tasks.sqlite3") as tasks,
        SupervisorStore(tmp_path / "supervisor.sqlite3") as runs,
    ):
        _create_task(tasks, task_id="T-BAD-WORKER", workspace=str(workspace), assigned_to="ghost")
        supervisor = Supervisor(_config(tmp_path), tasks, runs, home=tmp_path / "home")

        first = supervisor.run_once()
        second = supervisor.run_once()

        assert first.runs == ()
        assert len(first.skipped) == 1
        assert first.skipped[0][0] == "T-BAD-WORKER"
        assert "ghost" in first.skipped[0][1]
        assert "not an enabled worker" in first.skipped[0][1]
        assert second.skipped == ()
        events = [item.event for item in runs.audit_records()]
        assert events.count("plan-skipped") == 1
        assert "T-BAD-WORKER" in runs.audit_records()[0].detail


def test_run_once_keeps_in_flight_tasks_quiet(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    with (
        TaskStore(tmp_path / "tasks.sqlite3") as tasks,
        SupervisorStore(tmp_path / "supervisor.sqlite3") as runs,
    ):
        _create_task(tasks, task_id="T-WAIT", workspace=str(workspace))
        supervisor = Supervisor(_config(tmp_path), tasks, runs, home=tmp_path / "home")

        planned = supervisor.run_once()
        again = supervisor.run_once()

        assert len(planned.runs) == 1
        assert planned.runs[0].state == "awaiting-approval"
        assert planned.skipped == ()
        assert again.runs == ()
        assert again.skipped == ()
        assert [item.event for item in runs.audit_records()] == ["run-created"]


def test_run_once_plans_valid_task_and_reports_sibling_failure(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    with (
        TaskStore(tmp_path / "tasks.sqlite3") as tasks,
        SupervisorStore(tmp_path / "supervisor.sqlite3") as runs,
    ):
        _create_task(tasks, task_id="T-OK", workspace=str(workspace))
        _create_task(tasks, task_id="T-OUTSIDE", workspace=str(tmp_path / "missing"))
        supervisor = Supervisor(_config(tmp_path), tasks, runs, home=tmp_path / "home")

        tick = supervisor.run_once()

        assert [run.task_id for run in tick.runs] == ["T-OK"]
        assert tick.skipped[0][0] == "T-OUTSIDE"
        assert "workspace does not exist" in tick.skipped[0][1]


def test_serve_prints_a_planning_skip_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    config = SupervisorConfig(
        group="test-group",
        peer="supervisor",
        mode="approval",
        allowed_workspace_roots=(tmp_path,),
        workers=_workers(),
        require_cross_vendor_review=False,
        poll_interval_seconds=0.05,
    )
    with (
        TaskStore(tmp_path / "tasks.sqlite3") as tasks,
        SupervisorStore(tmp_path / "supervisor.sqlite3") as runs,
    ):
        _create_task(
            tasks, task_id="T-SERVE", workspace=str(workspace), assigned_to="ghost"
        )
        supervisor = Supervisor(config, tasks, runs, home=tmp_path / "home")
        supervisor.serve(stop_after=0.12)

    err = capsys.readouterr().err
    assert err.count("skipped T-SERVE") == 1
    assert "not an enabled worker" in err


def test_once_cli_exits_nonzero_when_every_task_is_unplannable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    home = tmp_path / "home"
    root = tmp_path / "workspaces"
    root.mkdir(parents=True)
    home.mkdir()
    config_path = tmp_path / "supervisor.toml"
    config_path.write_text(
        f'''[supervisor]
group = "test-group"
peer = "supervisor"
mode = "approval"
allowed_workspace_roots = ["{root}"]
max_review_rounds = 2
require_cross_vendor_review = false

[workers.worker]
vendor = "command"
executable = "/bin/true"
argv = ["worker.py"]
roles = ["worker"]
capabilities = ["coding"]

[workers.critic]
vendor = "command"
executable = "/bin/true"
argv = ["critic.py"]
roles = ["critic"]

[workers.verifier]
vendor = "command"
executable = "/bin/true"
argv = ["verifier.py"]
roles = ["verifier"]
''',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    with TaskStore(home / ".claude-mesh" / "groups" / "test-group" / "tasks.sqlite3") as tasks:
        _create_task(tasks, task_id="T-CLI", workspace=str(tmp_path / "elsewhere"))

    result = supervisor_run("once", config_path=config_path)

    captured = capsys.readouterr()
    assert result == 1
    assert "skipped T-CLI" in captured.err
    assert "workspace does not exist" in captured.err
    assert captured.out.strip() == "no records"
