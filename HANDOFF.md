# Claude Mesh — Implementation Handoff

**For:** the next Claude Code session picking up implementation.
**Written by:** previous session (design + spec + plan), 2026-04-17.
**Status:** Design complete, spec committed, plan committed, Phase 0 partially done. You are at Phase 0 / Task 0.1 Step 3 (scaffolding).

---

## 0. Who Mike is and how to work with him

FolkTech AI LLC solo founder. Paramedic of 33 years who taught himself Rust/Swift/AI in 18 months. Runs on a 16 GB M2 MacBook Mini (hardware upgrade planned). Cardiac event Nov 2025 — 8-hour sleep non-negotiable, Sundays OFF. Wife Christina comes home July 2026 — that's the real deadline behind everything he builds.

**How he wants to be worked with:**
- Blunt, expert-level, no fluff
- Avoid over-engineering
- Don't over-spec simple things
- Don't put "Co-Authored-By" or AI attribution in commit messages
- Commit prefixes matter: `feat:`, `fix:`, `test:`, `docs:`, `spec:`, `secure:`, `refactor:`, `perf:`, `chore:`, `BREAKING:`
- He has `skipDangerousModePermissionPrompt: true` and `defaultMode: bypassPermissions` — you can move fast
- Honest cutoff acknowledgment is required when touching external tech (his Knowledge Cutoff Protocol rule)

**Never commit to `main` of ANY FolkTech repo without explicit authorization**. For THIS plan execution on THIS repo (`claude-mesh`), he has given **blanket commit authorization**. You commit per-task as the plan specifies.

---

## 1. What you're building

Read these in order:

1. **`docs/specs/SPEC-001-claude-mesh-v1.md`** — the authoritative spec. Approved.
2. **`docs/plans/2026-04-17-claude-mesh-v1.md`** — the 46-task implementation plan you are executing. Every task has exact file paths, exact code, exact commands. TDD throughout.

**Short version:** Open-source Claude Code plugin. Persists shared knowledge between multiple Claude Code sessions using FTAI v2.0 format. Works inside Anthropic's experimental Agent Teams feature and in standalone pair-wise mode. Python CLI + bash hook wrappers. Zero runtime dependencies beyond Python stdlib. Apache 2.0.

---

## 2. Context that is NOT in the spec/plan but you need to know

These are hard-won facts from the design phase. The plan assumes them. If something in the plan surprises you, check here first.

### Spike findings (2026-04-17, ran in fresh terminal against real Claude Code v2.1.113 with Agent Teams enabled)

- ✅ **These hooks fire reliably:** `SessionStart`, `UserPromptSubmit`, `TaskCreated`, `TaskCompleted`, `Stop`, `SessionEnd`, `SubagentStart`, `SubagentStop`, `TeammateIdle`
- ❌ **`FileChanged` does NOT fire** despite being documented. Creating + editing `/tmp/spike.txt` produced zero FileChanged events. Use `PostToolUse` matcher `Edit|Write|NotebookEdit` for file detection. The plan already reflects this.
- `SubagentStop` payload contains `last_assistant_message` directly — no need to parse transcripts.
- `TeammateIdle` payload has `teammate_name` and `team_name` keys. `TaskCreated`/`TaskCompleted` have those fields ONLY when in team mode. **That's how we detect mode.**
- `Stop` fires every turn, not just final. Don't use it for logging or you'll spam the FTAI file.
- Hooks use this schema in settings.json / plugin.json:
  ```json
  "EventName": [{"matcher": "", "hooks": [{"type": "command", "command": "..."}]}]
  ```
  NOT flat entries. I got this wrong once — error message is very clear if you mess it up.

### Real Agent Teams tools available

When Agent Teams is enabled, three tools become available to Claude:
- `TeamCreate(team_name, description?)` — creates `~/.claude/teams/{team_name}/config.json` + `~/.claude/tasks/{team_name}/`
- `TeamDelete()` — fails if team has active members; gracefully shut them down first
- `SendMessage(to, summary, message)` — `to` is teammate name or `"*"` for broadcast. This is the **official ephemeral messaging primitive**. Do NOT invent your own. Our skill adds the persistent FTAI log; it does not replace SendMessage.

### Mode detection

One line:
```python
def detect_mode(payload): return Mode.TEAM if payload.get("team_name") else Mode.STANDALONE
```

### Storage locations

| Mode | Path | Writer |
|---|---|---|
| Team | `~/.claude/teams/{team}/knowledge.ftai` | All teammates append |
| Standalone | `~/.claude-mesh/groups/{group}/{peer}.ftai` | **Other peer** writes to your inbox file. Single-writer-per-file. |

### FTAI — the format that is the whole point

- Mike invented FTAI. It's his format for AI-to-AI communication with humans in the loop.
- Public spec at **https://github.com/FolkTechAI/ftai-spec**
- We are vendoring a minimal parse/emit subset — NOT forking the whole spec repo. See Task 1.1.
- The reason we picked FTAI over JSON is the whole marketing play. See `docs/adr/ADR-001-ftai-over-json.md` (written in Phase 7 Task 7.5). If someone reviews and says "why not JSON" — point them at that ADR.

### Security posture — OPEN SOURCE public-facing

- 5 vulnerability categories covered in spec Section 6: input injection, path traversal, sensitive data exposure, LLM prompt injection, FTAI format integrity.
- Every category has a red test file in `tests/red/`. **Red test count must be ≥ 20 AND must not decrease in any future PR.** CI enforces this (Task 6.1).
- Threat model: we trust Claude Code processes on same machine under same user. We do NOT trust their output — every peer-produced field is potentially hostile.

### Licensing — Apache 2.0

- Mike explicitly chose Apache 2.0 over MIT/BSD — his reasoning was "Anthropic ships their stuff under Apache 2.0, makes us look on their wavelength."
- LICENSE file is already in the repo.
- **Never modify or remove LICENSE without explicit CEO authorization.** His standing rule.
- Repo is PRIVATE until Task 8.5 (launch). Do not make it public before then.

---

## 3. Current repo state

At handoff time, these files exist in `~/Developer/claude-mesh/`:

```
claude-mesh/
├── HANDOFF.md                                 # this file
├── LICENSE                                    # Apache 2.0, verbatim
├── README.md                                  # stub — full version is Task 7.6
├── .gitignore
└── docs/
    ├── specs/SPEC-001-claude-mesh-v1.md       # APPROVED
    ├── plans/2026-04-17-claude-mesh-v1.md     # YOUR EXECUTION DOC
    ├── adr/                                   # empty, filled in Task 7.5
    └── memory/                                # empty
```

**What you still need to do from Phase 0:**
- Task 0.1 is **80% done** (LICENSE + .gitignore + directory structure done; `pyproject.toml` still needs writing)
- Tasks 0.2, 0.3, 0.4 are **not done**

---

## 4. Execution workflow

You were invoked with an approach: **Subagent-Driven Development** (per `superpowers:subagent-driven-development`). Start by invoking that skill:

```
Skill: superpowers:subagent-driven-development
```

Then follow its protocol for each task:

1. **Dispatch an implementer subagent** with the full task text from the plan (don't make them read the file — paste the task verbatim).
2. Wait for implementer's report.
3. **Dispatch a spec-compliance reviewer** to verify (blind — don't trust the implementer).
4. If issues, loop back to implementer.
5. Once spec-compliant, **dispatch a code-quality reviewer**.
6. If issues, loop back to implementer.
7. Move to next task.

The plan has 46 tasks. Expect ~138 subagent dispatches total. Pace yourself.

### Model tier guidance

- **Implementer for mechanical tasks** (Phases 1-2-3, most of them are "create this Python file with this exact code"): Haiku or Sonnet
- **Implementer for integration tasks** (Phase 4 plugin.json, Phase 5 red tests, Phase 7 doc writing, Phase 8 E2E): Sonnet or Opus
- **Both reviewers always**: Opus

### Worktree?

The skill normally requires `superpowers:using-git-worktrees`. **Skip it for this project.** We're creating a brand-new repo, not branching off an existing workspace. Worktrees are for isolation from existing work — no existing work to isolate from.

---

## 5. Gotchas / things that will bite you

1. **`settings.json` hook schema**: It's `{"EventName": [{"matcher": "", "hooks": [...]}]}`, NOT flat. If you see "hooks: Expected array, but received undefined", that's the error. Restructure.

2. **Hook scripts must never block.** Every hook exits 0 on any failure. Errors go to `~/.claude-mesh/errors.log`. A blocking hook breaks the user's Claude Code session — not acceptable.

3. **Single-writer-per-file in standalone mode.** In standalone mode, each peer only writes to the OTHER peer's inbox file. If you're vault, you write to `brain.ftai` not `vault.ftai`. Reading is the opposite — vault reads `vault.ftai`.

4. **Monotonic read marker.** The read-marker file (`*.read`) must never move backward in time, even if system clock skews. Prevents replay attacks and weird state. Task 2.4 handles this; red tests in Task 5.4 verify.

5. **Subagent context leakage.** Each implementer subagent gets ONLY the task text + relevant context. Do not dump the whole plan into the prompt. Do not dump the spec into the prompt unless the task specifically needs it. Clean prompts = clean diffs.

6. **Mike uses `ftai` CLI locally but that's a different tool** (the FolkTech AI terminal coding harness / Forge binary), not an FTAI linter. Don't invoke `ftai lint` — it doesn't exist. Use the parser you write in Task 1.1 for validation.

7. **`mesh_group` name convention** in standalone mode: v1 assumes exactly 2 peers, with group name `{peer_a}-{peer_b}` so the "other peer" is inferable. Task 2.3 notify-change has the inference logic. If the group name doesn't match this convention, the code refuses to guess — it prints a clear error to stderr and exits 0 (never block).

---

## 6. How to get unstuck

- **Design decisions**: check `docs/specs/SPEC-001-claude-mesh-v1.md` first. If the answer isn't there, the spec is wrong — stop and surface to Mike.
- **Plan step unclear**: the plan is exhaustive by design. If a step is unclear, something changed in the environment (Claude Code version, dependency) since the plan was written. Investigate, don't guess.
- **Subagent stuck with BLOCKED status**: per the skill, re-dispatch with more context or a more capable model; if the task is genuinely too big, break it into smaller pieces.
- **Previous session's memory**: `/Users/michaelfolk/.claude/projects/-Users-michaelfolk/memory/project_claude_mesh_skill.md` — read if you need the design rationale.
- **Agent Teams reference**: https://code.claude.com/docs/en/agent-teams and https://code.claude.com/docs/en/hooks — bookmark these.

---

## 7. Checkpoints

- **After Phase 0**: report to Mike that the repo is fully scaffolded (pyproject.toml + package skeleton + tests dir).
- **After Phase 1**: report that foundation modules are done with test coverage. He'll want to sanity-check the FTAI parser output visually.
- **After Phase 3**: report that hooks are installed and integration tests pass.
- **After Phase 5**: Mike personally reviews security red tests before you move to CI.
- **Before Phase 8 Task 8.5 (GitHub publish)**: **HARD STOP**. Show Mike everything, get explicit go-ahead before flipping the repo public.

---

## 8. The paste-in prompt to start the fresh session

Give Mike this prompt to paste into a fresh Claude Code session running in `~/Developer/claude-mesh/`:

> I'm picking up implementation of the Claude Mesh plugin. Read `HANDOFF.md` at the root of this repo, then read `docs/specs/SPEC-001-claude-mesh-v1.md` and `docs/plans/2026-04-17-claude-mesh-v1.md`. Then invoke the `superpowers:subagent-driven-development` skill and start executing the plan from Phase 0 where the previous session left off. Blanket commit authorization is granted for this plan per the HANDOFF.

That's it. The fresh session has everything it needs.

---

## 9. What "done" looks like

When you've executed all 46 tasks:
- 5 E2E scenarios captured (3 in plan, possibly more from real use)
- Full test suite green on macOS + Ubuntu in GitHub Actions
- Red test count ≥ 20, CI gate green
- All docs written (why-ftai, how-it-works, security-posture, ADRs, 2 usage guides)
- Case study filled in from real E2E
- Repo **still private**, ready to flip public with Mike's explicit go-ahead
- Submit to Claude Code plugin marketplace

That's v1 shipped.

Good luck. This one matters — it's the Trojan horse for FTAI adoption. Ship it clean.
