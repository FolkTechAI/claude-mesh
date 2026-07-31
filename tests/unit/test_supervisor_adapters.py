from __future__ import annotations

import sys
from pathlib import Path

import pytest

from claude_mesh.supervisor.adapters import AdapterError, run_agent
from claude_mesh.supervisor.config import WorkerConfig


def _agent(script: Path, *, timeout: int = 5, max_bytes: int = 65_536) -> WorkerConfig:
    return WorkerConfig(
        name="fake",
        vendor="command",
        roles=("worker", "critic", "verifier"),
        capabilities=("coding",),
        executable=sys.executable,
        timeout_seconds=timeout,
        max_output_bytes=max_bytes,
        argv=(str(script), "{role}"),
    )


def test_command_adapter_accepts_structured_worker_output(tmp_path: Path):
    script = tmp_path / "agent.py"
    script.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'status':'completed','summary':'done','evidence':'test',"
        "'changed_files':['x.py'],'tests':['pytest'],'remaining_risks':[]}))\n",
        encoding="utf-8",
    )

    result = run_agent(
        _agent(script), role="worker", prompt="do it", workspace=tmp_path
    )

    assert result.payload["status"] == "completed"
    assert result.actor == "fake"


def test_command_adapter_accepts_camel_case_structured_wrapper(tmp_path: Path):
    script = tmp_path / "wrapped.py"
    script.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'total_cost_usd':0.25,'structuredOutput':{'verdict':'pass',"
        "'attack_summary':'checked','findings':[],'confidence':'high'}}))\n",
        encoding="utf-8",
    )

    result = run_agent(
        _agent(script), role="critic", prompt="review", workspace=tmp_path
    )

    assert result.payload["verdict"] == "pass"
    assert result.cost_usd == 0.25


def test_command_adapter_rejects_invalid_contract(tmp_path: Path):
    script = tmp_path / "bad.py"
    script.write_text("print('{}')\n", encoding="utf-8")

    with pytest.raises(AdapterError, match="invalid structured output"):
        run_agent(_agent(script), role="critic", prompt="review", workspace=tmp_path)


def test_critic_challenge_requires_reproducible_finding(tmp_path: Path):
    script = tmp_path / "empty_challenge.py"
    script.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'verdict':'challenge','attack_summary':'vague',"
        "'findings':[],'confidence':'low'}))\n",
        encoding="utf-8",
    )

    with pytest.raises(AdapterError, match="invalid structured output"):
        run_agent(_agent(script), role="critic", prompt="review", workspace=tmp_path)


def test_command_adapter_enforces_timeout_and_output_limit(tmp_path: Path):
    sleepy = tmp_path / "sleepy.py"
    sleepy.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    with pytest.raises(AdapterError, match="timed out"):
        run_agent(
            _agent(sleepy, timeout=1),
            role="worker",
            prompt="wait",
            workspace=tmp_path,
        )

    noisy = tmp_path / "noisy.py"
    noisy.write_text("print('x' * 4096)\n", encoding="utf-8")
    with pytest.raises(AdapterError, match="safety limit"):
        run_agent(
            _agent(noisy, max_bytes=1024),
            role="worker",
            prompt="noise",
            workspace=tmp_path,
        )


def test_hermes_cannot_be_an_implementation_worker(tmp_path: Path):
    worker = WorkerConfig(
        name="hermes",
        vendor="hermes",
        roles=("worker",),
        capabilities=("coding",),
        executable=sys.executable,
    )
    with pytest.raises(AdapterError, match="worker mode is disabled"):
        run_agent(worker, role="worker", prompt="edit", workspace=tmp_path)
