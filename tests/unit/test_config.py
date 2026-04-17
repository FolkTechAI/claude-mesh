# tests/unit/test_config.py
from pathlib import Path

import pytest

from claude_mesh.config import MeshConfig, find_config, load_config, ConfigError


def test_load_valid_config(tmp_path: Path):
    cfg = tmp_path / ".claude-mesh"
    cfg.write_text(
        "mesh_group: vault-brain\n"
        "mesh_peer: vault\n"
        "cross_cutting_paths:\n"
        "  - src/api/**\n"
    )
    config = load_config(cfg)
    assert config.mesh_group == "vault-brain"
    assert config.mesh_peer == "vault"
    assert config.cross_cutting_paths == ["src/api/**"]


def test_rejects_missing_required_fields(tmp_path: Path):
    cfg = tmp_path / ".claude-mesh"
    cfg.write_text("mesh_group: vault-brain\n")  # no mesh_peer
    with pytest.raises(ConfigError, match="mesh_peer"):
        load_config(cfg)


def test_rejects_invalid_characters_in_name(tmp_path: Path):
    cfg = tmp_path / ".claude-mesh"
    cfg.write_text("mesh_group: ../../evil\nmesh_peer: vault\n")
    with pytest.raises(ConfigError, match="invalid characters"):
        load_config(cfg)


def test_find_config_walks_up(tmp_path: Path):
    (tmp_path / "deep" / "nested").mkdir(parents=True)
    cfg_file = tmp_path / ".claude-mesh"
    cfg_file.write_text("mesh_group: g\nmesh_peer: p\n")
    found = find_config(tmp_path / "deep" / "nested", stop_at=tmp_path.parent)
    assert found == cfg_file


def test_find_config_none_when_not_found(tmp_path: Path):
    found = find_config(tmp_path, stop_at=tmp_path.parent)
    assert found is None
