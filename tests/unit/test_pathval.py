# tests/unit/test_pathval.py
from pathlib import Path

import pytest

from claude_mesh.pathval import (
    PathValidationError,
    path_matches_any_glob,
    validate_relative_path,
    validate_under_allowed_root,
)


def test_path_matches_glob():
    assert path_matches_any_glob("src/api/auth.rs", ["src/api/**"])
    assert path_matches_any_glob("schema/users.json", ["schema/*.json"])


def test_path_does_not_match():
    assert not path_matches_any_glob("src/ui/App.tsx", ["src/api/**"])


def test_validate_relative_rejects_absolute():
    with pytest.raises(PathValidationError):
        validate_relative_path("/etc/passwd")


def test_validate_relative_rejects_traversal():
    with pytest.raises(PathValidationError):
        validate_relative_path("../outside")


def test_validate_under_allowed_root_accepts(tmp_path: Path):
    root = tmp_path / "allowed"
    root.mkdir()
    child = root / "file.txt"
    child.touch()
    validate_under_allowed_root(child, root)  # does not raise


def test_validate_under_allowed_root_rejects_escape(tmp_path: Path):
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.touch()
    with pytest.raises(PathValidationError):
        validate_under_allowed_root(outside, root)


def test_validate_under_allowed_root_rejects_symlink_escape(tmp_path: Path):
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "secret"
    outside.touch()
    link = root / "link"
    link.symlink_to(outside)
    with pytest.raises(PathValidationError):
        validate_under_allowed_root(link, root)
