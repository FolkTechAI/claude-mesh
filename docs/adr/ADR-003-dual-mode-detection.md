# ADR-003: Dual-Mode Detection via team_name Field Presence

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-04-17 |
| **Author** | Mike Folk (FolkTech AI LLC) |
| **Spec** | SPEC-001 Section 3.1 |

---

## Context

Claude Mesh must work in two scenarios:

1. **Team mode** — Claude Code is running with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and the session was spawned as part of a team
2. **Standalone mode** — Two independent `claude` sessions on paired projects, no Agent Teams dependency

When a hook fires, the script must determine which mode applies and route accordingly — different knowledge file paths, different group/peer identity sources, different storage semantics.

Three detection approaches were considered:

**Option 1 — Environment variable check.** Test whether `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set. Simple, but wrong: the flag being set doesn't mean this session is part of a team. A developer might enable the flag globally but run a solo session.

**Option 2 — Config file scan.** Check whether `.claude-mesh` exists. Simple for standalone detection, but says nothing about whether a team is active. A developer might have `.claude-mesh` present and have Agent Teams enabled — which mode wins?

**Option 3 — Hook payload inspection.** Anthropic's Agent Teams injects a `team_name` field into hook payloads for sessions that are part of a team. Its presence unambiguously signals "this session is a team member." Its absence, combined with `.claude-mesh` being discoverable, signals standalone mode.

Option 3 is the most accurate because the signal is authoritative — it comes from the runtime, not from user configuration. The env var check produces false positives; config scan alone is ambiguous.

---

## Decision

Detect mode by inspecting the hook payload for `team_name`:

```python
if payload.get("team_name"):
    return Mode.TEAM
elif config_found:
    return Mode.STANDALONE
else:
    return Mode.INACTIVE  # silently inactive
```

This is a one-line detector. It requires no configuration, no external state, and no env var interpretation.

---

## Consequences

**Positive:**
- Detection is correct by construction: the signal is authoritative and runtime-provided
- No false positives from env var checks
- No ambiguity between "teams enabled" and "in a team"
- Zero configuration required for team mode — the plugin just works when Agent Teams spawns a teammate

**Negative / risks:**
- If Anthropic renames `team_name` to a different field name in a future Claude Code release, detection breaks. The fix is a one-line update to the detector. Given how stable hook payload fields have been across Claude Code versions, this risk is low.
- If Anthropic adds a `team_name` field to non-team sessions (unlikely but theoretically possible), the plugin would incorrectly activate team mode. This would produce a non-fatal but confusing behavior: attempting to write to a team knowledge file that doesn't exist, logging an error, and falling through to inactive.

Both failure modes are detectable via `claude-mesh doctor` and produce log entries rather than silent corruption.
