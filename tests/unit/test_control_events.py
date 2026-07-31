from claude_mesh.events import (
    CapabilityEvent,
    ExperienceEvent,
    HeartbeatEvent,
    VerificationEvent,
    render_event,
)


def test_verification_event_is_structured_block():
    text = render_event(
        VerificationEvent("ake", "t", "V-1", "T-1", "pass", "12 checks")
    )
    assert text.startswith("@verification")
    assert "verdict: pass" in text
    assert text.rstrip().endswith("@end")


def test_experience_requires_verification_fields_in_schema():
    text = render_event(
        ExperienceEvent(
            "serena",
            "t",
            "E-1",
            "T-1",
            "success",
            "Use bounded retries",
            "receipt V-1",
            "ake",
        )
    )
    assert text.startswith("@experience")
    assert "verified_by: ake" in text


def test_capability_and_heartbeat_render():
    capability = render_event(
        CapabilityEvent("codex", "t", "code-review", "Reviews code", "low", "available")
    )
    heartbeat = render_event(HeartbeatEvent("codex", "t", "idle"))
    assert "@capability" in capability
    assert "@heartbeat" in heartbeat
