# tests/red/test_format_integrity.py
import pytest

from claude_mesh.ftai import FTAIParseError, parse_file


def test_malformed_file_rejected(tmp_path):
    p = tmp_path / "bad.ftai"
    p.write_text("this is not ftai\nfor sure\n")
    with pytest.raises(FTAIParseError):
        parse_file(p)


def test_oversized_file_rejected(tmp_path):
    p = tmp_path / "huge.ftai"
    p.write_text("@ftai v2.0\n" + "x" * (11 * 1024 * 1024))
    with pytest.raises(FTAIParseError, match="ceiling"):
        parse_file(p)


def test_unclosed_block_tag_rejected(tmp_path):
    p = tmp_path / "unclosed.ftai"
    p.write_text(
        "@ftai v2.0\n\n"
        "@decision\nid: x\ntitle: y\ncontent: z\n"
    )
    with pytest.raises(FTAIParseError):
        parse_file(p)


def test_future_timestamps_tolerated_but_logged(tmp_path):
    """Events with future timestamps can still be parsed; higher layers decide policy."""
    p = tmp_path / "future.ftai"
    p.write_text(
        "@ftai v2.0\n\n"
        "@message\nfrom: x\ntimestamp: 2099-01-01T00:00:00Z\nbody: later\n\n"
    )
    tags = parse_file(p)
    assert any(t.name == "message" for t in tags)
