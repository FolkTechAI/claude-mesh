# tests/unit/test_ftai.py
from claude_mesh.ftai import emit_tag, parse_file


def test_emit_single_line_tag():
    output = emit_tag("message", {
        "from": "alpha",
        "to": "beta",
        "timestamp": "2026-04-17T19:43:05Z",
        "body": "hello world",
    }, block=False)
    expected = (
        "@message\n"
        "from: alpha\n"
        "to: beta\n"
        "timestamp: 2026-04-17T19:43:05Z\n"
        "body: hello world\n"
        "\n"
    )
    assert output == expected


def test_emit_block_tag():
    output = emit_tag("decision", {
        "id": "use-ed25519",
        "title": "Use Ed25519",
        "content": "Chosen over RSA",
    }, block=True)
    assert output.startswith("@decision\n")
    assert output.rstrip().endswith("@end")
    assert "id: use-ed25519" in output


def test_parse_file_single_tag(tmp_path):
    path = tmp_path / "log.ftai"
    path.write_text(
        "@ftai v2.0\n"
        "\n"
        "@message\n"
        "from: alpha\n"
        "to: beta\n"
        "body: hello\n"
        "\n"
    )
    tags = parse_file(path)
    msg_tags = [t for t in tags if t.name == "message"]
    assert len(msg_tags) == 1
    assert msg_tags[0].fields["from"] == "alpha"
    assert msg_tags[0].fields["body"] == "hello"


def test_parse_file_block_tag(tmp_path):
    path = tmp_path / "log.ftai"
    path.write_text(
        "@ftai v2.0\n"
        "\n"
        "@decision\n"
        "id: use-ed25519\n"
        "title: Use Ed25519\n"
        "@end\n"
        "\n"
    )
    tags = parse_file(path)
    dec_tags = [t for t in tags if t.name == "decision"]
    assert len(dec_tags) == 1
    assert dec_tags[0].fields["id"] == "use-ed25519"
    assert dec_tags[0].is_block


def test_parse_malformed_raises(tmp_path):
    path = tmp_path / "bad.ftai"
    path.write_text("garbage without any @tags\n")
    import pytest
    from claude_mesh.ftai import FTAIParseError
    with pytest.raises(FTAIParseError):
        parse_file(path)


def test_parse_block_body_with_at_prefixed_line(tmp_path):
    """A block body line that STARTS with '@' must not hijack the block.

    Regression: message bodies inside @decision/@task/@schema blocks often
    contain lines beginning with '@' (an @-mention on its own line, a pasted
    code decorator, a quoted tag). The parser used to treat those as a new tag,
    silently dropping the open block, so the block's real @end then raised
    'Line N: @end without matching block tag' and crashed status/drain.
    """
    path = tmp_path / "log.ftai"
    path.write_text(
        "@ftai v2.0\n"
        "\n"
        "@decision\n"
        "id: pick-transport\n"
        "title: Pick transport\n"
        "body: chosen after review\n"
        "@property is a decorator we referenced\n"
        "@end\n"
        "\n"
    )
    tags = parse_file(path)
    dec = [t for t in tags if t.name == "decision"]
    assert len(dec) == 1
    assert dec[0].is_block
    assert dec[0].fields["id"] == "pick-transport"
