# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-07-31

### Added

- Deterministic supervisor with observe, operator-approval, and narrowly gated
  automatic modes.
- Adversarial worker → critic → bounded revision → independent verifier loop.
- Isolated git worktrees, worker/critic/verifier role separation, cross-vendor
  review policy, leases, crash recovery, and configuration fingerprints.
- Bounded Claude, Codex, Grok, Hermes, and generic-command process adapters
  with structured output contracts, timeouts, output limits, and process-group
  termination.
- Append-only run audit, content-addressed artifacts, available vendor cost
  receipts, FTAI verification receipts, and verified experience candidates.
- `supervisor submit` workflow so an operator can create a governed coding run
  without manually authoring mesh config or task-ledger entries.

### Security

- Agent identities cannot approve runs, workers cannot self-verify, and a
  post-plan config change invalidates approval.
- Grok supervisor calls use a temporary minimal home and disable personal
  plugins, MCPs, memory, subagents, web search, telemetry, and feedback.
- Hermes oneshot is prohibited from the implementation-worker role because it
  bypasses interactive approvals.
- The supervisor never merges, commits, pushes, deploys, sends external
  messages, or deletes retained worktrees.

## [0.2.0] — 2026-07-31

### Added

- N-way standalone fanout with authoritative `mesh_peers` rosters.
- Cross-vendor Grok Build adapter.
- Transactional task ledger with exclusive claims, leases, bounded attempts,
  lease-expiry requeue, and dead-letter state.
- Completion evidence and independent verification transitions.
- Structured `@verification`, `@experience`, `@capability`, and `@heartbeat`
  FTAI events.
- Token-free `claude-mesh watch` wake seam for vendor supervisors.
- `claude-mesh --version` and expanded diagnostics.

### Fixed

- N-way task events no longer split hyphenated group names or assume two peers.
- Status counts every supported event and applies recipient/self filtering.
- Concurrent writers cannot interleave records or initialize duplicate headers.
- Exact byte cursors replace timestamp-only markers, preventing same-timestamp
  and clock-skew event loss.
- Team-mode read cursors are participant-scoped.
- Source, Python package, Claude plugin, and marketplace versions agree.

### Security

- Inbox files are corrected to mode `0600` on append.
- Completion and verification cannot succeed without evidence.
- Event IDs support deduplication while task idempotency keys prevent duplicate
  task creation.

## [0.1.2] — 2026-04-18

### Fixed
- **Bug: init accepted group names the runtime would later reject.** `claude-mesh init --group spike` used to write a config that the PostToolUse hook silently rejected with `"cannot infer peer from group name"`. `init` now validates that the group name contains one of the peer names and always writes an explicit `mesh_peers` list so resolution is unambiguous.
- **Bug: peer names containing hyphens silently disabled mesh writes.** `notify_change` used `cfg.mesh_group.split("-")` and required exactly 2 parts, which broke for any peer like `mesh-test` or project named `my-project`. Resolution now uses the explicit `mesh_peers` list when present, falling back to prefix/suffix match on the group name. Both routes handle multi-token peer names.

### Added
- `mesh_peers: [a, b]` — optional explicit peer list in `.claude-mesh`. Authoritative for peer inference; group name becomes a human-readable label.
- `claude-mesh init --other PEER` — explicit flag for the second peer in the pair.
- Regression tests for both bugs.

### Changed
- README install instructions now use the working `/plugin marketplace add` + `/plugin install` flow.
- README quickstart shows the two-peer init pattern and documents the `mesh_peers` field.

## [0.1.1] — 2026-04-17

- Initial public release of the plugin.
