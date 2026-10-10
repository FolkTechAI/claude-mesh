# tests/red/test_sensitive_data.py
from pathlib import Path

from claude_mesh.commands import subagent_turn
from claude_mesh.commands.subagent_turn import run as subagent_turn_run
from claude_mesh.commands.task_event import run as task_event
from claude_mesh.sanitize import SensitiveDataFilter


def test_aws_key_redacted():
    f = SensitiveDataFilter()
    text = "AWS_SECRET_ACCESS_KEY=aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567"
    out = f.redact(text)
    assert "aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567" not in out
    assert "REDACTED" in out


def test_bearer_token_redacted():
    f = SensitiveDataFilter()
    out = f.redact("Authorization: Bearer eyJhbGc.eyJzdWI.SIGNATURE")
    assert "SIGNATURE" not in out or "REDACTED" in out


def test_openai_key_redacted():
    f = SensitiveDataFilter()
    out = f.redact("OPENAI_KEY=sk-proj-abcdefghijklmnop")
    assert "sk-proj-abcdefghijklmnop" not in out


def test_high_entropy_secret_redacted():
    """Long alphanumeric runs look like secrets; flag them."""
    f = SensitiveDataFilter()
    out = f.redact("token = abcdef1234567890abcdef1234567890abcdef")
    assert "abcdef1234567890abcdef1234567890abcdef" not in out


def test_task_event_redacts_secrets_before_write(tmp_path, monkeypatch):
    """CAT 3: hook-driven task-event must not persist credentials to an inbox."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".claude-mesh").write_text(
        "mesh_group: g\nmesh_peer: grok\nmesh_peers:\n  - grok\n  - alpha\n"
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(proj)

    sample_key = "sk-proj-abcdefghijklmnop"
    assert (
        task_event(
            "T-SEC",
            f"Rotate {sample_key}",
            "pending",
            description=f"api_key: {sample_key}",
        )
        == 0
    )
    text = (home / ".claude-mesh" / "groups" / "g" / "alpha.ftai").read_text()
    assert sample_key not in text
    assert "REDACTED" in text


def test_subagent_turn_redacts_secrets_before_write(tmp_path, monkeypatch):
    """CAT 3: SubagentStop summaries are durable inbox content, not just local logs."""
    sample_key = "sk-proj-abcdefghijklmnop"
    msg = (
        "Completed the credential rotation for the staging gateway. "
        f"Replacement key is {sample_key} and the smoke checks passed."
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        subagent_turn,
        "read_hook_payload",
        lambda: {
            "team_name": "spike",
            "teammate_name": "alpha",
            "last_assistant_message": msg,
        },
    )
    assert subagent_turn_run() == 0
    text = (tmp_path / ".claude" / "teams" / "spike" / "knowledge.ftai").read_text()
    assert sample_key not in text
    assert "REDACTED" in text
