# tests/red/test_sensitive_data.py
from claude_mesh.sanitize import SensitiveDataFilter


def test_aws_key_redacted():
    f = SensitiveDataFilter()
    text = "AWS_SECRET_ACCESS_KEY=aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567"
    out = f.redact(text)
    assert "aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567" not in out
    assert "REDACTED" in out


def test_bearer_token_redacted():
    f = SensitiveDataFilter()
    out = f.redact("Authorization: Bearer eyJhbGc.eyJzdWI.SIGNATURE")
    assert "SIGNATURE" not in out or "REDACTED" in out


def test_openai_key_redacted():
    f = SensitiveDataFilter()
    out = f.redact("OPENAI_KEY=sk-proj-abcdefghijklmnop")
    assert "sk-proj-abcdefghijklmnop" not in out


def test_high_entropy_secret_redacted():
    """Long alphanumeric runs look like secrets; flag them."""
    f = SensitiveDataFilter()
    out = f.redact("token = abcdef1234567890abcdef1234567890abcdef")
    assert "abcdef1234567890abcdef1234567890abcdef" not in out
