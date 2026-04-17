# src/claude_mesh/pathval.py
"""Path validation and glob matching for .claude-mesh.

Every path coming from config or from a peer is hostile until validated.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path


class PathValidationError(ValueError):
    """Raised when a path fails a security check."""


def validate_relative_path(path_str: str) -> None:
    """Reject absolute paths, parent traversal, null bytes, and empty strings."""
    if not path_str:
        raise PathValidationError("Empty path")
    if "\x00" in path_str:
        raise PathValidationError("Null byte in path")
    if path_str.startswith("/"):
        raise PathValidationError(f"Absolute path not allowed: {path_str!r}")
    parts = path_str.replace("\\", "/").split("/")
    if ".." in parts:
        raise PathValidationError(f"Parent traversal not allowed: {path_str!r}")


def validate_under_allowed_root(candidate: Path, allowed_root: Path) -> None:
    """Resolve and ensure `candidate` is under `allowed_root`. Follows symlinks."""
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise PathValidationError(f"Cannot resolve path: {candidate}") from exc
    try:
        resolved_root = allowed_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PathValidationError(f"Allowed root does not exist: {allowed_root}") from exc
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        raise PathValidationError(
            f"Path {resolved} is outside allowed root {resolved_root}"
        ) from None


def path_matches_any_glob(path: str, globs: list[str]) -> bool:
    """Check if path matches any fnmatch-style glob pattern."""
    for pattern in globs:
        if fnmatch.fnmatch(path, pattern):
            return True
        if "**" in pattern:
            # Translate ** to match across multiple path segments
            flat = pattern.replace("**", "*")
            if fnmatch.fnmatch(path, flat):
                return True
    return False
