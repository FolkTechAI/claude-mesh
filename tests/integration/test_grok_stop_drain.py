"""Grok Stop-hook drain: inject unread mail, consume only after a successful emit."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

STOP = Path(__file__).resolve().parents[2] / "hooks-grok" / "stop_drain.sh"
_BASH = shutil.which("bash")


@pytest.fixture
def mesh(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    home.mkdir()
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".claude-mesh").write_text(
        "mesh_group: wsfb\nmesh_peer: grok\n"
        "mesh_peers:\n  - grok\n  - claudepeer\n"
    )
    return home, proj


def _inbox(home: Path) -> Path:
    return home / ".claude-mesh" / "groups" / "wsfb" / "grok.ftai"


def _seed_mail(home: Path, body: str = "hello") -> Path:
    inbox = _inbox(home)
    inbox.parent.mkdir(parents=True)
    inbox.write_text(
        "@ftai v2.0\n\n"
        f"@message\nfrom: claudepeer\ntimestamp: 2026-04-17T10:00Z\nbody: {body}\n\n"
    )
    return inbox


def _run(
    home: Path,
    proj: Path,
    *,
    env_extra: dict[str, str] | None = None,
    payload: dict | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env.pop("CLAUDE_MESH_ROOT", None)
    if env_extra:
        env.update(env_extra)
    body = payload or {
        "hookEventName": "Stop",
        "reason": "end_turn",
        "stopHookActive": False,
        "cwd": str(proj),
        "workspaceRoot": str(proj),
    }
    assert _BASH is not None
    return subprocess.run(  # noqa: S603 - resolved bash path, fixed hook argv
        [_BASH, str(STOP)],
        input=json.dumps(body),
        capture_output=True,
        text=True,
        cwd=str(proj),
        env=env,
        timeout=30,
        check=False,
    )


@pytest.mark.skipif(not STOP.exists(), reason="grok adapter not present")
def test_stop_drain_injects_and_marks_read(mesh: tuple[Path, Path]) -> None:
    home, proj = mesh
    inbox = _seed_mail(home)
    result = _run(home, proj)
    assert result.returncode == 0, result.stderr
    assert "additionalContext" in result.stdout
    assert "hello" in result.stdout
    marker = inbox.with_suffix(inbox.suffix + ".read")
    assert marker.exists(), "successful injection must consume the drained mail"


@pytest.mark.skipif(not STOP.exists(), reason="grok adapter not present")
def test_stop_drain_keeps_mail_when_injection_fails(
    mesh: tuple[Path, Path], tmp_path: Path
) -> None:
    """Drain can succeed while the Stop JSON emit fails; mail must stay unread."""
    home, proj = mesh
    inbox = _seed_mail(home, body="KEEP-ME")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    wrapper = fake_bin / "python3"
    real_python = shutil.which("python3")
    assert real_python is not None
    wrapper.write_text(
        "#!/bin/sh\n"
        "# Fail only the stdin-script injection; let `python -m claude_mesh` through.\n"
        'if [ "$1" = "-" ]; then\n'
        "    echo forced-inject-fail >&2\n"
        "    exit 1\n"
        "fi\n"
        f"exec {shlex.quote(real_python)} \"$@\"\n"
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    result = _run(
        home,
        proj,
        env_extra={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )
    assert result.returncode == 0, result.stderr
    assert "additionalContext" not in result.stdout
    assert not inbox.with_suffix(inbox.suffix + ".read").exists()
    errors = (home / ".claude-mesh" / "errors.log").read_text()
    assert "stop-drain injection failed" in errors
    assert "KEEP-ME" in inbox.read_text()
