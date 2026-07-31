# SPEC-002: Claude Mesh v2 — N-way Mesh

| Field | Value |
|---|---|
| **Status** | Approved by CEO; implemented in v0.2.0 |
| **Author** | Mike Folk (FolkTech AI LLC) |
| **Created** | 2026-06-25 |
| **Target release** | v0.2.0 |
| **Supersedes** | Extends SPEC-001 (v1). v1 behavior remains valid; this spec adds N-way. |
| **Related** | SPEC-001 §2 (N-way deferred to v2), SPEC-001 Open Question #4 (storage model) |

---

## 1. Problem Statement

SPEC-001 shipped two modes. **Team mode** is already N-way (all teammates read+append one shared `knowledge.ftai`). **Standalone mode** is **pairs-only** — each peer owns a single-writer inbox file, and the model does not generalize past two peers.

Now that the developer runs **more than two** independent Claude Code sessions on one machine (multiple agents across multiple projects), standalone mode must support **three or more** participants: any participant can broadcast to the group or address a specific participant, and each participant sees only what it has not yet seen.

This spec resolves SPEC-001 Open Question #4 in favor of **per-recipient inbox
fanout** for standalone mode. This differs from the original draft's proposed
shared log. Live cross-vendor testing exposed the operational advantages:
recipient-scoped cursors, no raw directed-message exposure to non-recipients,
and compatibility with the already deployed Claude/Grok adapters. The accepted
decision is recorded in ADR-004.

## 2. Scope

### In scope for v2

- **N-way standalone mode** (3+ participants in one group), same-machine.
- **N-way per-recipient fanout:** one inbox per participant; broadcasts are
  appended to every recipient inbox except the sender.
- **Messaging semantics over recipient inboxes:**
  - **Broadcast** — `@message` with no `to:` → drained by every participant except the sender.
  - **Directed** — `@message to: <peer>` (or `to: [<peer>, <peer>]`) → drained only by the named participant(s).
  - **Threads** — existing `thread:` slug, unchanged.
- **Roster** = the `mesh_peers` list in `.claude-mesh` (already a list). Static/declared; no auto-discovery.
- **Two clean seams** (Section 3.3), enforced as code structure, not new features:
  - **Transport seam** — the message/FTAI core does not assume "local file."
  - **Adapter seam** — the FTAI/CLI core does not assume "Claude Code hooks."
- Security: maintain the SPEC-001 red-test floor (≥20, may not decrease) and add N-way coverage (Section 6).

### Out of scope for v2 (deliberately deferred)

- **Cross-machine / cross-network** participation (different LANs/houses). Becomes a future **transport** plug-in via the transport seam. Requires a transport decision + a security-model inversion (peer identity, authentication, E2E encryption) — out of scope here.
- **Additional cross-vendor adapters.** Grok is included in v0.2. Codex,
  Hermes, and other runtimes use the vendor-neutral CLI until dedicated
  lifecycle adapters are installed.
- **Named channels** (multiple rooms per group). v2 = one room per group.
- **Encryption / authentication** — same-machine, same-user trust boundary (unchanged from v1).
- **Vendor-native process wake** — v0.2 provides a token-free `watch` seam;
  each vendor adapter remains responsible for waking its own runtime safely.
- **Rename / rebrand** — the name remains **Claude Mesh**. No CLI/config/dir renames.

### Non-goals

- Replacing `SendMessage` or any Agent Teams primitive.
- Making `to:` an access-control or privacy boundary (see Section 4.3).

## 3. Architecture

### 3.1 One storage model

Standalone mode generalizes the deployed inbox model:

| Concern | v1 standalone (pairs) | v2 standalone (N-way) |
|---|---|---|
| Data file | one inbox file **per peer** (`{peer}.ftai`) | one inbox per participant, unchanged |
| Writers | single intended peer writer | many peer writers, serialized by advisory lock |
| Ordering | append order | append order plus unique `event_id` |
| Read state | timestamp marker | exact byte cursor per inbox |

Team mode retains its shared `knowledge.ftai`, with a separate cursor for every
teammate. The two modes intentionally keep different storage shapes because
their delivery primitives differ.

### 3.2 Drain semantics (the N-way core)

On publication, a broadcast is fanned out to every participant except the
sender. A directed event is appended only to the named recipient inbox. On its
supported lifecycle boundary, participant `P` drains events after its exact
byte cursor, including an event **iff**:

- the event's `from:` ≠ `P` (never echo your own messages), **and**
- the event has no `to:` (broadcast), **or** `to:` contains `P` (directed).

Then `P` advances its own cursor to the exact byte position covered by the
drain. Delivery is at-least-once; `event_id` supports deduplication.

### 3.3 The two seams (structural requirement)

These are **module boundaries**, not new transports/adapters. v2 implements exactly one of each (local-file transport; Claude-hook adapter), but the core must not hard-code either.

- **Publication seam.** `publish_event` owns recipient resolution and delivery;
  event producers do not construct inbox paths.
- **Adapter seam.** The FTAI core + CLI is vendor-neutral. Claude and Grok
  adapters drive the CLI at their own lifecycle boundaries.

Acceptance for the seams is a unit-level test that the core modules import neither file-path constants nor hook payload shapes directly (they go through the interface/adapter).

## 4. Behavior details

### 4.1 Config (`.claude-mesh`)

`mesh_peers` (already a list) is authoritative roster. A participant's own identity is `mesh_peer`. Validation: each name `[a-z0-9-]+`, unique within the group, `mesh_peer` ∈ `mesh_peers`.

### 4.2 Send

`claude-mesh send [--message|--decision|--note] TEXT [--to PEER[,PEER...]]`
- No `--to` → broadcast.
- `--to a,b` → directed to listed participants; validated against roster (unknown peer → non-zero exit, helpful stderr; hook never blocks).

### 4.3 `to:` is routing, not privacy

Standalone directed events are copied only to the recipient inbox, but `to:` is
still routing rather than cryptographic access control. Every process running as
the same operating-system user can read the local group directory.

## 5. Migration / compatibility

- Existing **pair** standalone meshes require no data migration. Their inbox
  files remain valid; v0.2 begins writing unique event IDs and migrates
  timestamp markers to exact cursors after the next successful drain.
- Team mode: no migration; already shared-log.
- Read-markers: legacy per-pair markers map to per-participant markers by peer name.

## 6. Security

All SPEC-001 §6 categories still apply (input injection, path security, sensitive-data exposure, LLM output injection, data-format integrity). v2 additions:

- **Red-test floor unchanged:** ≥20, may not decrease (CI-enforced).
- **New N-way red tests** (must fail with mitigation removed, pass with it in place):
  1. A directed `@message to: A` is **not** drained into B's context (routing correctness — explicitly *not* claimed as access control).
  2. Broadcast reaches all participants except the sender.
  3. Read-markers are independent: draining for A does not advance B's marker.
  4. Roster validation rejects `to:` to a non-roster peer (path/identity injection).
  5. Atomic append holds under N concurrent writers (no interleaved/corrupt events).

## 7. Testing

- Unit: drain filter (broadcast/directed/self-echo), roster validation, marker independence, seam-boundary import check.
- Integration: 3-participant group fixture — broadcast + directed + thread, each participant's drain verified independently.
- E2E: extend SPEC-001 scenarios with a 3-session standalone run.
- CI matrix unchanged (macOS 14+, Ubuntu 24.04, Python 3.11+; ruff/mypy/shellcheck; red-test-count gate).

## 8. Acceptance Criteria

- [x] N-way standalone: 3+ participants, broadcast and directed delivery.
- [x] Standalone uses locked per-recipient inbox fanout.
- [x] Exact participant-scoped cursors; independence and collision tests pass.
- [x] Vendor-neutral publication seam and Claude/Grok adapters.
- [x] Existing red tests and new N-way/concurrency tests pass.
- [x] `doctor` checks routing, permissions, versions, parsing, and task ledger.
- [x] CLI compatibility retained under the `claude-mesh` command.

## 9. Open Questions

1. **Marker storage at N scale** — one marker file per participant under the group dir vs. a single markers file keyed by participant. Lean: one file per participant (preserves single-writer-per-marker, matches v1 atomic-rename approach).
2. **Self-echo for the audit trail** — sender excludes its own events from *drain*, but they remain in the log for history. Confirmed desired (history complete; context not self-polluted).
3. **Future channels** — if named channels arrive, do they become sub-files per channel or a `channel:` field with drain filtering? Defer; note the parallel to the `to:` filter.

## 10. References

- SPEC-001 (v1) — `docs/specs/SPEC-001-claude-mesh-v1.md`
- ADR-001 (FTAI over JSON), ADR-002 (layer over Agent Teams), ADR-003 (dual-mode detection)
- FTAI v2.0 — https://github.com/FolkTechAI/ftai-spec

---

**END OF SPEC-002.**
