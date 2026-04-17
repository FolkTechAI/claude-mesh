# tests/unit/test_doctor.py
import sys
from pathlib import Path


def test_doctor_no_config_reports_inactive(tmp_path, monkeypatch, capsys):
    from claude_mesh.commands.doctor import run
    monkeypatch.chdir(tmp_path)
    rc = run()
    captured = capsys.readouterr()
    assert rc == 0
    assert "inactive" in captured.out.lower() or "no config" in captured.out.lower()


def test_doctor_healthy_config(tmp_home, project_with_mesh_config, monkeypatch, capsys):
    from claude_mesh.commands.doctor import run
    monkeypatch.chdir(project_with_mesh_config)
    rc = run()
    captured = capsys.readouterr()
    assert rc == 0
    assert "vault-brain" in captured.out or "vault" in captured.out
    assert "pass" in captured.out.lower() or "ok" in captured.out.lower()
