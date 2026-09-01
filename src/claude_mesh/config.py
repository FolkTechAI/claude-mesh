# src/claude_mesh/config.py
"""Load and validate .claude-mesh YAML config files.

We use a minimal hand-rolled YAML-subset parser (not the full PyYAML dep).
The schema is intentionally tiny: mesh_group, mesh_peer, optional cross_cutting_paths list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict


class ConfigError(ValueError):
    """Raised when .claude-mesh config is invalid."""


NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MAX_CONFIG_BYTES = 16 * 1024  # 16 KB ceiling


class RemotePeerConfig(TypedDict):
    """Configuration for a remote peer on another machine."""
    host: str
    user: str
    inbox_path: str


@dataclass(frozen=True)
class MeshConfig:
    mesh_group: str
    mesh_peer: str
    cross_cutting_paths: list[str] = field(default_factory=list)
    mesh_peers: list[str] = field(default_factory=list)
    remote_peers: dict[str, RemotePeerConfig] = field(default_factory=dict)
    source_path: Path | None = None

    def other_peer(self) -> str | None:
        """Return the opposite peer name for two-peer standalone mode, or None if ambiguous.

        Resolution order:
          1. If mesh_peers is an explicit 2-element list, pick the one that isn't mesh_peer.
          2. Otherwise try group = '{mesh_peer}-{other}' (prefix match).
          3. Otherwise try group = '{other}-{mesh_peer}' (suffix match).
          4. Otherwise give up (ambiguous — caller should require explicit mesh_peers).
        """
        if self.mesh_peers:
            if len(self.mesh_peers) == 2 and self.mesh_peer in self.mesh_peers:
                a, b = self.mesh_peers
                return b if a == self.mesh_peer else a
            return None

        prefix = self.mesh_peer + "-"
        suffix = "-" + self.mesh_peer
        if self.mesh_group.startswith(prefix):
            return self.mesh_group[len(prefix):]
        if self.mesh_group.endswith(suffix):
            return self.mesh_group[: -len(suffix)]
        return None

    def other_peers(self) -> list[str]:
        """Every participant in the group except this one (N-way safe).

        Unlike `other_peer()`, this generalizes past two peers: with an
        explicit `mesh_peers` roster it returns all the others, preserving
        roster order. Falls back to the two-peer inference when no roster is
        declared, and returns [] when the group cannot be resolved at all.
        """
        if self.mesh_peers:
            return [p for p in self.mesh_peers if p != self.mesh_peer]
        inferred = self.other_peer()
        return [inferred] if inferred else []


def _parse_minimal_yaml(text: str) -> dict[str, object]:
    """Parse a restricted YAML subset: string keys, string values, lists, and simple nested maps.

    Supports:
      key: value
      key:
        - item
        - item
      key:
        nested_key: value
        nested_key2: value
      key:
        submap:
          nested: value
    Lines beginning with '#' are comments. Blank lines ignored.
    """
    out: dict[str, object] = {}
    current_list_key: str | None = None
    current_map_key: str | None = None
    current_submap_key: str | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        # List item (  - value)
        if line.startswith(("  - ", "\t- ")):
            if current_list_key is None:
                raise ConfigError("List item without parent key")
            value = line.lstrip().removeprefix("- ").strip()
            # Ensure it's actually a list
            if not isinstance(out.get(current_list_key), list):
                out[current_list_key] = []
            assert isinstance(out[current_list_key], list)
            out[current_list_key].append(value)  # type: ignore[union-attr]
            continue

        # Deeply nested map item (        key: value)
        if line.startswith(("        ", "\t\t\t")):
            if current_map_key is None or current_submap_key is None:
                raise ConfigError("Deeply nested item without parent keys")
            if ":" not in line:
                raise ConfigError(f"Unexpected nested line (no colon): {line!r}")
            nested_key, _, nested_value = line.strip().partition(":")
            nested_key = nested_key.strip()
            nested_value = nested_value.strip()
            
            # Ensure parent is a dict
            if not isinstance(out.get(current_map_key), dict):
                out[current_map_key] = {}
            parent = out[current_map_key]
            assert isinstance(parent, dict)
            
            # Ensure submap exists
            if current_submap_key not in parent:
                parent[current_submap_key] = {}
            assert isinstance(parent[current_submap_key], dict)
            parent[current_submap_key][nested_key] = nested_value  # type: ignore[index]
            continue

        # Second-level map item (    key: or     key: value)
        if line.startswith(("    ", "\t\t")):
            if current_map_key is None:
                raise ConfigError("Nested item without parent key")
            if ":" not in line:
                raise ConfigError(f"Unexpected nested line (no colon): {line!r}")
            nested_key, _, nested_value = line.strip().partition(":")
            nested_key = nested_key.strip()
            nested_value = nested_value.strip()
            
            # Ensure parent is a dict (convert from list if needed)
            if not isinstance(out.get(current_map_key), dict):
                out[current_map_key] = {}
            assert isinstance(out[current_map_key], dict)
            
            if not nested_value:
                # This is a submap key
                current_submap_key = nested_key
                out[current_map_key][nested_key] = {}  # type: ignore[index]
            else:
                out[current_map_key][nested_key] = nested_value  # type: ignore[index]
            continue

        # Top-level key
        current_list_key = None
        current_map_key = None
        current_submap_key = None

        if ":" not in line:
            raise ConfigError(f"Unexpected line (no colon): {line!r}")

        key, _, rest = line.partition(":")
        key = key.strip()
        value = rest.strip()

        if not value:
            # Will be filled in by subsequent lines
            current_list_key = key
            current_map_key = key
            out[key] = None  # Will be set by first nested item
        else:
            out[key] = value

    return out


def load_config(path: Path) -> MeshConfig:
    """Load and validate a .claude-mesh config file."""
    if not path.is_file():
        raise ConfigError(f"Config not found: {path}")

    size = path.stat().st_size
    if size > MAX_CONFIG_BYTES:
        raise ConfigError(f"Config exceeds {MAX_CONFIG_BYTES} byte ceiling: {size}")

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"Config is not valid UTF-8: {exc}") from exc

    parsed = _parse_minimal_yaml(text)

    if "mesh_group" not in parsed:
        raise ConfigError("Missing required field: mesh_group")
    if "mesh_peer" not in parsed:
        raise ConfigError("Missing required field: mesh_peer")

    group = str(parsed["mesh_group"])
    peer = str(parsed["mesh_peer"])
    if not NAME_PATTERN.match(group):
        raise ConfigError(
            f"mesh_group {group!r} has invalid characters; only [a-z0-9-] allowed"
        )
    if not NAME_PATTERN.match(peer):
        raise ConfigError(
            f"mesh_peer {peer!r} has invalid characters; only [a-z0-9-] allowed"
        )

    paths_raw = parsed.get("cross_cutting_paths", [])
    if not isinstance(paths_raw, list):
        raise ConfigError("cross_cutting_paths must be a list")
    paths: list[str] = []
    for p in paths_raw:
        s = str(p)
        if ".." in s.split("/") or s.startswith("/"):
            raise ConfigError(
                f"cross_cutting_paths entry {s!r} must be relative with no '..' segments"
            )
        paths.append(s)

    peers_raw = parsed.get("mesh_peers", [])
    if not isinstance(peers_raw, list):
        raise ConfigError("mesh_peers must be a list")
    peers: list[str] = []
    for p in peers_raw:
        s = str(p)
        if not NAME_PATTERN.match(s):
            raise ConfigError(
                f"mesh_peers entry {s!r} has invalid characters; only [a-z0-9-] allowed"
            )
        peers.append(s)
    if len(peers) != len(set(peers)):
        raise ConfigError("mesh_peers must contain unique peer names")
    if peers and len(peers) < 2:
        raise ConfigError("mesh_peers must contain at least two peers")
    if peers and peer not in peers:
        raise ConfigError(
            f"mesh_peer {peer!r} must appear in mesh_peers {peers!r}"
        )

    # Parse remote_peers if present
    remote_peers_raw = parsed.get("remote_peers", {})
    if not isinstance(remote_peers_raw, dict):
        raise ConfigError("remote_peers must be a map")
    
    remote_peers: dict[str, RemotePeerConfig] = {}
    for remote_peer_name, remote_config_raw in remote_peers_raw.items():
        if not isinstance(remote_config_raw, dict):
            raise ConfigError(f"remote_peers.{remote_peer_name} must be a map")
        
        if not NAME_PATTERN.match(remote_peer_name):
            raise ConfigError(
                f"remote peer name {remote_peer_name!r} has invalid characters"
            )
        
        # Validate required fields
        if "host" not in remote_config_raw:
            raise ConfigError(f"remote_peers.{remote_peer_name} missing 'host'")
        if "user" not in remote_config_raw:
            raise ConfigError(f"remote_peers.{remote_peer_name} missing 'user'")
        if "inbox_path" not in remote_config_raw:
            raise ConfigError(f"remote_peers.{remote_peer_name} missing 'inbox_path'")
        
        remote_peers[remote_peer_name] = RemotePeerConfig(
            host=str(remote_config_raw["host"]),
            user=str(remote_config_raw["user"]),
            inbox_path=str(remote_config_raw["inbox_path"]),
        )

    return MeshConfig(
        mesh_group=group,
        mesh_peer=peer,
        cross_cutting_paths=paths,
        mesh_peers=peers,
        remote_peers=remote_peers,
        source_path=path,
    )


def find_config(start: Path, stop_at: Path | None = None) -> Path | None:
    """Walk up from `start` looking for a `.claude-mesh` file. Stop at `stop_at` exclusive."""
    current = start.resolve()
    stop = stop_at.resolve() if stop_at else None
    while True:
        candidate = current / ".claude-mesh"
        if candidate.is_file():
            return candidate
        if stop is not None and current == stop:
            return None
        if current.parent == current:
            return None
        current = current.parent
