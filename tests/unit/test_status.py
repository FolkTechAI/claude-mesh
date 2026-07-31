# tests/unit/test_status.py
import os
import subprocess
import sys
from pathlib import Path


def test_status_in_non_mesh_dir_prints_inactive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = subprocess.run(
        [sys.executable, "-m", "claude_mesh", "status"],
        capture_output=True, text=True, check=False,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        },
    )
    assert r.returncode == 0
    assert "inactive" in r.stdout.lower() or "no mesh" in r.stdout.lower()
