# ADR-004: Per-recipient inbox fanout for standalone N-way meshes

## Status

Accepted for v0.2.0.

## Context

The original SPEC-002 draft proposed replacing standalone per-peer inboxes with
one shared group log. Before approval, the deployed cross-vendor Claude/Grok
work proved that per-peer inboxes were already interoperable and operationally
useful. Current target scale is tens of trusted local agents, not thousands of
network participants.

## Decision

Standalone N-way meshes retain one FTAI inbox per participant. Broadcast
publication fans an event out to every declared participant except the sender.
Directed publication writes only the target inbox. A single `event_id` is
preserved across every fanout copy.

Every append uses an advisory process lock and complete-write loop. Header
initialization and event append share the same critical section. Each inbox is
consumed with an exact byte cursor.

Team mode keeps Anthropic's shared team log because that is the native shape of
the Agent Teams integration.

## Consequences

Benefits:

- Directed event bodies are not copied into unrelated participant logs.
- Every participant has a simple independent cursor.
- The deployed Claude and Grok adapters remain compatible.
- A damaged inbox affects one recipient rather than the entire group.
- Exact cursors eliminate timestamp collision and clock-skew loss.

Costs:

- A broadcast performs `N-1` local writes.
- Group-wide audit reconstruction reads multiple inboxes.
- Fanout is practical for the intended local scale but is not a design for
  massive distributed pub/sub.

If the system later crosses machines or reaches hundreds of participants, a
network transport can replace local fanout behind the publication seam without
changing the FTAI event contracts.
