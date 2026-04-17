# ADR-002: Layer Over Agent Teams, Not Replace or Parallel

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-04-17 |
| **Author** | Mike Folk (FolkTech AI LLC) |
| **Spec** | SPEC-001 Sections 1, 2, 3.1 |

---

## Context

Anthropic's Agent Teams feature lets Claude Code spawn teammate processes that share a task list and can message each other via `SendMessage`. Agent Teams solves coordination within a spawned team. What it does not provide is a **persistent, human-readable, structured shared knowledge layer** — a durable log of what happened, what was decided, and what changed across the team's work.

Three paths were considered for how Claude Mesh should relate to Agent Teams:

**Path A — Layer on top.** Claude Mesh adds a persistent knowledge layer alongside Agent Teams primitives. `SendMessage` handles ephemeral questions; Claude Mesh handles durable events. The plugin activates when Agent Teams is present and degrades gracefully when it's not.

**Path B — Replace Agent Teams primitives.** Claude Mesh provides its own task list and messaging, making Agent Teams optional or irrelevant. Full ownership of the coordination layer.

**Path C — Parallel, independent.** Claude Mesh operates completely independently, ignoring Agent Teams state. No integration, no awareness of team context.

Path B was eliminated because reimplementing Agent Teams primitives would duplicate Anthropic's work, require significant additional scope, and compete with a vendor-supported feature. Any reimplementation would be maintained by a single contributor against a moving target.

Path C was eliminated because the plugin would lose team-context signals (team name, teammate identity) that are only available via Agent Teams hooks. Ignoring those means poorer mode detection and weaker event attribution.

Path A preserves Agent Teams' strengths (task routing, ephemeral messaging) while adding what it lacks (persistence, structure, human-readable log). The two layers complement rather than compete.

---

## Decision

Layer on top of Agent Teams (Path A).

Claude Mesh hooks fire on Agent Teams events (`PostToolUse TeamCreate`, `SubagentStop`, `TeammateIdle`, `TaskCreated`, `TaskCompleted`) and use the `team_name` from those payloads to route events to the right knowledge file. The plugin also works standalone when Agent Teams is disabled — dual-mode detection (see ADR-003) means the same plugin serves both contexts.

---

## Consequences

**Positive:**
- Plugin works with Agent Teams when enabled and degrades gracefully when it's not — the same plugin serves both modes
- No reimplementation of Anthropic-owned primitives
- Team context (team name, teammate identity) is authoritative from the payload, not approximated
- Tight scope: Claude Mesh only has to solve the persistence and structure problem

**Negative / risks:**
- We depend on a small set of hook events being stable in Claude Code's API. If Anthropic renames or removes `SubagentStop`, `TaskCreated`, or `TeamCreate`, integration breaks. This is mitigated by the fact that hooks are documented and stable; breaking changes would affect all plugins.
- We cannot influence task routing or `SendMessage` behavior — those remain Anthropic-controlled. This is acceptable since we're not trying to replace them.
- If Agent Teams becomes unavailable or deprecated, team mode becomes unavailable. Standalone mode is unaffected.
