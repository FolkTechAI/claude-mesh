from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from claude_mesh.supervisor.config import SupervisorConfig, WorkerConfig
from claude_mesh.supervisor.engine import Supervisor, SupervisorError
from claude_mesh.supervisor.store import SupervisorStore
from claude_mesh.task_store import TaskStore


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git")
    assert git is not None
    return subprocess.run(  # noqa: S603 - test-controlled argv
        [git, "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _agent(name: str, role: str, script: Path) -> WorkerConfig:
    return WorkerConfig(
        name=name,
        vendor="command",
        roles=(role,),
        capabilities=("coding",) if role == "worker" else (),
        executable=sys.executable,
        timeout_seconds=10,
        argv=(str(script), "{role}"),
    )


def test_worker_is_challenged_revises_then_independently_verified(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(
        repo,
        "-c",
        "user.name=Mesh Test",
        "-c",
        "user.email=mesh@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )

    script = tmp_path / "adversaries.py"
    script.write_text(
        """import json, pathlib, sys
role = sys.argv[1]
prompt = sys.stdin.read()
target = pathlib.Path('result.txt')
if role == 'worker':
    revised = 'revision round' in prompt
    target.write_text('safe\\n' if revised else 'unsafe\\n')
    print(json.dumps({'status':'completed','summary':'revised' if revised else 'first',
        'evidence':'result.txt inspected','changed_files':['result.txt'],
        'tests':['fixture check'],'remaining_risks':[]}))
elif role == 'critic':
    safe = target.read_text() == 'safe\\n'
    findings = [] if safe else [{'severity':'high','title':'unsafe value',
        'evidence':'result.txt contains unsafe','reproduction':'read result.txt'}]
    print(json.dumps({'verdict':'pass' if safe else 'challenge',
        'attack_summary':'safe' if safe else 'falsified','findings':findings,
        'confidence':'high'}))
else:
    safe = target.read_text() == 'safe\\n'
    print(json.dumps({'verdict':'pass' if safe else 'fail',
        'checks':['read result.txt'],'evidence':target.read_text().strip(),
        'residual_risk':'none' if safe else 'unsafe value'}))
""",
        encoding="utf-8",
    )
    workers = {
        "worker": _agent("worker", "worker", script),
        "critic": _agent("critic", "critic", script),
        "verifier": _agent("verifier", "verifier", script),
    }
    config = SupervisorConfig(
        group="test-group",
        peer="supervisor",
        mode="approval",
        allowed_workspace_roots=(tmp_path,),
        workers=workers,
        max_review_rounds=2,
        require_cross_vendor_review=False,
        require_distinct_verifier=True,
    )
    home = tmp_path / "home"
    with (
        TaskStore(tmp_path / "tasks.sqlite3") as tasks,
        SupervisorStore(tmp_path / "supervisor.sqlite3") as runs,
    ):
        tasks.create(
            task_id="T-ADV",
            subject="Produce a safe result",
            description="The result must contain safe",
            created_by="mike",
            assigned_to="worker",
            priority="high",
            risk="medium",
            max_attempts=2,
            idempotency_key="adversarial-fixture",
            workspace=str(repo),
            capability="coding",
            acceptance_criteria="result.txt contains exactly safe",
        )
        supervisor = Supervisor(config, tasks, runs, home=home)

        planned = supervisor.run_task("T-ADV")
        assert planned.state == "awaiting-approval"
        approved = supervisor.approve(planned.id, "mike")
        assert approved.state == "approved"
        result = supervisor.execute(planned.id)

        assert result.state == "passed"
        task = tasks.get("T-ADV")
        assert task is not None and task.status == "verified"
        assert task.verified_by == "verifier"
        artifacts = runs.artifacts(planned.id)
        assert [item.phase for item in artifacts] == [
            "worker",
            "critic",
            "revision",
            "critic",
            "verifier",
        ]
        assert result.execution_workspace
        assert (Path(result.execution_workspace) / "result.txt").read_text() == "safe\n"
        mike_inbox = home / ".claude-mesh" / "groups" / "test-group" / "mike.ftai"
        receipts = mike_inbox.read_text(encoding="utf-8")
        assert "@verification" in receipts
        assert "@experience" in receipts
        assert "Resolved adversarial findings" in receipts


def test_automatic_mode_still_respects_task_approval_flag(tmp_path: Path):
    workers = {
        "worker": WorkerConfig("worker", "a", ("worker",), ("coding",), "/bin/true"),
        "critic": WorkerConfig("critic", "b", ("critic",), (), "/bin/true"),
        "verifier": WorkerConfig("verifier", "c", ("verifier",), (), "/bin/true"),
    }
    config = SupervisorConfig(
        group="test-group",
        peer="supervisor",
        mode="automatic",
        allowed_workspace_roots=(tmp_path,),
        workers=workers,
    )
    workspace = tmp_path / "repo"
    workspace.mkdir()
    with (
        TaskStore(tmp_path / "tasks.sqlite3") as tasks,
        SupervisorStore(tmp_path / "supervisor.sqlite3") as runs,
    ):
        tasks.create(
            task_id="T-GATED",
            subject="Gated",
            description="",
            created_by="mike",
            assigned_to="worker",
            priority="normal",
            risk="low",
            max_attempts=1,
            idempotency_key="gated",
            workspace=str(workspace),
            approval_required=True,
        )
        supervisor = Supervisor(config, tasks, runs, home=tmp_path / "home")
        planned = supervisor.plan("T-GATED")

        assert planned.state == "awaiting-approval"


def test_agent_identity_cannot_approve_and_config_change_invalidates_plan(
    tmp_path: Path,
):
    workers = {
        "worker": WorkerConfig("worker", "a", ("worker",), ("coding",), "/bin/true"),
        "critic": WorkerConfig("critic", "b", ("critic",), (), "/bin/true"),
        "verifier": WorkerConfig("verifier", "c", ("verifier",), (), "/bin/true"),
    }
    workspace = tmp_path / "repo"
    workspace.mkdir()
    base = SupervisorConfig(
        group="test-group",
        peer="supervisor",
        mode="approval",
        allowed_workspace_roots=(tmp_path,),
        workers=workers,
    )
    with (
        TaskStore(tmp_path / "tasks.sqlite3") as tasks,
        SupervisorStore(tmp_path / "supervisor.sqlite3") as runs,
    ):
        tasks.create(
            task_id="T-CONFIG",
            subject="Pinned config",
            description="",
            created_by="mike",
            assigned_to="worker",
            priority="normal",
            risk="low",
            max_attempts=1,
            idempotency_key="config",
            workspace=str(workspace),
        )
        supervisor = Supervisor(base, tasks, runs)
        planned = supervisor.plan("T-CONFIG")
        with pytest.raises(SupervisorError, match="agent identity"):
            supervisor.approve(planned.id, "critic")
        supervisor.approve(planned.id, "mike")
        changed = SupervisorConfig(
            group="test-group",
            peer="supervisor",
            mode="approval",
            allowed_workspace_roots=(tmp_path,),
            workers=workers,
            max_review_rounds=3,
        )
        with pytest.raises(SupervisorError, match="changed after planning"):
            Supervisor(changed, tasks, runs).execute(planned.id)


def test_observe_and_low_risk_automatic_modes_do_not_share_authority(tmp_path: Path):
    workers = {
        "worker": WorkerConfig("worker", "a", ("worker",), ("coding",), "/bin/true"),
        "critic": WorkerConfig("critic", "b", ("critic",), (), "/bin/true"),
        "verifier": WorkerConfig("verifier", "c", ("verifier",), (), "/bin/true"),
    }
    workspace = tmp_path / "repo"
    workspace.mkdir()
    with (
        TaskStore(tmp_path / "tasks.sqlite3") as tasks,
        SupervisorStore(tmp_path / "supervisor.sqlite3") as runs,
    ):
        for task_id, approval_required in (("T-OBS", False), ("T-AUTO", False)):
            tasks.create(
                task_id=task_id,
                subject=task_id,
                description="",
                created_by="mike",
                assigned_to="worker",
                priority="normal",
                risk="low",
                max_attempts=1,
                idempotency_key=task_id,
                workspace=str(workspace),
                approval_required=approval_required,
            )
        observe = SupervisorConfig(
            group="test-group",
            peer="supervisor",
            mode="observe",
            allowed_workspace_roots=(tmp_path,),
            workers=workers,
        )
        automatic = SupervisorConfig(
            group="test-group",
            peer="supervisor",
            mode="automatic",
            allowed_workspace_roots=(tmp_path,),
            workers=workers,
            automatic_max_risk="low",
        )

        assert Supervisor(observe, tasks, runs).plan("T-OBS").state == "planned"
        assert Supervisor(automatic, tasks, runs).plan("T-AUTO").state == "auto-approved"
