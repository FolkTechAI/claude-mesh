# tests/red/test_path_security.py
"""Red tests — reject path traversal, symlink escape, absolute paths, null bytes."""

import pytest

from claude_mesh.config import ConfigError, MeshConfig, load_config
from claude_mesh.drain import read_marker_path
from claude_mesh.mode import Mode
from claude_mesh.pathval import (
    PathValidationError,
    validate_path_component,
    validate_relative_path,
    validate_under_allowed_root,
)
from claude_mesh.storage import resolve_knowledge_path


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


def test_team_name_traversal_cannot_escape_teams_root(tmp_path):
    """Hostile team_name must not resolve outside ~/.claude/teams/.

    The attack is real: pathlib interpolates `../../.ssh` as parent segments.
    Resolution must fail closed before any inbox I/O.
    """
    home = tmp_path
    payload = {"team_name": "../../.ssh"}
    escaped = (home / ".claude" / "teams" / "../../.ssh" / "knowledge.ftai").resolve()
    allowed = (home / ".claude" / "teams").resolve()
    assert not str(escaped).startswith(str(allowed))

    with pytest.raises(PathValidationError):
        resolve_knowledge_path(Mode.TEAM, payload, None, home)
    assert not escaped.exists()


def test_team_name_absolute_and_separator_rejected(tmp_path):
    for team_name in ("/etc/passwd", "foo/bar", "foo\\bar", "..", "."):
        with pytest.raises(PathValidationError):
            resolve_knowledge_path(
                Mode.TEAM, {"team_name": team_name}, None, tmp_path
            )


def test_writing_to_peer_traversal_cannot_escape_groups_root(tmp_path):
    """writing_to_peer is a second interpolation site — defend it here too."""
    home = tmp_path
    config = MeshConfig(mesh_group="vault-brain", mesh_peer="vault")
    escaped = (
        home / ".claude-mesh" / "groups" / "vault-brain" / "../../.ssh.ftai"
    ).resolve()
    allowed = (home / ".claude-mesh" / "groups").resolve()
    assert not str(escaped).startswith(str(allowed))

    with pytest.raises(PathValidationError):
        resolve_knowledge_path(
            Mode.STANDALONE, {}, config, home, writing_to_peer="../../.ssh"
        )
    assert not escaped.exists()


def test_participant_marker_cannot_escape_inbox_dir(tmp_path):
    """Team-mode read markers include teammate_name in the filename suffix.

    Built without Path.with_suffix: 3.12 rejects separators there, 3.11
    interpolates them. The attack is the interpolated path either way.
    """
    log = tmp_path / "teams" / "spike" / "knowledge.ftai"
    log.parent.mkdir(parents=True)
    log.write_text("@ftai v2.0\n", encoding="utf-8")
    hostile = "../../../../.ssh/authorized_keys"
    escaped = (log.parent / f"{log.name}.{hostile}.read").resolve()
    assert not str(escaped).startswith(str(log.parent.resolve()))

    with pytest.raises(PathValidationError):
        read_marker_path(log, hostile)
    assert not escaped.exists()


def test_path_component_rejects_control_and_null():
    with pytest.raises(PathValidationError):
        validate_path_component("foo\x00bar")
    with pytest.raises(PathValidationError):
        validate_path_component("foo\nbar")
    validate_path_component("mesh-team")
    validate_path_component("My_Team")
