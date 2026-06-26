# SPEC-002: Claude Mesh v2 — N-way Mesh

| Field | Value |
|---|---|
| **Status** | Draft — pending CEO approval |
| **Author** | Mike Folk (FolkTech AI LLC) |
| **Created** | 2026-06-25 |
| **Target release** | v0.2.0 |
| **Supersedes** | Extends SPEC-001 (v1). v1 behavior remains valid; this spec adds N-way. |
| **Related** | SPEC-001 §2 (N-way deferred to v2), SPEC-001 Open Question #4 (storage model) |

---

## 1. Problem Statement

SPEC-001 shipped two modes. **Team mode** is already N-way (all teammates read+append one shared `knowledge.ftai`). **Standalone mode** is **pairs-only** — each peer owns a single-writer inbox file, and the model does not generalize past two peers.

Now that the developer runs **more than two** independent Claude Code sessions on one machine (multiple agents across multiple projects), standalone mode must support **three or more** participants: any participant can broadcast to the group or address a specific participant, and each participant sees only what it has not yet seen.

This spec resolves SPEC-001 Open Question #4 in favor of **collapsing standalone onto the team-mode storage model** (single shared log), and establishes two architectural seams so that future cross-location and cross-vendor work is additive, not a rewrite.

## 2. Scope

### In scope for v2

- **N-way standalone mode** (3+ participants in one group), same-machine.
- **Unified storage model:** one shared append-only `knowledge.ftai` per group; per-participant read-markers. Per-peer inbox files (v1 standalone) are retired.
- **Messaging semantics over the shared log:**
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
- **Cross-vendor** participation (Grok, Codex, other agents). Becomes a future **adapter** plug-in via the adapter seam. FTAI is already vendor-neutral; only the auto-wiring is Claude-specific.
- **Named channels** (multiple rooms per group). v2 = one room per group.
- **Encryption / authentication** — same-machine, same-user trust boundary (unchanged from v1).
- **Real-time push** — delivery remains turn-based (piggyback on `UserPromptSubmit`).
- **Rename / rebrand** — the name remains **Claude Mesh**. No CLI/config/dir renames.

### Non-goals

- Replacing `SendMessage` or any Agent Teams primitive.
- Making `to:` an access-control or privacy boundary (see Section 4.3).

## 3. Architecture

### 3.1 One storage model

Standalone mode adopts the team-mode model:

| Concern | v1 standalone (pairs) | v2 standalone (N-way) |
|---|---|---|
| Data file | one inbox file **per peer** (`{peer}.ftai`) | **one shared** `~/.claude-mesh/groups/{group}/knowledge.ftai` |
| Writers | single-writer-per-file | many writers, atomic `O_APPEND` ≤ `PIPE_BUF` (as team mode already does) |
| Ordering | n/a | append-time timestamp |
| Read state | one read-marker per pair | **one read-marker per participant** |

Team mode is unchanged. After v2, both modes share the same storage shape, eliminating the dual-storage-model branch in the code.

### 3.2 Drain semantics (the N-way core)

On `UserPromptSubmit`, a participant `P` drains the shared log for events newer than `P`'s read-marker, including an event **iff**:

- the event's `from:` ≠ `P` (never echo your own messages), **and**
- the event has no `to:` (broadcast), **or** `to:` contains `P` (directed).

Then `P` advances its own read-marker. Read-markers are independent per participant, so each Claude sees each message exactly once regardless of the others.

### 3.3 The two seams (structural requirement)

These are **module boundaries**, not new transports/adapters. v2 implements exactly one of each (local-file transport; Claude-hook adapter), but the core must not hard-code either.

- **Transport seam.** A `Transport` interface with the operations the core needs: `append(event)`, `read_since(marker)`, `advance_marker(marker)`. v2 ships `LocalFileTransport`. The message model, drain logic, and read-marker logic depend on the interface, never on file paths directly. (Future: a `NetworkTransport` is a new class, no core change.)
- **Adapter seam.** The FTAI core + CLI (`send`/`drain`/`status`) is the vendor-neutral surface. The Claude Code hooks are one **adapter** that drives the CLI on Claude lifecycle events. The core never imports hook-specific assumptions. (Future: a Codex/Grok adapter drives the same CLI.)

Acceptance for the seams is a unit-level test that the core modules import neither file-path constants nor hook payload shapes directly (they go through the interface/adapter).

## 4. Behavior details

### 4.1 Config (`.claude-mesh`)

`mesh_peers` (already a list) is authoritative roster. A participant's own identity is `mesh_peer`. Validation: each name `[a-z0-9-]+`, unique within the group, `mesh_peer` ∈ `mesh_peers`.

### 4.2 Send

`claude-mesh send [--message|--decision|--note] TEXT [--to PEER[,PEER...]]`
- No `--to` → broadcast.
- `--to a,b` → directed to listed participants; validated against roster (unknown peer → non-zero exit, helpful stderr; hook never blocks).

### 4.3 `to:` is routing, not privacy

On a single shared log, every participant can read the raw file (same-machine trust). `to:` controls **what is drained into whose context**, not who *can* read it. This is documented in the CLI help and the schema comment. True private DMs would require per-recipient files or encryption — explicitly out of scope.

## 5. Migration / compatibility

- Existing **pair** standalone meshes: on first v2 run, if legacy `{peer}.ftai` inbox files exist, `claude-mesh doctor` reports them and offers a one-shot merge into the group `knowledge.ftai` (append, dedup by `from:`+`timestamp`+`body` hash). No silent data loss.
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

- [ ] N-way standalone: 3+ participants, broadcast + directed + threads working.
- [ ] Standalone uses the shared-log model; per-peer inbox path retired (with migration in `doctor`).
- [ ] Per-participant read-markers; independence test passes.
- [ ] Transport seam + adapter seam in place; seam-boundary tests pass; v2 ships exactly one transport (local-file) and one adapter (Claude hooks).
- [ ] All SPEC-001 red tests still pass; new N-way red tests pass; total red-test count ≥ prior count.
- [ ] `claude-mesh doctor` healthy on fresh N-way install and reports/merges legacy pair inboxes.
- [ ] Name unchanged (Claude Mesh); no rename.
- [ ] CI green.

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
