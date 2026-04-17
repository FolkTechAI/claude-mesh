# tests/unit/test_cli.py
import subprocess
import sys


def test_cli_help_runs():
    result = subprocess.run(
        [sys.executable, "-m", "claude_mesh", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "claude-mesh" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_cli_unknown_subcommand_fails():
    result = subprocess.run(
        [sys.executable, "-m", "claude_mesh", "nonexistent"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
