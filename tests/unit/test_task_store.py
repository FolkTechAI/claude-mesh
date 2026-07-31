from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path

import pytest

from claude_mesh.task_store import TaskConflict, TaskStore


def _create(store: TaskStore, task_id: str = "T-1"):
    return store.create(
        task_id=task_id,
        subject="Test task",
        description="Do the work",
        created_by="alpha",
        assigned_to="beta",
        priority="high",
        risk="medium",
        max_attempts=2,
        idempotency_key=f"idem-{task_id}",
    )


def _future(seconds: int = 300) -> str:
    return (
        dt.datetime.now(dt.UTC) + dt.timedelta(seconds=seconds)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")


def test_create_is_idempotent(tmp_path: Path):
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        first, created = _create(store)
        second, created_again = _create(store)
    assert created is True
    assert created_again is False
    assert first.id == second.id


def test_only_assignee_can_claim(tmp_path: Path):
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        _create(store)
        with pytest.raises(TaskConflict, match="assigned"):
            store.claim("T-1", "gamma", _future())


def test_completion_requires_owner_and_evidence(tmp_path: Path):
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        _create(store)
        store.claim("T-1", "beta", _future())
        with pytest.raises(TaskConflict, match="evidence"):
            store.complete("T-1", "beta", "")
        with pytest.raises(TaskConflict, match="lease belongs"):
            store.complete("T-1", "gamma", "tests passed")
        complete = store.complete("T-1", "beta", "tests passed")
    assert complete.status == "completed"
    assert complete.evidence == "tests passed"


def test_verification_is_separate_transition(tmp_path: Path):
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        _create(store)
        store.claim("T-1", "beta", _future())
        store.complete("T-1", "beta", "artifact sha256")
        verified = store.verify("T-1", "ake", "pass", "checks 12/12")
    assert verified.status == "verified"
    assert verified.verified_by == "ake"


def test_assignee_cannot_self_verify(tmp_path: Path):
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        _create(store)
        store.claim("T-1", "beta", _future())
        store.complete("T-1", "beta", "artifact sha256")
        with pytest.raises(TaskConflict, match="other than"):
            store.verify("T-1", "beta", "pass", "looks good")


def test_verifier_crash_returns_completed_task_to_retry_queue(tmp_path: Path):
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        _create(store)
        store.claim("T-1", "beta", _future())
        store.complete("T-1", "beta", "artifact sha256")
        failed = store.fail_verification("T-1", "verifier process crashed")

    assert failed.status == "failed"
    assert failed.lease_owner is None
    assert failed.last_error == "verifier process crashed"


def test_expired_lease_requeues_then_dead_letters(tmp_path: Path):
    past = "2020-01-01T00:00:00.000000Z"
    with TaskStore(tmp_path / "tasks.sqlite3") as store:
        _create(store)
        store.claim("T-1", "beta", past)
        first = store.requeue_expired()
        assert first[0].status == "pending"
        store.claim("T-1", "beta", past)
        second = store.requeue_expired()
    assert second[0].status == "dead-letter"


def test_concurrent_claim_has_exactly_one_winner(tmp_path: Path):
    path = tmp_path / "tasks.sqlite3"
    with TaskStore(path) as store:
        _create(store)

    barrier = threading.Barrier(3)
    outcomes: list[str] = []

    def claim() -> None:
        with TaskStore(path) as store:
            barrier.wait()
            try:
                store.claim("T-1", "beta", _future())
            except TaskConflict:
                outcomes.append("conflict")
            else:
                outcomes.append("claimed")

    first = threading.Thread(target=claim)
    second = threading.Thread(target=claim)
    first.start()
    second.start()
    barrier.wait()
    first.join()
    second.join()

    assert sorted(outcomes) == ["claimed", "conflict"]
