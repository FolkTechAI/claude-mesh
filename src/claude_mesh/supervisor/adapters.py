"""Bounded, non-shell process adapters for local agent CLIs."""

from __future__ import annotations

import json
import os
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from claude_mesh.supervisor.config import WorkerConfig
from claude_mesh.supervisor.prompts import schema_for


class AdapterError(RuntimeError):
    """Raised when an agent process fails or violates its output contract."""


@dataclass(frozen=True)
class AgentResult:
    actor: str
    vendor: str
    role: str
    payload: dict[str, object]
    raw: str
    duration_seconds: float
    cost_usd: float | None = None


def _minimal_environment() -> dict[str, str]:
    allowed = {
        "HOME",
        "PATH",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "TERM",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


def _read_bounded_process(
    argv: list[str],
    *,
    cwd: Path,
    stdin: bytes | None,
    timeout: int,
    max_bytes: int,
    env_overrides: dict[str, str] | None = None,
) -> tuple[int, bytes, bytes, float]:
    started = time.monotonic()
    environment = _minimal_environment()
    environment.update(env_overrides or {})
    process = subprocess.Popen(  # noqa: S603 - executable comes from validated config
        argv,
        cwd=cwd,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    assert process.stdout is not None and process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    input_view = memoryview(stdin) if stdin is not None else None
    input_offset = 0
    if input_view is not None and process.stdin is not None:
        os.set_blocking(process.stdin.fileno(), False)
        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
    chunks: dict[str, list[bytes]] = {"stdout": [], "stderr": []}
    total = 0
    deadline = started + timeout
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AdapterError(f"agent timed out after {timeout}s")
            for key, _ in selector.select(timeout=min(0.25, remaining)):
                stream = key.fileobj
                if key.data == "stdin":
                    assert input_view is not None
                    try:
                        written = os.write(stream.fileno(), input_view[input_offset:])
                    except BrokenPipeError:
                        written = len(input_view) - input_offset
                    input_offset += written
                    if input_offset >= len(input_view):
                        selector.unregister(stream)
                        stream.close()
                    continue
                data = os.read(stream.fileno(), 65_536)
                if not data:
                    selector.unregister(stream)
                    continue
                total += len(data)
                if total > max_bytes:
                    raise AdapterError(
                        f"agent output exceeded {max_bytes} byte safety limit"
                    )
                chunks[str(key.data)].append(data)
        returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
    except Exception:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
        raise
    return (
        returncode,
        b"".join(chunks["stdout"]),
        b"".join(chunks["stderr"]),
        time.monotonic() - started,
    )


def _extract_payload(raw: str, role: str) -> dict[str, object]:
    candidates: list[object] = []
    try:
        candidates.append(json.loads(raw))
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                candidates.append(json.loads(raw[start : end + 1]))
            except json.JSONDecodeError:
                pass
    while candidates:
        value = candidates.pop(0)
        if isinstance(value, dict):
            for key in (
                "structured_output",
                "structuredOutput",
                "output",
                "result",
                "response",
                "text",
            ):
                nested = value.get(key)
                if isinstance(nested, dict):
                    candidates.append(nested)
                elif isinstance(nested, str):
                    try:
                        candidates.append(json.loads(nested))
                    except json.JSONDecodeError:
                        pass
            if _valid_shape(value, role):
                return value
    raise AdapterError(f"{role} returned invalid structured output")


def _valid_shape(payload: dict[str, object], role: str) -> bool:
    required = {
        "worker": {"status", "summary", "evidence", "changed_files", "tests", "remaining_risks"},
        "critic": {"verdict", "attack_summary", "findings", "confidence"},
        "verifier": {"verdict", "checks", "evidence", "residual_risk"},
    }[role]
    if not required.issubset(payload):
        return False
    if role == "worker":
        status = payload.get("status")
        return (
            status in {"completed", "blocked"}
            and isinstance(payload.get("summary"), str)
            and isinstance(payload.get("evidence"), str)
            and (status == "blocked" or bool(str(payload.get("evidence", "")).strip()))
            and isinstance(payload.get("changed_files"), list)
            and isinstance(payload.get("tests"), list)
            and isinstance(payload.get("remaining_risks"), list)
        )
    if role == "critic":
        verdict = payload.get("verdict")
        findings = payload.get("findings")
        if verdict not in {"pass", "challenge"} or not isinstance(findings, list):
            return False
        if verdict == "pass":
            return not findings
        return bool(findings) and all(
            isinstance(finding, dict)
            and {"severity", "title", "evidence", "reproduction"}.issubset(finding)
            and finding.get("severity") in {"critical", "high", "medium", "low"}
            and all(
                isinstance(finding.get(key), str) and bool(finding.get(key).strip())
                for key in ("title", "evidence", "reproduction")
            )
            for finding in findings
        )
    return (
        payload.get("verdict") in {"pass", "fail"}
        and isinstance(payload.get("checks"), list)
        and bool(payload.get("checks"))
        and isinstance(payload.get("evidence"), str)
        and bool(payload.get("evidence", "").strip())
    )


def _extract_cost(raw: str) -> float | None:
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(envelope, dict):
        return None
    value = envelope.get("total_cost_usd")
    if value is None:
        value = envelope.get("totalCostUsd")
    if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


def run_agent(
    worker: WorkerConfig,
    *,
    role: str,
    prompt: str,
    workspace: Path,
    max_budget_usd: float | None = None,
) -> AgentResult:
    if role not in {"worker", "critic", "verifier"}:
        raise AdapterError(f"unsupported agent role: {role!r}")
    if len(prompt.encode("utf-8")) > 512 * 1024:
        raise AdapterError("agent prompt exceeded 512 KiB safety limit")
    schema = json.dumps(schema_for(role), separators=(",", ":"))
    stdin: bytes | None = None
    output_file: Path | None = None
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    env_overrides: dict[str, str] = {}
    if worker.vendor == "claude":
        permission = "acceptEdits" if role == "worker" else "plan"
        tools = "Read,Edit,Write,Glob,Grep" if role == "worker" else "Read,Glob,Grep"
        argv = [
            worker.executable,
            "-p",
            "--safe-mode",
            "--no-chrome",
            "--output-format",
            "json",
            "--json-schema",
            schema,
            "--permission-mode",
            permission,
            "--tools",
            tools,
            "--no-session-persistence",
        ]
        if worker.model:
            argv.extend(["--model", worker.model])
        if max_budget_usd is not None:
            argv.extend(["--max-budget-usd", f"{max_budget_usd:.2f}"])
        argv.append(prompt)
    elif worker.vendor == "codex":
        temp_dir = tempfile.TemporaryDirectory(prefix="mesh-supervisor-")
        schema_file = Path(temp_dir.name) / "schema.json"
        output_file = Path(temp_dir.name) / "result.json"
        schema_file.write_text(schema, encoding="utf-8")
        sandbox = "workspace-write" if role == "worker" else "read-only"
        argv = [
            worker.executable,
            "--sandbox",
            sandbox,
            "--ask-for-approval",
            "never",
            "--cd",
            str(workspace),
            "exec",
            "--ephemeral",
            "--output-schema",
            str(schema_file),
            "--output-last-message",
            str(output_file),
            "-",
        ]
        if worker.model:
            argv[1:1] = ["--model", worker.model]
        stdin = prompt.encode("utf-8")
    elif worker.vendor == "grok":
        temp_dir = tempfile.TemporaryDirectory(prefix="mesh-supervisor-")
        temp_root = Path(temp_dir.name)
        prompt_file = temp_root / "prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")
        grok_home = temp_root / "grok-home"
        grok_home.mkdir(mode=0o700)
        source_home = Path(
            os.environ.get("GROK_HOME", str(Path.home() / ".grok"))
        ).expanduser()
        auth_source = source_home / "auth.json"
        if auth_source.is_file():
            auth_target = grok_home / "auth.json"
            shutil.copyfile(auth_source, auth_target)
            os.chmod(auth_target, 0o600)
        (grok_home / "config.toml").write_text(
            "[compat.cursor]\n"
            "skills = false\nrules = false\nagents = false\nmcps = false\n"
            "hooks = false\nsessions = false\n"
            "[compat.claude]\n"
            "skills = false\nrules = false\nagents = false\nmcps = false\n"
            "hooks = false\nsessions = false\n"
            "[compat.codex]\nsessions = false\n"
            "[plugins]\npaths = []\n"
            "[skills]\npaths = []\n",
            encoding="utf-8",
        )
        env_overrides = {
            "GROK_HOME": str(grok_home),
            "GROK_TELEMETRY_ENABLED": "false",
            "GROK_TELEMETRY_MIXPANEL_ENABLED": "false",
            "GROK_FEEDBACK_ENABLED": "false",
        }
        permission = "acceptEdits" if role == "worker" else "plan"
        sandbox = "workspace" if role == "worker" else "read-only"
        tools = (
            "read_file,search_replace,grep_search,list_dir,bash"
            if role == "worker"
            else "read_file,grep_search,list_dir,bash"
        )
        argv = [
            worker.executable,
            "--cwd",
            str(workspace),
            "--sandbox",
            sandbox,
            "--no-memory",
            "--no-subagents",
            "--disable-web-search",
            "--prompt-file",
            str(prompt_file),
            "--output-format",
            "json",
            "--json-schema",
            schema,
            "--permission-mode",
            permission,
            "--tools",
            tools,
            "--max-turns",
            "30",
        ]
        if worker.model:
            argv.extend(["--model", worker.model])
    elif worker.vendor == "hermes":
        if role == "worker":
            raise AdapterError("Hermes worker mode is disabled: oneshot bypasses approvals")
        argv = [worker.executable, "--safe-mode", "--toolsets", "", "--oneshot", prompt]
        if worker.model:
            argv.extend(["--model", worker.model])
    else:
        argv = [worker.executable, *worker.argv]
        argv = [
            part.replace("{role}", role).replace("{workspace}", str(workspace))
            for part in argv
        ]
        stdin = prompt.encode("utf-8")

    try:
        returncode, stdout, stderr, duration = _read_bounded_process(
            argv,
            cwd=workspace,
            stdin=stdin,
            timeout=worker.timeout_seconds,
            max_bytes=worker.max_output_bytes,
            env_overrides=env_overrides,
        )
        if returncode != 0:
            error = stderr.decode("utf-8", errors="replace")[-4000:]
            raise AdapterError(
                f"{worker.name} exited {returncode}: {error or 'no stderr'}"
            )
        raw = stdout.decode("utf-8", errors="replace")
        if output_file is not None and output_file.exists():
            raw = output_file.read_text(encoding="utf-8", errors="replace")
        payload = _extract_payload(raw, role)
        return AgentResult(
            actor=worker.name,
            vendor=worker.vendor,
            role=role,
            payload=payload,
            raw=raw,
            duration_seconds=duration,
            cost_usd=_extract_cost(raw),
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()
