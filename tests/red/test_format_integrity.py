# tests/red/test_format_integrity.py
from pathlib import Path

import pytest

from claude_mesh.commands.drain import run as drain_run
from claude_mesh.commands.drain import run_prompt_mode
from claude_mesh.drain import drain_unread, pending_marker_path, read_marker_path
from claude_mesh.ftai import FTAIParseError, parse_file


def test_malformed_file_rejected(tmp_path):
    p = tmp_path / "bad.ftai"
    p.write_text("this is not ftai\nfor sure\n")
    with pytest.raises(FTAIParseError):
        parse_file(p)


def test_oversized_file_rejected(tmp_path):
    p = tmp_path / "huge.ftai"
    p.write_text("@ftai v2.0\n" + "x" * (11 * 1024 * 1024))
    with pytest.raises(FTAIParseError, match="ceiling"):
        parse_file(p)


def test_unclosed_block_tag_rejected(tmp_path):
    p = tmp_path / "unclosed.ftai"
    p.write_text(
        "@ftai v2.0\n\n"
        "@decision\nid: x\ntitle: y\ncontent: z\n"
    )
    with pytest.raises(FTAIParseError):
        parse_file(p)


def test_future_timestamps_tolerated_but_logged(tmp_path):
    """Events with future timestamps can still be parsed; higher layers decide policy."""
    p = tmp_path / "future.ftai"
    p.write_text(
        "@ftai v2.0\n\n"
        "@message\nfrom: x\ntimestamp: 2099-01-01T00:00:00Z\nbody: later\n\n"
    )
    tags = parse_file(p)
    assert any(t.name == "message" for t in tags)


def _standalone_inbox(tmp_path: Path, monkeypatch, body: str) -> Path:
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".claude-mesh").write_text(
        "mesh_group: g\nmesh_peer: grok\nmesh_peers:\n  - grok\n  - x\n"
    )
    group = home / ".claude-mesh" / "groups" / "g"
    group.mkdir(parents=True)
    log = group / "grok.ftai"
    log.write_text(body)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(proj)
    return log


def test_drain_command_fail_closed_on_malformed_inbox(tmp_path, monkeypatch, capsys):
    """CAT 5: a hostile/corrupt inbox must not crash drain or inject into the prompt.

    Hooks swallow a traceback with `|| true` and only skip mark-read when stdout
    is empty. Emitting nothing is the load-bearing fail-closed contract.
    """
    log = _standalone_inbox(tmp_path, monkeypatch, "this is not ftai\nfor sure\n")
    rc = drain_run("prompt")
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "claude-mesh drain:" in captured.err
    assert not pending_marker_path(read_marker_path(log)).exists()


def test_drain_command_fail_closed_on_unclosed_block(tmp_path, monkeypatch, capsys):
    log = _standalone_inbox(
        tmp_path,
        monkeypatch,
        "@ftai v2.0\n\n@decision\nid: x\ntitle: y\ncontent: z\n",
    )
    rc = drain_run("prompt")
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "claude-mesh drain:" in captured.err
    with pytest.raises(FTAIParseError):
        drain_unread(log, read_marker_path(log))


def test_prompt_mode_fail_closed_on_malformed_file(tmp_path, capsys):
    log = tmp_path / "knowledge.ftai"
    log.write_text("not ftai\n")
    rc = run_prompt_mode(log)
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "claude-mesh drain:" in captured.err
