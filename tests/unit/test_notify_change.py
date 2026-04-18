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


def test_notify_change_peer_with_hyphen(tmp_home):
    """Regression for bug #2: peer name with internal hyphens must not break peer inference.

    Old code split('-') and required exactly 2 parts; a peer like 'mesh-test' in group
    'mesh-test-peer' produced 3 parts and silently failed. The suffix-match path must
    now resolve 'mesh-test' as peer_a and 'peer' as the other peer.
    """
    proj = tmp_home / "project-hyphen"
    proj.mkdir()
    (proj / ".claude-mesh").write_text(
        "mesh_group: mesh-test-peer\n"
        "mesh_peer: mesh-test\n"
        "cross_cutting_paths:\n"
        "  - src/**\n"
    )
    rc = notify_change(
        path="src/spike.txt",
        tool="Edit",
        summary_override="hyphen test",
        hook_payload={},
        home=tmp_home,
        cwd=proj,
    )
    assert rc == 0
    inbox = tmp_home / ".claude-mesh" / "groups" / "mesh-test-peer" / "peer.ftai"
    assert inbox.exists()
    text = inbox.read_text()
    assert "@file_change" in text
    assert "from: mesh-test" in text


def test_notify_change_explicit_mesh_peers(tmp_home):
    """Bug #1 fix: explicit mesh_peers list resolves the other peer unambiguously."""
    proj = tmp_home / "project-explicit"
    proj.mkdir()
    (proj / ".claude-mesh").write_text(
        "mesh_group: spike\n"  # arbitrary label, no hyphen
        "mesh_peer: alpha\n"
        "mesh_peers:\n"
        "  - alpha\n"
        "  - beta\n"
        "cross_cutting_paths:\n"
        "  - src/**\n"
    )
    rc = notify_change(
        path="src/thing.txt",
        tool="Edit",
        summary_override="explicit peers test",
        hook_payload={},
        home=tmp_home,
        cwd=proj,
    )
    assert rc == 0
    inbox = tmp_home / ".claude-mesh" / "groups" / "spike" / "beta.ftai"
    assert inbox.exists()
    assert "from: alpha" in inbox.read_text()
