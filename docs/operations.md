# FolkTech Mesh Operations

## Operating boundary

FolkTech Mesh 0.3 is designed for trusted agents running as the same operating
system user on one machine. It is not a network security boundary. A `to:`
field controls routing, not confidentiality.

The FTAI inboxes are the durable, human-readable event record. The SQLite task
ledger is the coordination authority for task ownership, leases, attempts, and
verification state.

## Adversarial supervisor

The supervisor is a deterministic state machine around model processes; it is
not another model pretending to be a manager. Its coding path is:

```text
operator approval -> isolated worktree -> worker -> adversarial critic
                  -> bounded revision -> critic replay -> independent verifier
                  -> verification receipt -> verified experience candidate
```

The worker cannot verify its own task. With the default policy, the critic must
use a different vendor and the verifier must be a third identity. Any critic
challenge is sent back as untrusted evidence for a bounded revision loop. A
verifier pass is the only path to `passed`.

Initialize once:

```bash
claude-mesh supervisor init \
  --group folktech-supervisor \
  --workspace-root /Users/you/Developer \
  --operator your-name
```

Submit a task and create its approval-gated run:

```bash
claude-mesh supervisor submit \
  --id FIX-42 \
  --subject "Fix calendar lookup" \
  --description "Reproduce the failure before changing code" \
  --workspace /Users/you/Developer/project \
  --acceptance-criteria "Regression test and full relevant suite pass" \
  --risk medium
```

Then approve and execute using the `run-...` identifier printed by `submit`:

```bash
claude-mesh supervisor approve --run-id run-... --by your-name
claude-mesh supervisor execute --run-id run-...
claude-mesh supervisor artifacts --run-id run-... --json
claude-mesh supervisor list --json
```

Modes in `~/.claude-mesh/supervisor.toml`:

- `observe`: plans only; execution is impossible.
- `approval`: every run waits for an operator. This is the default.
- `automatic`: only a task explicitly submitted with
  `--no-approval-required` and at or below `automatic_max_risk` can run.

Changing any selected worker, executable, model, sandbox-relevant setting, or
review policy after planning invalidates the run's configuration fingerprint.
The operator must create and approve a new plan. Configured agent identities
cannot grant operator approval.

Blunt boundary: every process runs as the same macOS user. The approval ledger
is a strong workflow invariant, but it is not a defense against a malicious
local process that already has unrestricted terminal and filesystem access.
Keep `claude-mesh supervisor approve` behind Hermes's universal action-control
approval and deny it to unattended cron jobs. A model must not be able to call
the approval command merely by writing `--by mike`.

Each run has bounded model calls, timeouts, output ceilings, review rounds, and
an isolated git worktree under `~/.claude-mesh/worktrees/`. Worktrees are kept
for inspection; the supervisor never merges, commits, pushes, deploys, or
deletes them. Claude receives a hard per-call dollar ceiling. Grok-reported
cost is accumulated and stops later calls after the run ceiling is exceeded.
Codex currently does not report cost through this CLI contract, so its safety
boundary is timeout, output, call count, sandbox, and explicit approval—not a
provable dollar cap.

Grok runs with a temporary minimal home containing only copied authentication,
with personal plugins, MCP servers, memory, subagents, web search, feedback,
and telemetry disabled. Claude runs in safe mode with customizations and MCPs
disabled. Codex critics and verifiers use its read-only sandbox; Codex workers
use workspace-write inside the isolated git worktree.

Passed runs publish hashed `@verification` receipts and `@experience`
candidates containing resolved critic findings. That is an auditable learning
seam for Myelin/Serena. It does not alter model weights, promote a new policy,
or rewrite supervisor code. Learning remains evidence-gated input to the
separate learning governor.

## Event delivery

Standalone messages are fanned out to each recipient's inbox:

```text
~/.claude-mesh/groups/{group}/{peer}.ftai
```

Writes use an exclusive process lock, complete-write loops, mode `0600`, and
single-critical-section header initialization. Reads commit exact byte cursors,
not wall-clock timestamps. This prevents same-timestamp events and clock skew
from silently skipping work.

Delivery remains at-least-once. Every new event has an `event_id`; a drain
suppresses duplicate IDs within the unread window. Task side effects must use
the task's `idempotency_key`, not message arrival, as the execution identity.

## Task lifecycle

```text
pending -> accepted -> in-progress -> completed -> verified
                     \-> failed       \-> rejected
expired lease -> pending -> ... -> dead-letter after max attempts
```

Only the declared assignee can claim a task. Claiming is transactional, so two
workers racing for the same task cannot both win. Starting, completing, and
failing require ownership of the current lease. Completion and verification
both require evidence.

Useful commands:

```bash
claude-mesh task list
claude-mesh task list --status pending --status failed
claude-mesh task sweep
claude-mesh task list --json
```

Run `task sweep` from a lightweight scheduler. It does not invoke a model.

## Verification and learning seams

AKE or another verifier can publish a standalone receipt:

```bash
claude-mesh verification \
  --id V-42 \
  --task-id RELEASE-42 \
  --verdict pass \
  --checks "policy, tests, artifact hash" \
  --evidence "receipt URI or compact evidence"
```

Only verified outcomes should be sent toward Myelin:

```bash
claude-mesh experience \
  --id E-42 \
  --task-id RELEASE-42 \
  --outcome "Release validation succeeded" \
  --lesson "Use the bounded retry path for transient provider failures" \
  --evidence "verification V-42" \
  --verified-by ake \
  --tag release \
  --tag retry-policy
```

These are protocol seams. FolkTech Mesh does not import or control AKE or
Myelin. Their adapters consume `@verification` and `@experience` events,
preserving component ownership and preventing an event bus from becoming a
god-system.

## Capability and presence

```bash
claude-mesh capability \
  --name code-review \
  --description "Reviews Python and TypeScript changes" \
  --risk medium \
  --status available \
  --constraints "No deploy authority"

claude-mesh heartbeat --state busy --task-id RELEASE-42
```

Capability records describe what an agent claims it can do. They are not
permissions. The action control plane remains authoritative for execution.

## Token-free wake seam

```bash
claude-mesh watch --timeout 0 --json
```

`watch` monitors only local file metadata and unread state. It does not call a
model, consume an event, or mark anything read. A vendor adapter or supervisor
can use its output to wake the relevant runtime.

Claude still drains on `UserPromptSubmit`. Grok drains at `Stop` because its
prompt hook cannot inject context. A runtime that offers a safe background
wake API can wrap `watch`; the mesh deliberately does not fake a wake by
injecting synthetic user messages.

## Diagnostics

```bash
claude-mesh --version
claude-mesh status
claude-mesh doctor
```

`doctor` checks configuration, roster routing, directory access, inbox parsing
and permissions, source/distribution version alignment, Claude plugin cache
version, and task-ledger integrity.

Before trusting a new installation:

1. Confirm every vendor adapter reports version `0.3.0`.
2. Send a directed message and a broadcast.
3. Run one task through claim, completion, and independent verification.
4. Expire a test lease and confirm it requeues.
5. Run the full test and simulated E2E suites.
