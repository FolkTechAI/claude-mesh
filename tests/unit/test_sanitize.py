# tests/unit/test_sanitize.py
from claude_mesh.sanitize import (
    MAX_BODY_CHARS,
    MAX_SUMMARY_CHARS,
    SensitiveDataFilter,
    sanitize_body,
    sanitize_field,
    sanitize_summary,
)


def test_strips_null_bytes():
    assert sanitize_field("hello\x00world") == "helloworld"


def test_strips_ansi_escapes():
    assert sanitize_field("\x1b[31mred\x1b[0m") == "red"


def test_strips_zero_width_chars():
    # Zero-width space U+200B between 'foo' and 'bar'
    assert sanitize_field("foo\u200bbar") == "foobar"


def test_truncates_body():
    long = "a" * (MAX_BODY_CHARS + 500)
    out = sanitize_body(long)
    assert out.endswith("[truncated: 500 more chars omitted]")
    assert len(out) <= MAX_BODY_CHARS + 50


def test_truncates_summary():
    long = "b" * (MAX_SUMMARY_CHARS + 100)
    out = sanitize_summary(long)
    assert out.endswith("[truncated: 100 more chars omitted]")


def test_redacts_common_secrets():
    f = SensitiveDataFilter()
    assert f.redact("AWS_SECRET_ACCESS_KEY=AKIAABCD1234EFGHIJKL") != \
        "AWS_SECRET_ACCESS_KEY=AKIAABCD1234EFGHIJKL"
    assert "[REDACTED]" in f.redact("Bearer abc123xyz456")
    assert "[REDACTED]" in f.redact("api_key: sk-proj-abcdefghij")
