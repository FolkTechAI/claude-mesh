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
