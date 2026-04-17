# Claude Mesh v1 — Launch Checklist

Complete these steps in order when ready to go public.

---

## Pre-launch verification (should already be done — re-verify before flipping public)

- [ ] Full test suite green: `python3.11 -m pytest tests/ -v` (expect 79+ tests)
- [ ] Red test count gate passes: `python3.11 -m pytest tests/red/ -v` (expect 20 tests)
- [ ] No secrets in tracked files: `git grep -iE "(sk-[A-Za-z0-9]{20,}|ghp_|AKIA[0-9A-Z]{16}|-----BEGIN PRIVATE KEY-----|api[_-]?key\s*[=:]\s*[A-Za-z0-9-]{20,})"`
  (expect only test fixture strings in `tests/unit/test_sanitize.py` and `docs/plans/`)
- [ ] No private paths in code: `git grep -F "/Users/michaelfolk" -- '*.py' '*.sh'`
  (expect zero results)
- [ ] README renders correctly: open `README.md` locally and spot-check links

---

## Step 1 — Create GitHub repository (Task 8.5)

**This is the one step that makes the repo public. Do NOT run until ready to announce.**

```bash
gh repo create FolkTechAI/claude-mesh --public --source=. --remote=origin --push
```

This command:
1. Creates `FolkTechAI/claude-mesh` as a public GitHub repo
2. Sets it as the `origin` remote
3. Pushes all 44 local commits

If the repo already exists as private on GitHub, use instead:
```bash
# Flip existing private repo to public:
gh repo edit FolkTechAI/claude-mesh --visibility public
# Then push:
git push -u origin main
```

---

## Step 2 — Post-launch sanity checks

Run immediately after push:

- [ ] Visit `https://github.com/FolkTechAI/claude-mesh` — repo is public and indexed
- [ ] CI workflow triggers and passes (`Actions` tab — lint, test, shellcheck, red-test-count gate)
- [ ] README renders correctly — badges resolve, code blocks display, links work
- [ ] `docs/` directory is navigable
- [ ] `plugin.json` is accessible at the root
- [ ] License shows as `Apache-2.0` in the sidebar

---

## Step 3 — Marketplace submission (Task 8.6)

### Target registry

The Claude Code plugin marketplace. At time of writing (2026-04-17), Anthropic has not
publicly documented a self-service plugin submission portal. Check the current state
at launch time:

1. Visit `https://code.claude.com/docs` and search "plugin marketplace" or "plugin registry"
2. Check `https://code.claude.com/plugins` if that URL exists
3. Check the `plugin-dev` skill documentation via Claude Code: type `/plugin-dev:create-plugin`
   and ask "how do I submit a plugin to the marketplace?"

### Required metadata (already in plugin.json)

```json
{
  "name": "claude-mesh",
  "version": "0.1.0",
  "description": "FTAI-structured shared knowledge between Claude Code sessions. Works standalone or with Agent Teams.",
  "author": "FolkTech AI LLC",
  "license": "Apache-2.0",
  "homepage": "https://github.com/FolkTechAI/claude-mesh"
}
```

### Keywords to use in submission

`agent-teams`, `multi-agent`, `shared-memory`, `ftai`, `collaboration`, `hooks`,
`knowledge-persistence`, `claude-code-plugin`

### Submission process (fill in at launch time)

- [ ] Confirm submission endpoint/form URL from Anthropic docs
- [ ] Submit `plugin.json` + repo URL
- [ ] Note any required review or approval SLA

---

## Step 4 — Real Claude E2E validation (post-launch follow-up)

The simulated E2E in `scripts/e2e_simulated.sh` exercises the Python pipeline but not
live Claude Code processes. Before calling v1 "production validated":

- [ ] Run Agent Teams with `claude-mesh` installed: create a real team, have two Claude
  instances work on a shared file, verify `knowledge.ftai` accumulates correctly
- [ ] Verify `<mesh_context>` appears in Claude's next prompt (check via `UserPromptSubmit`
  hook trace or by printing from the hook)
- [ ] Run `claude-mesh doctor` in a real project dir — verify all checks pass
- [ ] Test graceful degradation in a real project without `.claude-mesh` — verify no errors

Document findings and update `docs/case-study.md` with real session excerpts.

---

## Step 5 — Optional: Announcement

Suggested announcement text for X/Twitter, Hacker News, or Anthropic Discord:

> Claude Mesh — open-source Claude Code plugin that gives your AI teammates persistent
> shared memory. Works with Agent Teams and standalone session pairs. Zero dependencies,
> Apache 2.0.
> https://github.com/FolkTechAI/claude-mesh

---

## What is NOT needed at launch

- No npm/PyPI publish needed — users install via `pip install git+https://github.com/FolkTechAI/claude-mesh`
  or clone + `pip install -e .`
- No domain or landing page needed for v1 — GitHub + README is sufficient
- No Docker image needed — Python stdlib only
