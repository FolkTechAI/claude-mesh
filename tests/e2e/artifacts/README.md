# E2E Simulated Artifacts

These artifacts were captured by `scripts/e2e_simulated.sh` during Phase 8 launch preparation.

## What these are

Each scenario runs `python3.11 -m claude_mesh` with constructed hook payloads against an
isolated `HOME` (temp directory). They prove the CLI pipeline end-to-end:

  hook payload (JSON) → CLI → FTAI write → FTAI read → `<mesh_context>` output

**What they are not:** artifacts from live Claude Code sessions. Real E2E validation
requires running Agent Teams with two active Claude Code processes. That run is a
post-launch follow-up (tracked in `LAUNCH_CHECKLIST.md`).

## Scenarios

### scenario-1/ — Agent Teams mode

Simulates teammate `backend` on team `hackathon`:

- `step1a` — PostToolUse edit on `src/api/auth.rs` → `@file_change` in knowledge.ftai
- `step1b` — SubagentStop with 200-char message → `@message` in knowledge.ftai
- `step1c` — TaskCreated (TASK-042) → `@task` in knowledge.ftai
- `step1d` — drain `--format prompt` → `<mesh_context unread="3">` block (what Claude would see)
- `knowledge.ftai` — the raw FTAI knowledge log

### scenario-2/ — Standalone vault+brain pair

Simulates vault project editing `src/api/auth.rs` (a cross-cutting path) and brain draining it:

- `step2a` — vault notify-change → writes `brain.ftai`
- `step2b` — brain drain → `<mesh_context unread="1">`
- `step2c` — brain mark-read
- `step2d` — brain drain after mark-read → empty (0 bytes)
- `brain.ftai` — brain's inbox (written by vault, single-writer guarantee)
- `vault_config.txt` / `brain_config.txt` — the `.claude-mesh` configs used

### scenario-3/ — Graceful degradation

No `.claude-mesh` config, no `team_name` in payload. Verifies all CLI commands exit 0
and write nothing:

- `step3a-3d` — notify-change, subagent-turn, task-event, drain — all exit 0, write nothing
- `step3e` — status → "inactive — no .claude-mesh config found"
- `step3f` — doctor → "inactive — no .claude-mesh found"

## Timestamps

Artifacts contain live ISO timestamps from the run. They are deterministic in structure
but not in exact timestamp values. This is expected — the FTAI schema uses timestamps
as event ordering fields, not as canonical identifiers.

## Re-running

```bash
# From repo root
bash scripts/e2e_simulated.sh
```

Each run overwrites the artifacts in place. The final run before the Phase 8 commit
is the canonical reference set.
