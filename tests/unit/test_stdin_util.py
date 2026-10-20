"""Bounds on hook/CLI stdin: never hang, never buffer unbounded input."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from claude_mesh.stdin_util import MAX_PAYLOAD_BYTES

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"


def test_stdin_util_module_roundtrips_json():
    payload = '{"prompt":"hello from mesh"}'
    r = subprocess.run(  # noqa: S603 - sys.executable, fixed argv
        [sys.executable, "-m", "claude_mesh.stdin_util"],
        input=payload,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env={**os.environ, "PYTHONPATH": str(SRC)},
        cwd=str(REPO),
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout == payload


def test_read_stdin_bounded_truncates_to_max_payload_bytes():
    """Last os.read() can overshoot the cap; the returned payload must not."""
    blob = b"a" * (MAX_PAYLOAD_BYTES + 80_000)
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(SRC)!r})\n"
        "from claude_mesh.stdin_util import MAX_PAYLOAD_BYTES, read_stdin_bounded\n"
        "out = read_stdin_bounded(2.0)\n"
        "sys.stdout.write(str(len(out.encode('utf-8'))) + '\\n')\n"
        "sys.stdout.write('ok' if out == ('a' * MAX_PAYLOAD_BYTES) else 'bad')\n"
    )
    read_fd, write_fd = os.pipe()
    try:
        proc = subprocess.Popen(  # noqa: S603 - sys.executable, fixed argv
            [sys.executable, "-c", script],
            stdin=read_fd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
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
        out, err = proc.communicate(timeout=15)
        worker.join(timeout=5)
        assert proc.returncode == 0, err
        lines = out.splitlines()
        assert lines[0] == str(MAX_PAYLOAD_BYTES)
        assert lines[1] == "ok"
    finally:
        if read_fd != -1:
            os.close(read_fd)
