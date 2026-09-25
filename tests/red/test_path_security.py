# tests/red/test_path_security.py
"""Red tests — reject path traversal, symlink escape, absolute paths, null bytes."""

from pathlib import Path

import pytest

from claude_mesh.config import ConfigError, MeshConfig, load_config
from claude_mesh.drain import read_marker_path
from claude_mesh.mode import Mode
from claude_mesh.pathval import (
    PathValidationError,
    validate_mesh_name,
    validate_relative_path,
    validate_under_allowed_root,
)
from claude_mesh.storage import resolve_knowledge_path
from claude_mesh.supervisor.store import supervisor_db_path
from claude_mesh.task_store import task_db_path


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


def test_pathlib_absolute_component_discards_prefix(tmp_home: Path):
    """The vulnerability is real: pathlib join is not confinement.

    An absolute team_name would rewrite the knowledge path to an arbitrary
    location if the mesh-name check were removed.
    """
    escaped = tmp_home / "escaped"
    naive = tmp_home / ".claude" / "teams" / str(escaped) / "knowledge.ftai"
    assert naive == escaped / "knowledge.ftai"


def test_team_name_absolute_path_rejected(tmp_home: Path):
    escaped = tmp_home / "escaped"
    payload = {"team_name": str(escaped), "teammate_name": "alpha"}
    with pytest.raises(PathValidationError, match="team_name"):
        resolve_knowledge_path(Mode.TEAM, payload, None, tmp_home)
    assert not (escaped / "knowledge.ftai").exists()


def test_team_name_parent_traversal_rejected(tmp_home: Path):
    payload = {"team_name": "../../.ssh", "teammate_name": "alpha"}
    with pytest.raises(PathValidationError, match="team_name"):
        resolve_knowledge_path(Mode.TEAM, payload, None, tmp_home)
    assert not (tmp_home / ".ssh" / "knowledge.ftai").exists()


def test_team_name_nested_slash_rejected(tmp_home: Path):
    payload = {"team_name": "foo/../../.ssh", "teammate_name": "alpha"}
    with pytest.raises(PathValidationError, match="team_name"):
        resolve_knowledge_path(Mode.TEAM, payload, None, tmp_home)


def test_writing_to_peer_traversal_rejected(tmp_home: Path):
    config = MeshConfig(mesh_group="vault-brain", mesh_peer="vault")
    with pytest.raises(PathValidationError, match="peer"):
        resolve_knowledge_path(
            Mode.STANDALONE,
            {},
            config,
            tmp_home,
            writing_to_peer="../evil",
        )
    assert not (tmp_home / ".claude-mesh" / "evil.ftai").exists()


def test_marker_participant_traversal_rejected(tmp_path: Path):
    log = tmp_path / "knowledge.ftai"
    log.touch()
    with pytest.raises(PathValidationError, match="participant"):
        read_marker_path(log, "../../../.ssh/stolen")
    assert not (tmp_path / ".ssh" / "stolen").exists()


def test_task_db_group_traversal_rejected(tmp_home: Path):
    with pytest.raises(PathValidationError, match="group"):
        task_db_path(tmp_home, "../../.ssh")


def test_supervisor_db_group_traversal_rejected(tmp_home: Path):
    with pytest.raises(PathValidationError, match="group"):
        supervisor_db_path(tmp_home, str(tmp_home / "escaped"))


def test_mesh_name_null_byte_rejected():
    with pytest.raises(PathValidationError):
        validate_mesh_name("team\x00name", "team_name")
