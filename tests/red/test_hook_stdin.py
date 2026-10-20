"""Red tests — hook wrappers must not hang or buffer unbounded stdin.

The Python CLI already bounds stdin (`read_stdin_bounded`). The bash
wrappers used to undo that with `PAYLOAD="$(cat)"`, which blocks forever
on an inherited pipe that never reaches EOF and will buffer an unbounded
write. These tests pin the hook-layer bound.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from claude_mesh.stdin_util import MAX_PAYLOAD_BYTES

_BASH = shutil.which("bash")

REPO = Path(__file__).resolve().parents[2]
CLAUDE_COMMON = REPO / "hooks" / "_common.sh"
GROK_COMMON = REPO / "hooks-grok" / "_common.sh"
UPS_HOOK = REPO / "hooks" / "user_prompt_submit.sh"


def _env(home: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = str(home)
    return env


def _run_open_pipe(
    argv: list[str],
    env: dict[str, str],
    timeout: float = 15,
) -> subprocess.CompletedProcess[str]:
    """Run argv with stdin held open (no EOF) and no bytes written."""
    read_fd, write_fd = os.pipe()
    try:
        proc = subprocess.Popen(  # noqa: S603 - fixed test argv
            argv,
            stdin=read_fd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        os.close(read_fd)
        read_fd = -1
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            raise AssertionError(
                f"command hung on a never-EOF stdin pipe: {argv!r}\n{err}"
            ) from None
        return subprocess.CompletedProcess(argv, proc.returncode, out, err)
    finally:
        if read_fd != -1:
            os.close(read_fd)
        os.close(write_fd)


@pytest.mark.parametrize("common", [CLAUDE_COMMON, GROK_COMMON], ids=["claude", "grok"])
def test_hook_helper_returns_on_never_eof_pipe(common: Path, tmp_path: Path):
    """cat on a held-open pipe never returns; read_hook_stdin must."""
    t0 = time.monotonic()
    assert _BASH is not None
    result = _run_open_pipe(
        [_BASH, "-c", 'source "$1"; read_hook_stdin', "bash", str(common)],
        env=_env(tmp_path),
    )
    elapsed = time.monotonic() - t0
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert elapsed < 5.0


def test_hook_helper_caps_oversized_envelope(tmp_path: Path):
    blob = b"a" * (MAX_PAYLOAD_BYTES + 80_000)
    read_fd, write_fd = os.pipe()
    try:
        assert _BASH is not None
        proc = subprocess.Popen(  # noqa: S603 - resolved bash path, fixed argv
            [_BASH, "-c", 'source "$1"; read_hook_stdin', "bash", str(CLAUDE_COMMON)],
            stdin=read_fd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_env(tmp_path),
        )
        os.close(read_fd)
        read_fd = -1

        def _pump() -> None:
            view = memoryview(blob)
            offset = 0
            try:
                while offset < len(view):
                    offset += os.write(write_fd, view[offset : offset + 65536])
            except (BrokenPipeError, OSError):
                pass
            finally:
                try:
                    os.close(write_fd)
                except OSError:
                    pass

        worker = threading.Thread(target=_pump, daemon=True)
        worker.start()
        try:
            out, err = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
        worker.join(timeout=5)
        assert proc.returncode == 0, err
        assert out is not None
        assert len(out) == MAX_PAYLOAD_BYTES
        assert set(out) <= {ord("a")}
    finally:
        if read_fd != -1:
            os.close(read_fd)


def test_user_prompt_submit_returns_on_never_eof_pipe(tmp_path: Path):
    """The UserPromptSubmit wrapper is on the hot path of every Claude turn."""
    t0 = time.monotonic()
    assert _BASH is not None
    result = _run_open_pipe(
        [_BASH, str(UPS_HOOK)],
        env=_env(tmp_path),
    )
    elapsed = time.monotonic() - t0
    assert result.returncode == 0, result.stderr
    assert elapsed < 5.0
    assert "mesh_context" not in result.stdout
