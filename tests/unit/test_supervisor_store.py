from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from claude_mesh.supervisor.store import RunConflict, SupervisorStore


def _run(store: SupervisorStore, workspace: Path):
    return store.create_run(
        task_id="T-1",
        state="awaiting-approval",
        worker="worker",
        critics=("critic",),
        verifier="verifier",
        workspace=workspace,
        risk="medium",
        mode="approval",
    )


def test_approval_and_transitions_are_compare_and_set(tmp_path: Path):
    with SupervisorStore(tmp_path / "supervisor.sqlite3") as store:
        run = _run(store, tmp_path / "project")
        approved = store.approve(run.id, "mike")
        assert approved.state == "approved"
        assert approved.approved_by == "mike"
        with pytest.raises(RunConflict, match="not awaiting"):
            store.approve(run.id, "someone-else")
        running = store.transition(
            run.id,
            expected={"approved"},
            state="running-worker",
            actor="supervisor",
        )
        assert running.state == "running-worker"
        with pytest.raises(RunConflict, match="expected"):
            store.transition(
                run.id,
                expected={"approved"},
                state="passed",
                actor="worker",
            )


def test_artifacts_are_content_addressed(tmp_path: Path):
    with SupervisorStore(tmp_path / "supervisor.sqlite3") as store:
        run = _run(store, tmp_path / "project")
        artifact = store.add_artifact(
            run.id,
            phase="critic",
            actor="critic",
            round_=0,
            payload='{"verdict":"challenge"}',
        )

        assert artifact.sha256 == hashlib.sha256(artifact.payload.encode()).hexdigest()
        assert store.artifacts(run.id) == [artifact]


def test_cost_and_audit_are_append_only(tmp_path: Path):
    with SupervisorStore(tmp_path / "supervisor.sqlite3") as store:
        run = _run(store, tmp_path / "project")
        updated = store.add_cost(run.id, 0.125)
        store.record_audit(run.id, "receipt:verification", "supervisor", "to=mike")

        assert updated.estimated_cost_usd == pytest.approx(0.125)
        events = [item.event for item in store.audit_records(run.id)]
        assert events == ["run-created", "cost", "receipt:verification"]


def test_recovery_blocks_interrupted_runs(tmp_path: Path):
    with SupervisorStore(tmp_path / "supervisor.sqlite3") as store:
        run = _run(store, tmp_path / "project")
        store.approve(run.id, "mike")
        store.transition(
            run.id,
            expected={"approved"},
            state="running-critic",
            actor="supervisor",
        )

        recovered = store.recover_interrupted()

        assert recovered[0].state == "blocked"
        assert "manual review" in (recovered[0].error or "")
