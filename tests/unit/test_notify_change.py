# tests/unit/test_notify_change.py
from pathlib import Path

from claude_mesh.commands.notify_change import notify_change


def test_notify_change_standalone(tmp_home, project_with_mesh_config):
    rc = notify_change(
        path="src/api/auth.rs",
        tool="Edit",
        summary_override="3 files changed, 40 insertions, 8 deletions",
        hook_payload={},
        home=tmp_home,
        cwd=project_with_mesh_config,
    )
    assert rc == 0
    # vault writes to brain's inbox
    inbox = tmp_home / ".claude-mesh" / "groups" / "vault-brain" / "brain.ftai"
    assert inbox.exists()
    assert "@file_change" in inbox.read_text()
    assert "src/api/auth.rs" in inbox.read_text()


def test_notify_change_skips_non_matching_path(tmp_home, project_with_mesh_config):
    rc = notify_change(
        path="docs/internal/notes.md",  # does not match src/api/**
        tool="Edit",
        summary_override="docs updated",
        hook_payload={},
        home=tmp_home,
        cwd=project_with_mesh_config,
    )
    assert rc == 0  # successful no-op
    inbox = tmp_home / ".claude-mesh" / "groups" / "vault-brain" / "brain.ftai"
    assert not inbox.exists()
