# src/claude_mesh/sanitize.py
"""Input sanitization and sensitive data redaction for peer-produced content."""

from __future__ import annotations

import re
import unicodedata

MAX_BODY_CHARS = 2048
MAX_SUMMARY_CHARS = 512

_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_ZERO_WIDTH_RE = re.compile(r"[\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]")


def sanitize_field(value: str) -> str:
    """Strip null bytes, ANSI escapes, zero-width chars. Normalize unicode (NFC)."""
    if not value:
        return ""
    value = value.replace("\x00", "")
    value = _ANSI_ESCAPE_RE.sub("", value)
    value = _ZERO_WIDTH_RE.sub("", value)
    value = unicodedata.normalize("NFC", value)
    # Collapse CRLF to LF; preserve other newlines inside body
    value = value.replace("\r\n", "\n")
    return value


def sanitize_body(value: str) -> str:
    """Sanitize and truncate to MAX_BODY_CHARS."""
    clean = sanitize_field(value)
    if len(clean) <= MAX_BODY_CHARS:
        return clean
    dropped = len(clean) - MAX_BODY_CHARS
    return clean[:MAX_BODY_CHARS] + f" [truncated: {dropped} more chars omitted]"


def sanitize_summary(value: str) -> str:
    """Sanitize and truncate to MAX_SUMMARY_CHARS."""
    clean = sanitize_field(value)
    if len(clean) <= MAX_SUMMARY_CHARS:
        return clean
    dropped = len(clean) - MAX_SUMMARY_CHARS
    return clean[:MAX_SUMMARY_CHARS] + f" [truncated: {dropped} more chars omitted]"


class SensitiveDataFilter:
    """Redact common credential patterns from strings before they reach the mesh log."""

    _PATTERNS: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"(?i)(aws_secret_access_key\s*[=:]\s*)([A-Za-z0-9+/=]{20,})"), r"\1[REDACTED]"),
        (re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([A-Za-z0-9_-]{16,})"), r"\1[REDACTED]"),
        (re.compile(r"(?i)(password\s*[=:]\s*)(\S+)"), r"\1[REDACTED]"),
        (re.compile(r"(?i)(bearer\s+)([A-Za-z0-9_.\-]{8,})"), r"\1[REDACTED]"),
        (re.compile(r"(sk-[A-Za-z0-9][A-Za-z0-9-]{15,})"), "[REDACTED]"),
        (re.compile(r"\b[A-Za-z0-9]{32,}\b"), "[REDACTED-HIGH-ENTROPY]"),
    ]

    def redact(self, text: str) -> str:
        out = text
        for pattern, replacement in self._PATTERNS:
            out = pattern.sub(replacement, out)
        return out
