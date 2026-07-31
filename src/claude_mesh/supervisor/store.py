"""Crash-safe supervisor run, approval, artifact, and audit ledger."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from claude_mesh.identity import utc_now
from claude_mesh.storage import ensure_directory


class RunConflict(RuntimeError):  # noqa: N818 - public lifecycle vocabulary
    """Raised when a supervisor state transition loses a race or is invalid."""


ACTIVE_STATES = {
    "running-worker",
    "running-critic",
    "running-revision",
    "running-verifier",
}
TERMINAL_STATES = {"passed", "failed", "blocked", "cancelled"}


@dataclass(frozen=True)
class RunRecord:
    id: str
    task_id: str
    state: str
    worker: str
    critics_json: str
    verifier: str
    workspace: str
    execution_workspace: str
    risk: str
    mode: str
    round: int
    approved_by: str | None
    approved_at: str | None
    created_at: str
    updated_at: str
    error: str | None
    final_evidence: str | None
    estimated_cost_usd: float
    config_sha256: str

    @property
    def critics(self) -> tuple[str, ...]:
        return tuple(json.loads(self.critics_json))


@dataclass(frozen=True)
class ArtifactRecord:
    id: int
    run_id: str
    phase: str
    actor: str
    round: int
    payload: str
    sha256: str
    created_at: str


@dataclass(frozen=True)
class AuditRecord:
    id: int
    run_id: str | None
    event: str
    actor: str
    detail: str
    created_at: str


def supervisor_db_path(home: Path, group: str) -> Path:
    return home / ".claude-mesh" / "groups" / group / "supervisor.sqlite3"


class SupervisorStore:
    def __init__(self, path: Path):
        ensure_directory(path.parent)
        self.path = path
        self.conn = sqlite3.connect(path, timeout=5.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = FULL")
        self._schema()
        os.chmod(path, 0o600)

    def __enter__(self) -> SupervisorStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.conn.close()

    def _schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                state TEXT NOT NULL,
                worker TEXT NOT NULL,
                critics_json TEXT NOT NULL,
                verifier TEXT NOT NULL,
                workspace TEXT NOT NULL,
                execution_workspace TEXT NOT NULL DEFAULT '',
                risk TEXT NOT NULL,
                mode TEXT NOT NULL,
                round INTEGER NOT NULL DEFAULT 0,
                approved_by TEXT,
                approved_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error TEXT,
                final_evidence TEXT,
                estimated_cost_usd REAL NOT NULL DEFAULT 0,
                config_sha256 TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_runs_state ON runs(state, updated_at);
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                actor TEXT NOT NULL,
                round INTEGER NOT NULL,
                payload TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                event TEXT NOT NULL,
                actor TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        existing = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        if "config_sha256" not in existing:
            self.conn.execute(
                "ALTER TABLE runs ADD COLUMN config_sha256 TEXT NOT NULL DEFAULT ''"
            )
        self.conn.commit()

    @staticmethod
    def _run(row: sqlite3.Row) -> RunRecord:
        return RunRecord(**dict(row))

    def create_run(
        self,
        *,
        task_id: str,
        state: str,
        worker: str,
        critics: tuple[str, ...],
        verifier: str,
        workspace: Path,
        risk: str,
        mode: str,
        config_sha256: str = "",
    ) -> RunRecord:
        active = self.conn.execute(
            "SELECT id, state FROM runs WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if active and active["state"] not in TERMINAL_STATES:
            raise RunConflict(
                f"task {task_id!r} already has active run {active['id']} "
                f"in state {active['state']}"
            )
        run_id = f"run-{uuid.uuid4()}"
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO runs (
                id, task_id, state, worker, critics_json, verifier, workspace,
                risk, mode, created_at, updated_at, config_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                task_id,
                state,
                worker,
                json.dumps(critics),
                verifier,
                str(workspace),
                risk,
                mode,
                now,
                now,
                config_sha256,
            ),
        )
        self._audit(run_id, "run-created", "supervisor", f"state={state}")
        self.conn.commit()
        result = self.get_run(run_id)
        assert result is not None
        return result

    def get_run(self, run_id: str) -> RunRecord | None:
        row = self.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._run(row) if row else None

    def list_runs(self, states: set[str] | None = None) -> list[RunRecord]:
        if states:
            placeholders = ",".join("?" for _ in states)
            rows = self.conn.execute(
                f"SELECT * FROM runs WHERE state IN ({placeholders}) "  # noqa: S608
                "ORDER BY created_at DESC",
                tuple(sorted(states)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC"
            ).fetchall()
        return [self._run(row) for row in rows]

    def approve(self, run_id: str, approved_by: str) -> RunRecord:
        if not approved_by.strip():
            raise RunConflict("approval requires an actor")
        now = utc_now()
        changed = self.conn.execute(
            """
            UPDATE runs SET state = 'approved', approved_by = ?, approved_at = ?,
                updated_at = ?
            WHERE id = ? AND state = 'awaiting-approval'
            """,
            (approved_by, now, now, run_id),
        ).rowcount
        if changed != 1:
            raise RunConflict(f"run {run_id!r} is not awaiting approval")
        self._audit(run_id, "approved", approved_by, "operator approval recorded")
        self.conn.commit()
        result = self.get_run(run_id)
        assert result is not None
        return result

    def transition(
        self,
        run_id: str,
        *,
        expected: set[str],
        state: str,
        actor: str,
        detail: str = "",
        round_: int | None = None,
        execution_workspace: Path | None = None,
        error: str | None = None,
        final_evidence: str | None = None,
        estimated_cost_usd: float | None = None,
    ) -> RunRecord:
        placeholders = ",".join("?" for _ in expected)
        assignments = ["state = ?", "updated_at = ?", "error = ?"]
        values: list[object] = [state, utc_now(), error]
        if round_ is not None:
            assignments.append("round = ?")
            values.append(round_)
        if execution_workspace is not None:
            assignments.append("execution_workspace = ?")
            values.append(str(execution_workspace))
        if final_evidence is not None:
            assignments.append("final_evidence = ?")
            values.append(final_evidence)
        if estimated_cost_usd is not None:
            assignments.append("estimated_cost_usd = ?")
            values.append(estimated_cost_usd)
        values.extend([run_id, *sorted(expected)])
        sql = (
            f"UPDATE runs SET {', '.join(assignments)} WHERE id = ? "  # noqa: S608
            f"AND state IN ({placeholders})"
        )
        changed = self.conn.execute(sql, tuple(values)).rowcount
        if changed != 1:
            current = self.get_run(run_id)
            raise RunConflict(
                f"run {run_id!r} expected {sorted(expected)}, "
                f"found {current.state if current else 'missing'}"
            )
        self._audit(run_id, f"state:{state}", actor, detail)
        self.conn.commit()
        result = self.get_run(run_id)
        assert result is not None
        return result

    def add_artifact(
        self,
        run_id: str,
        *,
        phase: str,
        actor: str,
        round_: int,
        payload: str,
    ) -> ArtifactRecord:
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        now = utc_now()
        cursor = self.conn.execute(
            """
            INSERT INTO artifacts (run_id, phase, actor, round, payload, sha256, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, phase, actor, round_, payload, digest, now),
        )
        self._audit(run_id, f"artifact:{phase}", actor, f"sha256={digest}")
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM artifacts WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        assert row is not None
        return ArtifactRecord(**dict(row))

    def artifacts(self, run_id: str) -> list[ArtifactRecord]:
        rows = self.conn.execute(
            "SELECT * FROM artifacts WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [ArtifactRecord(**dict(row)) for row in rows]

    def add_cost(self, run_id: str, cost_usd: float) -> RunRecord:
        if cost_usd < 0:
            raise RunConflict("cost cannot be negative")
        changed = self.conn.execute(
            """
            UPDATE runs SET estimated_cost_usd = estimated_cost_usd + ?,
                updated_at = ?
            WHERE id = ?
            """,
            (cost_usd, utc_now(), run_id),
        ).rowcount
        if changed != 1:
            raise RunConflict(f"unknown run {run_id!r}")
        self._audit(run_id, "cost", "supervisor", f"usd={cost_usd:.6f}")
        self.conn.commit()
        result = self.get_run(run_id)
        assert result is not None
        return result

    def record_audit(
        self, run_id: str | None, event: str, actor: str, detail: str
    ) -> None:
        self._audit(run_id, event, actor, detail)
        self.conn.commit()

    def audit_records(self, run_id: str | None = None) -> list[AuditRecord]:
        if run_id is None:
            rows = self.conn.execute("SELECT * FROM audit ORDER BY id").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM audit WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return [AuditRecord(**dict(row)) for row in rows]

    def recover_interrupted(self) -> list[RunRecord]:
        placeholders = ",".join("?" for _ in ACTIVE_STATES)
        rows = self.conn.execute(
            f"SELECT id FROM runs WHERE state IN ({placeholders})",  # noqa: S608
            tuple(sorted(ACTIVE_STATES)),
        ).fetchall()
        recovered: list[RunRecord] = []
        for row in rows:
            recovered.append(
                self.transition(
                    row["id"],
                    expected=ACTIVE_STATES,
                    state="blocked",
                    actor="supervisor-recovery",
                    detail="supervisor stopped during an active model process",
                    error="interrupted; manual review required before retry",
                )
            )
        return recovered

    def _audit(self, run_id: str | None, event: str, actor: str, detail: str) -> None:
        self.conn.execute(
            "INSERT INTO audit (run_id, event, actor, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, event, actor, detail, utc_now()),
        )
