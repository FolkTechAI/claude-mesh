"""Transactional task ownership for the same-machine mesh.

FTAI remains the durable human-readable event stream. SQLite is the narrow
coordination ledger that provides compare-and-set ownership, leases, retries,
and idempotency under concurrent agents.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from claude_mesh.identity import utc_now
from claude_mesh.storage import ensure_directory


class TaskConflict(RuntimeError):  # noqa: N818 - public lifecycle vocabulary
    """Raised when a task transition violates ownership or lifecycle rules."""


@dataclass(frozen=True)
class TaskRecord:
    id: str
    subject: str
    description: str
    created_by: str
    assigned_to: str
    status: str
    priority: str
    risk: str
    created_at: str
    updated_at: str
    lease_owner: str | None
    lease_until: str | None
    attempt: int
    max_attempts: int
    evidence: str | None
    last_error: str | None
    verified_by: str | None
    verification: str | None
    idempotency_key: str
    workspace: str
    capability: str
    acceptance_criteria: str
    approval_required: int


def task_db_path(home: Path, group: str) -> Path:
    return home / ".claude-mesh" / "groups" / group / "tasks.sqlite3"


class TaskStore:
    def __init__(self, path: Path):
        ensure_directory(path.parent)
        self.path = path
        self.conn = sqlite3.connect(path, timeout=5.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = FULL")
        self._create_schema()
        os.chmod(path, 0o600)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> TaskStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _create_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL,
                assigned_to TEXT NOT NULL,
                status TEXT NOT NULL,
                priority TEXT NOT NULL,
                risk TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                lease_owner TEXT,
                lease_until TEXT,
                attempt INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                evidence TEXT,
                last_error TEXT,
                verified_by TEXT,
                verification TEXT,
                idempotency_key TEXT NOT NULL UNIQUE,
                workspace TEXT NOT NULL DEFAULT '',
                capability TEXT NOT NULL DEFAULT 'coding',
                acceptance_criteria TEXT NOT NULL DEFAULT '',
                approval_required INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        existing = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        additions = {
            "workspace": "TEXT NOT NULL DEFAULT ''",
            "capability": "TEXT NOT NULL DEFAULT 'coding'",
            "acceptance_criteria": "TEXT NOT NULL DEFAULT ''",
            "approval_required": "INTEGER NOT NULL DEFAULT 1",
        }
        for column, definition in additions.items():
            if column not in existing:
                self.conn.execute(
                    f"ALTER TABLE tasks ADD COLUMN {column} {definition}"  # noqa: S608
                )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_status_assignee "
            "ON tasks(status, assigned_to)"
        )
        self.conn.commit()

    @staticmethod
    def _record(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(**dict(row))

    def get(self, task_id: str) -> TaskRecord | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._record(row) if row else None

    def create(
        self,
        *,
        task_id: str,
        subject: str,
        description: str,
        created_by: str,
        assigned_to: str,
        priority: str,
        risk: str,
        max_attempts: int,
        idempotency_key: str,
        workspace: str = "",
        capability: str = "coding",
        acceptance_criteria: str = "",
        approval_required: bool = True,
    ) -> tuple[TaskRecord, bool]:
        existing = self.conn.execute(
            "SELECT * FROM tasks WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing:
            return self._record(existing), False
        now = utc_now()
        try:
            self.conn.execute(
                """
                INSERT INTO tasks (
                    id, subject, description, created_by, assigned_to, status,
                    priority, risk, created_at, updated_at, max_attempts,
                    idempotency_key, workspace, capability,
                    acceptance_criteria, approval_required
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    subject,
                    description,
                    created_by,
                    assigned_to,
                    priority,
                    risk,
                    now,
                    now,
                    max_attempts,
                    idempotency_key,
                    workspace,
                    capability,
                    acceptance_criteria,
                    int(approval_required),
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            raise TaskConflict(f"task {task_id!r} already exists") from exc
        record = self.get(task_id)
        assert record is not None
        return record, True

    def claim(self, task_id: str, peer: str, lease_until: str) -> TaskRecord:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise TaskConflict(f"unknown task {task_id!r}")
            record = self._record(row)
            if record.assigned_to != peer:
                raise TaskConflict(
                    f"task {task_id!r} is assigned to {record.assigned_to!r}, not {peer!r}"
                )
            if record.status not in {"pending", "failed"}:
                raise TaskConflict(
                    f"task {task_id!r} cannot be claimed from status {record.status!r}"
                )
            if record.attempt >= record.max_attempts:
                raise TaskConflict(f"task {task_id!r} exhausted its retry budget")
            now = utc_now()
            self.conn.execute(
                """
                UPDATE tasks
                SET status = 'accepted', lease_owner = ?, lease_until = ?,
                    attempt = attempt + 1, updated_at = ?, last_error = NULL
                WHERE id = ?
                """,
                (peer, lease_until, now, task_id),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        result = self.get(task_id)
        assert result is not None
        return result

    def start(self, task_id: str, peer: str, lease_until: str) -> TaskRecord:
        return self._owned_transition(
            task_id,
            peer,
            allowed={"accepted", "in-progress"},
            status="in-progress",
            lease_until=lease_until,
        )

    def renew(self, task_id: str, peer: str, lease_until: str) -> TaskRecord:
        """Extend an active lease without changing task state."""
        return self._owned_transition(
            task_id,
            peer,
            allowed={"accepted", "in-progress"},
            status="in-progress",
            lease_until=lease_until,
        )

    def complete(self, task_id: str, peer: str, evidence: str) -> TaskRecord:
        if not evidence.strip():
            raise TaskConflict("completion requires non-empty evidence")
        return self._owned_transition(
            task_id,
            peer,
            allowed={"accepted", "in-progress"},
            status="completed",
            evidence=evidence,
            lease_until=None,
        )

    def fail(self, task_id: str, peer: str, error: str) -> TaskRecord:
        if not error.strip():
            raise TaskConflict("failure requires a reason")
        return self._owned_transition(
            task_id,
            peer,
            allowed={"accepted", "in-progress"},
            status="failed",
            last_error=error,
            lease_until=None,
        )

    def verify(
        self,
        task_id: str,
        verifier: str,
        verdict: str,
        evidence: str,
    ) -> TaskRecord:
        if verdict not in {"pass", "fail"}:
            raise TaskConflict("verification verdict must be pass or fail")
        if not evidence.strip():
            raise TaskConflict("verification requires evidence")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise TaskConflict(f"unknown task {task_id!r}")
            record = self._record(row)
            if record.status != "completed":
                raise TaskConflict(
                    f"task {task_id!r} must be completed before verification"
                )
            if verifier == record.assigned_to:
                raise TaskConflict(
                    f"task {task_id!r} must be verified by a peer other than "
                    f"its assignee {record.assigned_to!r}"
                )
            status = "verified" if verdict == "pass" else "rejected"
            self.conn.execute(
                """
                UPDATE tasks
                SET status = ?, verified_by = ?, verification = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, verifier, evidence, utc_now(), task_id),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        result = self.get(task_id)
        assert result is not None
        return result

    def fail_verification(self, task_id: str, reason: str) -> TaskRecord:
        """Return a completed task to the retry queue when verification crashes.

        This is deliberately different from a verifier's ``fail`` verdict. A
        crashed or malformed verifier did not establish that the work is bad;
        it established only that the supervisor cannot safely accept it.
        """
        if not reason.strip():
            raise TaskConflict("verification failure requires a reason")
        now = utc_now()
        changed = self.conn.execute(
            """
            UPDATE tasks
            SET status = 'failed', lease_owner = NULL, lease_until = NULL,
                last_error = ?, updated_at = ?
            WHERE id = ? AND status = 'completed'
            """,
            (reason, now, task_id),
        ).rowcount
        if changed != 1:
            current = self.get(task_id)
            raise TaskConflict(
                f"task {task_id!r} must be completed before verification failure; "
                f"found {current.status if current else 'missing'}"
            )
        self.conn.commit()
        result = self.get(task_id)
        assert result is not None
        return result

    def requeue_expired(self, now: str | None = None) -> list[TaskRecord]:
        now = now or utc_now()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM tasks
                WHERE status IN ('accepted', 'in-progress')
                  AND lease_until IS NOT NULL
                  AND lease_until < ?
                """,
                (now,),
            ).fetchall()
            for row in rows:
                record = self._record(row)
                status = "pending" if record.attempt < record.max_attempts else "dead-letter"
                self.conn.execute(
                    """
                    UPDATE tasks
                    SET status = ?, lease_owner = NULL, lease_until = NULL,
                        updated_at = ?, last_error = 'lease expired'
                    WHERE id = ?
                    """,
                    (status, now, record.id),
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        records: list[TaskRecord] = []
        for row in rows:
            record = self.get(row["id"])
            if record is not None:
                records.append(record)
        return records

    def list(self, statuses: set[str] | None = None) -> list[TaskRecord]:
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            rows = self.conn.execute(
                f"SELECT * FROM tasks WHERE status IN ({placeholders}) ORDER BY updated_at",  # noqa: S608
                tuple(sorted(statuses)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tasks ORDER BY updated_at"
            ).fetchall()
        return [self._record(row) for row in rows]

    def _owned_transition(
        self,
        task_id: str,
        peer: str,
        *,
        allowed: set[str],
        status: str,
        lease_until: str | None,
        evidence: str | None = None,
        last_error: str | None = None,
    ) -> TaskRecord:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise TaskConflict(f"unknown task {task_id!r}")
            record = self._record(row)
            if record.lease_owner != peer:
                raise TaskConflict(
                    f"task {task_id!r} lease belongs to {record.lease_owner!r}, not {peer!r}"
                )
            if record.status not in allowed:
                raise TaskConflict(
                    f"task {task_id!r} cannot move from {record.status!r} to {status!r}"
                )
            self.conn.execute(
                """
                UPDATE tasks
                SET status = ?, lease_until = ?, evidence = COALESCE(?, evidence),
                    last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, lease_until, evidence, last_error, utc_now(), task_id),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        result = self.get(task_id)
        assert result is not None
        return result
