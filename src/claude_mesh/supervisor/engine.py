"""Deterministic supervisor and adversarial worker-critic-verifier loop."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from claude_mesh.config import MeshConfig
from claude_mesh.events import ExperienceEvent, VerificationEvent
from claude_mesh.identity import new_event_id, utc_now
from claude_mesh.publish import PublishError, publish_event
from claude_mesh.sanitize import SensitiveDataFilter, sanitize_body, sanitize_summary
from claude_mesh.supervisor.adapters import AdapterError, AgentResult, run_agent
from claude_mesh.supervisor.config import (
    SupervisorConfig,
    SupervisorConfigError,
    WorkerConfig,
    validate_workspace,
)
from claude_mesh.supervisor.prompts import critic_prompt, verifier_prompt, worker_prompt
from claude_mesh.supervisor.store import RunConflict, RunRecord, SupervisorStore
from claude_mesh.task_store import TaskConflict, TaskRecord, TaskStore


class SupervisorError(RuntimeError):
    """Raised when a task cannot be supervised safely."""


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Supervisor:
    def __init__(
        self,
        config: SupervisorConfig,
        task_store: TaskStore,
        run_store: SupervisorStore,
        *,
        home: Path | None = None,
    ):
        self.config = config
        self.tasks = task_store
        self.runs = run_store
        self.home = home or Path.home()

    def recover(self) -> list[RunRecord]:
        """Fail closed after a supervisor crash during a model invocation."""
        return self.runs.recover_interrupted()

    def plan(self, task_id: str) -> RunRecord:
        task = self._task(task_id)
        workspace = validate_workspace(task.workspace, self.config.allowed_workspace_roots)
        worker = self._select_worker(task)
        critics = self._select_critics(worker)
        verifier = self._select_verifier(worker, critics)
        state = self._initial_state(task)
        return self.runs.create_run(
            task_id=task.id,
            state=state,
            worker=worker.name,
            critics=tuple(critic.name for critic in critics),
            verifier=verifier.name,
            workspace=workspace,
            risk=task.risk,
            mode=self.config.mode,
            config_sha256=self._configuration_fingerprint(worker, critics, verifier),
        )

    def approve(self, run_id: str, approved_by: str) -> RunRecord:
        if approved_by == self.config.peer or approved_by in self.config.workers:
            raise SupervisorError("a configured agent identity cannot grant operator approval")
        return self.runs.approve(run_id, approved_by)

    def execute(self, run_id: str) -> RunRecord:
        run = self._run(run_id)
        if run.state not in {"approved", "auto-approved"}:
            raise SupervisorError(
                f"run {run.id} is {run.state!r}; approval is required before execution"
            )
        task = self._task(run.task_id)
        try:
            worker = self.config.workers[run.worker]
            critics = [self.config.workers[name] for name in run.critics]
            verifier = self.config.workers[run.verifier]
        except KeyError as exc:
            raise SupervisorError(
                f"approved run references missing worker {exc.args[0]!r}"
            ) from exc
        fingerprint = self._configuration_fingerprint(worker, critics, verifier)
        if not run.config_sha256 or fingerprint != run.config_sha256:
            raise SupervisorError(
                "supervisor or worker configuration changed after planning; "
                "create and approve a new run"
            )
        workspace = validate_workspace(run.workspace, self.config.allowed_workspace_roots)
        call_budget = self._per_call_budget(len(critics))

        try:
            execution_workspace = self._create_worktree(run, workspace)
            self.runs.transition(
                run.id,
                expected={"approved", "auto-approved"},
                state="running-worker",
                actor="supervisor",
                detail=f"worker={worker.name}",
                round_=0,
                execution_workspace=execution_workspace,
            )
            lease_until = self._lease_deadline()
            self.tasks.claim(task.id, worker.name, lease_until)
            self.tasks.start(task.id, worker.name, lease_until)

            worker_result = self._invoke(
                run,
                worker,
                "worker",
                worker_prompt(task, round_=0),
                execution_workspace,
                round_=0,
                call_budget=call_budget,
            )
            if worker_result.payload["status"] == "blocked":
                raise SupervisorError(
                    f"worker blocked: {worker_result.payload.get('summary', '')}"
                )

            all_critiques: list[dict[str, object]] = []
            round_ = 0
            while True:
                self.tasks.renew(task.id, worker.name, self._lease_deadline())
                self.runs.transition(
                    run.id,
                    expected={"running-worker", "running-revision"},
                    state="running-critic",
                    actor="supervisor",
                    detail=f"round={round_} critics={[item.name for item in critics]}",
                    round_=round_,
                )
                round_critiques = [
                    self._invoke(
                        run,
                        critic,
                        "critic",
                        critic_prompt(task, worker_result.payload, round_=round_),
                        execution_workspace,
                        round_=round_,
                        call_budget=call_budget,
                    ).payload
                    for critic in critics
                ]
                all_critiques.extend(round_critiques)
                challenges = [
                    critique
                    for critique in round_critiques
                    if critique.get("verdict") == "challenge"
                ]
                if not challenges:
                    break
                round_ += 1
                if round_ > self.config.max_review_rounds:
                    raise SupervisorError(
                        "adversarial findings remained after the revision budget"
                    )
                self.runs.transition(
                    run.id,
                    expected={"running-critic"},
                    state="running-revision",
                    actor="supervisor",
                    detail=f"round={round_} unresolved_challenges={len(challenges)}",
                    round_=round_,
                )
                self.tasks.renew(task.id, worker.name, self._lease_deadline())
                worker_result = self._invoke(
                    run,
                    worker,
                    "worker",
                    worker_prompt(
                        task,
                        round_=round_,
                        prior_output=worker_result.payload,
                        challenges=challenges,
                    ),
                    execution_workspace,
                    round_=round_,
                    phase="revision",
                    call_budget=call_budget,
                )
                if worker_result.payload["status"] == "blocked":
                    raise SupervisorError(
                        f"worker blocked during revision: "
                        f"{worker_result.payload.get('summary', '')}"
                    )

            completion_evidence = json.dumps(
                {
                    "worker": worker_result.payload,
                    "critics": all_critiques,
                    "worktree": str(execution_workspace),
                },
                sort_keys=True,
            )
            self.tasks.complete(task.id, worker.name, completion_evidence)
            self.runs.transition(
                run.id,
                expected={"running-critic"},
                state="running-verifier",
                actor="supervisor",
                detail=f"verifier={verifier.name}",
                round_=round_,
            )
            verification = self._invoke(
                run,
                verifier,
                "verifier",
                verifier_prompt(task, worker_result.payload, all_critiques),
                execution_workspace,
                round_=round_,
                call_budget=call_budget,
            )
            verdict = str(verification.payload["verdict"])
            evidence = json.dumps(verification.payload, sort_keys=True)
            self.tasks.verify(task.id, verifier.name, verdict, evidence)
            if verdict != "pass":
                failed = self.runs.transition(
                    run.id,
                    expected={"running-verifier"},
                    state="failed",
                    actor=verifier.name,
                    detail="independent verification failed",
                    error=evidence,
                    final_evidence=evidence,
                )
                self._publish_verification_receipt(task, failed, verification.payload)
                return failed
            passed = self.runs.transition(
                run.id,
                expected={"running-verifier"},
                state="passed",
                actor=verifier.name,
                detail="independent verification passed",
                final_evidence=evidence,
            )
            self._publish_verification_receipt(task, passed, verification.payload)
            self._publish_experience_receipt(task, passed, verification.payload)
            return passed
        except (
            AdapterError,
            OSError,
            RunConflict,
            subprocess.SubprocessError,
            TaskConflict,
            SupervisorError,
        ) as exc:
            self._record_failure(run.id, task, worker, str(exc))
            result = self.runs.get_run(run.id)
            assert result is not None
            return result

    def run_task(self, task_id: str) -> RunRecord:
        run = self.plan(task_id)
        if run.state == "auto-approved":
            return self.execute(run.id)
        return run

    def run_once(self) -> list[RunRecord]:
        """Plan every pending task that has no active supervisor run."""
        results: list[RunRecord] = []
        for task in self.tasks.list({"pending", "failed"}):
            try:
                result = self.run_task(task.id)
            except (SupervisorError, SupervisorConfigError, RunConflict):
                continue
            results.append(result)
            if len(results) >= self.config.max_concurrent_runs:
                break
        return results

    def serve(self, stop_after: float | None = None) -> None:
        """Foreground polling loop; process managers own daemonization."""
        started = time.monotonic()
        self.recover()
        while stop_after is None or time.monotonic() - started < stop_after:
            self.run_once()
            time.sleep(self.config.poll_interval_seconds)

    def _task(self, task_id: str) -> TaskRecord:
        task = self.tasks.get(task_id)
        if task is None:
            raise SupervisorError(f"unknown task {task_id!r}")
        return task

    def _run(self, run_id: str) -> RunRecord:
        run = self.runs.get_run(run_id)
        if run is None:
            raise SupervisorError(f"unknown run {run_id!r}")
        return run

    def _initial_state(self, task: TaskRecord) -> str:
        if self.config.mode == "observe":
            return "planned"
        eligible = (
            self.config.mode == "automatic"
            and not bool(task.approval_required)
            and RISK_ORDER.get(task.risk, 99)
            <= RISK_ORDER.get(self.config.automatic_max_risk, -1)
        )
        return "auto-approved" if eligible else "awaiting-approval"

    def _select_worker(self, task: TaskRecord) -> WorkerConfig:
        worker = self.config.workers.get(task.assigned_to)
        if (
            worker is None
            or not worker.enabled
            or "worker" not in worker.roles
            or task.capability not in worker.capabilities
        ):
            raise SupervisorError(
                f"assigned peer {task.assigned_to!r} is not an enabled worker "
                f"for capability {task.capability!r}"
            )
        return worker

    def _select_critics(self, worker: WorkerConfig) -> list[WorkerConfig]:
        candidates = [
            item
            for item in self.config.workers.values()
            if item.enabled and item.name != worker.name and "critic" in item.roles
        ]
        if self.config.require_cross_vendor_review:
            candidates = [item for item in candidates if item.vendor != worker.vendor]
        if not candidates:
            raise SupervisorError("no eligible independent critic")
        return sorted(candidates, key=lambda item: item.name)[:2]

    def _select_verifier(
        self, worker: WorkerConfig, critics: list[WorkerConfig]
    ) -> WorkerConfig:
        critic_names = {critic.name for critic in critics}
        candidates = [
            item
            for item in self.config.workers.values()
            if item.enabled and item.name != worker.name and "verifier" in item.roles
        ]
        if self.config.require_distinct_verifier:
            candidates = [item for item in candidates if item.name not in critic_names]
        if self.config.require_cross_vendor_review:
            candidates = [item for item in candidates if item.vendor != worker.vendor]
        if not candidates:
            raise SupervisorError("no eligible independent verifier")
        return sorted(candidates, key=lambda item: item.name)[0]

    def _configuration_fingerprint(
        self,
        worker: WorkerConfig,
        critics: list[WorkerConfig],
        verifier: WorkerConfig,
    ) -> str:
        policy = {
            "group": self.config.group,
            "peer": self.config.peer,
            "operator": self.config.operator,
            "mode": self.config.mode,
            "allowed_workspace_roots": [
                str(path) for path in self.config.allowed_workspace_roots
            ],
            "max_review_rounds": self.config.max_review_rounds,
            "max_run_cost_usd": self.config.max_run_cost_usd,
            "require_cross_vendor_review": self.config.require_cross_vendor_review,
            "require_distinct_verifier": self.config.require_distinct_verifier,
            "automatic_max_risk": self.config.automatic_max_risk,
            "worker": asdict(worker),
            "critics": [asdict(item) for item in critics],
            "verifier": asdict(verifier),
        }
        encoded = json.dumps(policy, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _create_worktree(self, run: RunRecord, workspace: Path) -> Path:
        git = shutil.which("git")
        if not git:
            raise SupervisorError("git is required for isolated coding execution")
        probe = subprocess.run(  # noqa: S603 - fixed git argv
            [git, "-C", str(workspace), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if probe.returncode != 0:
            raise SupervisorError("coding execution requires a git workspace")
        root = Path(probe.stdout.strip()).resolve()
        if root != workspace:
            workspace = root
        worktree_root = self.home / ".claude-mesh" / "worktrees" / self.config.group
        worktree_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = worktree_root / run.id
        if target.exists():
            raise SupervisorError(f"worktree target already exists: {target}")
        branch = f"folktech-mesh/{run.id.removeprefix('run-')[:12]}"
        created = subprocess.run(  # noqa: S603 - fixed git argv
            [git, "-C", str(workspace), "worktree", "add", "-b", branch, str(target), "HEAD"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if created.returncode != 0:
            raise SupervisorError(
                f"failed to create isolated worktree: {created.stderr.strip()}"
            )
        return target

    def _invoke(
        self,
        run: RunRecord,
        actor: WorkerConfig,
        role: str,
        prompt: str,
        workspace: Path,
        *,
        round_: int,
        call_budget: float,
        phase: str | None = None,
    ) -> AgentResult:
        result = run_agent(
            actor,
            role=role,
            prompt=prompt,
            workspace=workspace,
            max_budget_usd=call_budget,
        )
        artifact_payload = json.dumps(
            {
                "actor": result.actor,
                "vendor": result.vendor,
                "role": result.role,
                "payload": result.payload,
                "duration_seconds": result.duration_seconds,
                "cost_usd": result.cost_usd,
            },
            sort_keys=True,
        )
        artifact_payload = SensitiveDataFilter().redact(artifact_payload)
        self.runs.add_artifact(
            run.id,
            phase=phase or role,
            actor=actor.name,
            round_=round_,
            payload=artifact_payload,
        )
        if result.cost_usd is not None:
            updated = self.runs.add_cost(run.id, result.cost_usd)
            if updated.estimated_cost_usd > self.config.max_run_cost_usd:
                raise SupervisorError(
                    f"recorded model cost ${updated.estimated_cost_usd:.2f} exceeded "
                    f"run limit ${self.config.max_run_cost_usd:.2f}"
                )
        return result

    def _mesh_config(self, task: TaskRecord, run: RunRecord) -> MeshConfig:
        peers = list(
            dict.fromkeys(
                [
                    self.config.peer,
                    task.created_by,
                    task.assigned_to,
                    *run.critics,
                    run.verifier,
                ]
            )
        )
        return MeshConfig(
            mesh_group=self.config.group,
            mesh_peer=self.config.peer,
            mesh_peers=peers,
        )

    def _receipt_targets(self, task: TaskRecord) -> list[str]:
        return [
            peer
            for peer in dict.fromkeys([task.created_by, task.assigned_to])
            if peer != self.config.peer
        ]

    def _publish_verification_receipt(
        self,
        task: TaskRecord,
        run: RunRecord,
        verification: dict[str, object],
    ) -> None:
        if not self.config.publish_receipts:
            return
        artifact_hashes = ", ".join(
            f"{item.phase}:{item.sha256[:12]}" for item in self.runs.artifacts(run.id)
        )
        evidence = sanitize_body(
            SensitiveDataFilter().redact(
                f"run={run.id}; artifacts={artifact_hashes}; "
                f"evidence={verification.get('evidence', '')}"
            )
        )
        config = self._mesh_config(task, run)
        for target in self._receipt_targets(task):
            event = VerificationEvent(
                from_=self.config.peer,
                timestamp=utc_now(),
                id=f"verify-{run.id}",
                task_id=task.id,
                verdict=str(verification.get("verdict", "fail")),
                evidence=evidence,
                checks=sanitize_body(
                    json.dumps(verification.get("checks", []), sort_keys=True)
                ),
                to=target,
                event_id=new_event_id(),
            )
            self._publish_receipt(run.id, event, config, target, "verification")

    def _publish_experience_receipt(
        self,
        task: TaskRecord,
        run: RunRecord,
        verification: dict[str, object],
    ) -> None:
        if not self.config.publish_receipts:
            return
        finding_titles: list[str] = []
        for artifact in self.runs.artifacts(run.id):
            if artifact.phase != "critic":
                continue
            try:
                payload = json.loads(artifact.payload).get("payload", {})
            except (AttributeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            for finding in payload.get("findings", []):
                if isinstance(finding, dict) and finding.get("title"):
                    finding_titles.append(str(finding["title"]))
        lesson = (
            "Resolved adversarial findings before acceptance: "
            + "; ".join(dict.fromkeys(finding_titles))
            if finding_titles
            else "Independent critic and verifier found no reproducible blocking defect."
        )
        config = self._mesh_config(task, run)
        for target in self._receipt_targets(task):
            event = ExperienceEvent(
                from_=self.config.peer,
                timestamp=utc_now(),
                id=f"experience-{run.id}",
                task_id=task.id,
                outcome=sanitize_summary(
                    f"Passed adversarial supervision after {run.round} revision round(s)"
                ),
                lesson=sanitize_body(lesson),
                evidence=sanitize_body(
                    f"run={run.id}; verifier={run.verifier}; "
                    f"residual_risk={verification.get('residual_risk', '')}"
                ),
                verified_by=run.verifier,
                tags=["supervisor", "adversarial-review", "verified"],
                to=target,
                event_id=new_event_id(),
            )
            self._publish_receipt(run.id, event, config, target, "experience")

    def _publish_receipt(
        self,
        run_id: str,
        event: VerificationEvent | ExperienceEvent,
        config: MeshConfig,
        target: str,
        kind: str,
    ) -> None:
        try:
            publish_event(event, config=config, home=self.home, to=target)
        except (OSError, PublishError) as exc:
            self.runs.record_audit(
                run_id,
                f"receipt-failed:{kind}",
                "supervisor",
                sanitize_summary(str(exc)),
            )
        else:
            self.runs.record_audit(
                run_id,
                f"receipt:{kind}",
                "supervisor",
                f"to={target}",
            )

    def _record_failure(
        self,
        run_id: str,
        task: TaskRecord,
        worker: WorkerConfig,
        error: str,
    ) -> None:
        current_task = self.tasks.get(task.id)
        if current_task and current_task.status in {"accepted", "in-progress"}:
            try:
                self.tasks.fail(task.id, worker.name, error)
            except TaskConflict:
                pass
        elif current_task and current_task.status == "completed":
            try:
                self.tasks.fail_verification(task.id, error)
            except TaskConflict:
                pass
        current = self.runs.get_run(run_id)
        if current and current.state not in {"failed", "passed", "blocked", "cancelled"}:
            try:
                self.runs.transition(
                    run_id,
                    expected={current.state},
                    state="failed",
                    actor="supervisor",
                    detail="execution failed closed",
                    error=error,
                )
            except RunConflict:
                pass

    def _lease_deadline(self) -> str:
        return (
            dt.datetime.now(dt.UTC)
            + dt.timedelta(seconds=self.config.lease_seconds)
        ).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def _per_call_budget(self, critic_count: int) -> float:
        max_calls = 1 + self.config.max_review_rounds + (
            critic_count * (self.config.max_review_rounds + 1)
        ) + 1
        return max(0.01, self.config.max_run_cost_usd / max_calls)
