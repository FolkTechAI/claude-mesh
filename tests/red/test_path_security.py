# tests/red/test_path_security.py
"""Red tests — reject path traversal, symlink escape, absolute paths, null bytes."""

import pytest

from claude_mesh.config import ConfigError, load_config
from claude_mesh.pathval import (
    PathValidationError,
    validate_relative_path,
    validate_under_allowed_root,
)


def test_traversal_rejected():
    with pytest.raises(PathValidationError):
        validate_relative_path("../../etc/passwd")


def test_absolute_rejected():
    with pytest.raises(PathValidationError):
        validate_relative_path("/etc/passwd")


def test_null_byte_in_path_rejected():
    with pytest.raises(PathValidationError):
        validate_relative_path("foo\x00.txt")


def test_symlink_escape_rejected(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "secret"
    outside.touch()
    link = root / "evil-link"
    link.symlink_to(outside)
    with pytest.raises(PathValidationError):
        validate_under_allowed_root(link, root)


def test_config_name_traversal_rejected(tmp_path):
    cfg = tmp_path / ".claude-mesh"
    cfg.write_text("mesh_group: ../../etc\nmesh_peer: v\n")
    with pytest.raises(ConfigError, match="invalid"):
        load_config(cfg)


def test_cross_cutting_paths_traversal_rejected(tmp_path):
    cfg = tmp_path / ".claude-mesh"
    cfg.write_text(
        "mesh_group: vb\nmesh_peer: v\n"
        "cross_cutting_paths:\n"
        "  - ../../../sensitive/**\n"
    )
    with pytest.raises(ConfigError):
        load_config(cfg)


def test_team_name_traversal_rejected(tmp_path):
    """Hook team_name is untrusted and becomes a directory under ~/.claude/teams/."""
    from claude_mesh.mode import Mode
    from claude_mesh.storage import resolve_knowledge_path

    with pytest.raises(PathValidationError):
        resolve_knowledge_path(
            Mode.TEAM, {"team_name": "../../../etc"}, config=None, home=tmp_path
        )
    assert not (tmp_path / "etc").exists()


def test_writing_to_peer_traversal_rejected(tmp_path):
    """A caller-supplied peer name must not escape ~/.claude-mesh/groups/."""
    from claude_mesh.config import MeshConfig
    from claude_mesh.mode import Mode
    from claude_mesh.storage import resolve_knowledge_path

    config = MeshConfig(mesh_group="vault-brain", mesh_peer="vault")
    with pytest.raises(PathValidationError):
        resolve_knowledge_path(
            Mode.STANDALONE,
            {},
            config,
            tmp_path,
            writing_to_peer="../../outside",
        )
    assert not (tmp_path / "outside.ftai").exists()


def test_constructed_group_name_traversal_rejected(tmp_path):
    """MeshConfig can be built without load_config; resolution must still refuse."""
    from claude_mesh.config import MeshConfig
    from claude_mesh.mode import Mode
    from claude_mesh.storage import resolve_knowledge_path

    config = MeshConfig(mesh_group="../../evil", mesh_peer="vault")
    with pytest.raises(PathValidationError):
        resolve_knowledge_path(Mode.STANDALONE, {}, config, tmp_path)
    assert not (tmp_path / "evil").exists()


def test_participant_marker_traversal_rejected(tmp_path):
    """Per-participant read markers must stay next to the knowledge file."""
    from claude_mesh.drain import read_marker_path

    log = tmp_path / "inbox" / "knowledge.ftai"
    log.parent.mkdir()
    log.touch()
    with pytest.raises(PathValidationError):
        read_marker_path(log, "../../evil")
    assert not (tmp_path / "evil.read").exists()


def test_send_team_traversal_does_not_write_outside(tmp_path):
    """Team-mode send must fail closed instead of creating a file outside teams/."""
    from claude_mesh.commands.send import send_event

    rc = send_event(
        text="exfil",
        kind="message",
        to=None,
        hook_payload={"team_name": "../../../stolen", "teammate_name": "alpha"},
        home=tmp_path,
        cwd=tmp_path,
    )
    assert rc == 1
    assert not (tmp_path / "stolen").exists()
    assert list(tmp_path.rglob("knowledge.ftai")) == []
