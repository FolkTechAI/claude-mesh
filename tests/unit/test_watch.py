from __future__ import annotations

from pathlib import Path

from claude_mesh.commands.watch import run


def test_watch_times_out_without_consuming(tmp_path: Path, monkeypatch, capsys):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".claude-mesh").write_text(
        "mesh_group: g\n"
        "mesh_peer: alpha\n"
        "mesh_peers:\n"
        "  - alpha\n"
        "  - beta\n"
    )
    monkeypatch.chdir(project)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert run(timeout=0.06, interval=0.05, as_json=True) == 0
    assert capsys.readouterr().out == ""


def test_watch_reports_existing_unread(tmp_path: Path, monkeypatch, capsys):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".claude-mesh").write_text(
        "mesh_group: g\n"
        "mesh_peer: alpha\n"
        "mesh_peers:\n"
        "  - alpha\n"
        "  - beta\n"
    )
    home = tmp_path / "home"
    inbox = home / ".claude-mesh" / "groups" / "g" / "alpha.ftai"
    inbox.parent.mkdir(parents=True)
    inbox.write_text(
        "@ftai v2.0\n\n@message\nfrom: beta\ntimestamp: 2026-01-01T00:00:00Z\nbody: hi\n\n"
    )
    monkeypatch.chdir(project)
    monkeypatch.setenv("HOME", str(home))
    assert run(timeout=0.1, interval=0.05, as_json=True) == 0
    assert '"unread": 1' in capsys.readouterr().out
