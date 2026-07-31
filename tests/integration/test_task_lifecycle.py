from __future__ import annotations

from pathlib import Path

from claude_mesh.commands.control import run as control_run
from claude_mesh.commands.task import run


def _project(root: Path, peer: str) -> Path:
    project = root / peer
    project.mkdir(parents=True)
    (project / ".claude-mesh").write_text(
        "mesh_group: operators\n"
        f"mesh_peer: {peer}\n"
        "mesh_peers:\n"
        "  - alpha\n"
        "  - beta\n"
    )
    return project


def test_full_task_lifecycle_with_independent_verification(
    tmp_path: Path, monkeypatch
):
    home = tmp_path / "home"
    alpha = _project(tmp_path, "alpha")
    beta = _project(tmp_path, "beta")
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.chdir(alpha)
    assert run(
        "create",
        task_id="T-99",
        subject="Build adapter",
        description="Implement and test it",
        to="beta",
        risk="high",
        idempotency_key="release-adapter",
    ) == 0

    monkeypatch.chdir(beta)
    assert run("claim", task_id="T-99", lease_seconds=300) == 0
    assert run("start", task_id="T-99", lease_seconds=300) == 0
    assert run("complete", task_id="T-99", evidence="123 tests passed") == 0

    monkeypatch.chdir(alpha)
    assert run(
        "verify",
        task_id="T-99",
        verdict="pass",
        evidence="AKE replay passed",
    ) == 0
    assert control_run(
        "experience",
        record_id="E-99",
        task_id="T-99",
        outcome="Adapter validated",
        lesson="Require independent replay",
        evidence="task verification receipt",
        verified_by="alpha",
        tags=["release"],
        to="beta",
    ) == 0

    beta_inbox = home / ".claude-mesh" / "groups" / "operators" / "beta.ftai"
    alpha_inbox = home / ".claude-mesh" / "groups" / "operators" / "alpha.ftai"
    assert "status: verified" in beta_inbox.read_text()
    assert "@verification" in beta_inbox.read_text()
    assert "@experience" in beta_inbox.read_text()
    assert "status: completed" in alpha_inbox.read_text()
