# tests/unit/test_events.py
from claude_mesh.events import (
    DecisionEvent,
    FileChangeEvent,
    MessageEvent,
    NoteEvent,
    TaskEvent,
    header_block,
    render_event,
)


def test_header_block():
    out = header_block(group_or_team="vault-brain", participants=["vault", "brain"])
    assert out.startswith("@ftai v2.0")
    assert "@document" in out
    assert "@schema" in out
    assert "vault-brain" in out
    assert "participants: [vault, brain]" in out


def test_render_message():
    e = MessageEvent(from_="alpha", timestamp="2026-04-17T19:43:05Z", body="hello", to="beta")
    text = render_event(e)
    assert "@message" in text
    assert "from: alpha" in text
    assert "to: beta" in text
    assert "body: hello" in text


def test_render_file_change():
    e = FileChangeEvent(
        from_="alpha",
        timestamp="2026-04-17T19:42:11Z",
        path="src/api/auth.rs",
        tool="Edit",
        summary="3 files changed",
    )
    text = render_event(e)
    assert "@file_change" in text
    assert "path: src/api/auth.rs" in text


def test_render_decision_block_has_end():
    e = DecisionEvent(
        from_="alpha",
        timestamp="t",
        id="use-ed25519",
        title="Use Ed25519",
        content="Chosen",
    )
    text = render_event(e)
    assert "@decision" in text
    assert text.rstrip().endswith("@end")


def test_render_task_block_has_end():
    e = TaskEvent(from_="alpha", timestamp="t", id="1", subject="s", status="pending")
    text = render_event(e)
    assert "@task" in text
    assert text.rstrip().endswith("@end")


def test_render_note():
    e = NoteEvent(from_="alpha", timestamp="t", content="heads up")
    text = render_event(e)
    assert "@note" in text
