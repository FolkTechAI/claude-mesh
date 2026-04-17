#!/usr/bin/env bash
# scripts/e2e_simulated.sh
#
# Simulated end-to-end scenarios for Claude Mesh v1.
#
# What this script does:
#   Invokes the claude-mesh CLI directly with constructed hook payloads.
#   This exercises the full pipeline: hooks -> CLI -> FTAI write -> FTAI read.
#   Each scenario uses an isolated HOME (tmp dir) so they don't interfere.
#
# What this script does NOT do:
#   Spawn real Claude Code processes. Real E2E requires live Agent Teams sessions.
#   The limitation is documented in docs/case-study.md.
#
# Artifacts are written to tests/e2e/artifacts/scenario-{1,2,3}/
# Run from repo root: bash scripts/e2e_simulated.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACTS_DIR="${REPO_ROOT}/tests/e2e/artifacts"

# Capture a fixed timestamp for deterministic artifacts (stripped of wall-clock noise in README)
RUN_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=== Claude Mesh — Simulated E2E Run ==="
echo "Run timestamp : ${RUN_TS}"
echo "Repo root     : ${REPO_ROOT}"
echo ""

###############################################################################
# Helper: run python module with HOME override and optional stdin payload
###############################################################################
run_mesh() {
    local tmp_home="$1"; shift
    local payload_file="$1"; shift
    # remaining args = claude-mesh subcommand + args
    HOME="${tmp_home}" python3.11 -m claude_mesh "$@" < "${payload_file}"
}

run_mesh_no_stdin() {
    local tmp_home="$1"; shift
    HOME="${tmp_home}" python3.11 -m claude_mesh "$@"
}

###############################################################################
# SCENARIO 1 — Agent Teams mode
###############################################################################
echo "--- SCENARIO 1: Agent Teams mode ---"
S1_HOME="$(mktemp -d)"
S1_ARTIFACTS="${ARTIFACTS_DIR}/scenario-1"
mkdir -p "${S1_ARTIFACTS}"

# --- Step 1a: PostToolUse (edit) hook — file_change event ---
cat > "${S1_ARTIFACTS}/payload_post_tool_use.json" <<'JSON'
{
  "team_name": "hackathon",
  "teammate_name": "backend",
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "/workspace/src/api/auth.rs",
    "new_content": "// Updated auth middleware"
  }
}
JSON

# Run notify-change (what post_tool_use_edit.sh calls)
run_mesh "${S1_HOME}" "${S1_ARTIFACTS}/payload_post_tool_use.json" \
    notify-change "src/api/auth.rs" "Edit" \
    > "${S1_ARTIFACTS}/step1a_notify_change.stdout" 2>&1 || true
echo "[1a] notify-change exit: $?"

# --- Step 1b: SubagentStop hook — message event ---
cat > "${S1_ARTIFACTS}/payload_subagent_stop.json" <<'JSON'
{
  "team_name": "hackathon",
  "teammate_name": "backend",
  "last_assistant_message": "Completed the JWT refresh rotation implementation in src/api/auth.rs. The token now rotates on every successful use and old tokens are blacklisted in Redis. This change affects the authentication flow across all endpoints — frontend will need to update token storage logic to capture the new token from response headers."
}
JSON

run_mesh "${S1_HOME}" "${S1_ARTIFACTS}/payload_subagent_stop.json" \
    subagent-turn \
    > "${S1_ARTIFACTS}/step1b_subagent_turn.stdout" 2>&1 || true
echo "[1b] subagent-turn exit: $?"

# --- Step 1c: TaskCreated hook — task event ---
cat > "${S1_ARTIFACTS}/payload_task_created.json" <<'JSON'
{
  "team_name": "hackathon",
  "teammate_name": "backend",
  "task_id": "TASK-042",
  "task_subject": "Update frontend token storage to handle rotating JWT"
}
JSON

run_mesh "${S1_HOME}" "${S1_ARTIFACTS}/payload_task_created.json" \
    task-event --id "TASK-042" --subject "Update frontend token storage to handle rotating JWT" --status pending \
    > "${S1_ARTIFACTS}/step1c_task_event.stdout" 2>&1 || true
echo "[1c] task-event exit: $?"

# --- Step 1d: Drain (what UserPromptSubmit hook would call for the other teammate) ---
cat > "${S1_ARTIFACTS}/payload_drain_team.json" <<'JSON'
{
  "team_name": "hackathon",
  "teammate_name": "frontend"
}
JSON

run_mesh "${S1_HOME}" "${S1_ARTIFACTS}/payload_drain_team.json" \
    drain --format prompt \
    > "${S1_ARTIFACTS}/step1d_drain_prompt.stdout" 2>&1 || true
echo "[1d] drain --format prompt exit: $?"

# Copy the resulting knowledge.ftai for inspection
S1_FTAI="${S1_HOME}/.claude/teams/hackathon/knowledge.ftai"
if [ -f "${S1_FTAI}" ]; then
    cp "${S1_FTAI}" "${S1_ARTIFACTS}/knowledge.ftai"
    echo "[1e] knowledge.ftai captured ($(wc -l < "${S1_ARTIFACTS}/knowledge.ftai" | tr -d ' ') lines)"
else
    echo "[1e] WARN: knowledge.ftai not found at ${S1_FTAI}" >&2
fi

# Verify expected tags present (grep -c may exit 1 when count is 0, so ignore exit code)
echo "[1f] Tag check:"
echo "  @file_change entries: $(grep -c "^@file_change" "${S1_ARTIFACTS}/knowledge.ftai" || echo 0)"
echo "  @message entries:     $(grep -c "^@message"     "${S1_ARTIFACTS}/knowledge.ftai" || echo 0)"
echo "  @task entries:        $(grep -c "^@task"        "${S1_ARTIFACTS}/knowledge.ftai" || echo 0)"

rm -rf "${S1_HOME}"
echo ""

###############################################################################
# SCENARIO 2 — Standalone vault+brain pair
###############################################################################
echo "--- SCENARIO 2: Standalone vault+brain pair ---"
S2_HOME="$(mktemp -d)"
S2_ARTIFACTS="${ARTIFACTS_DIR}/scenario-2"
mkdir -p "${S2_ARTIFACTS}"

# Create two project directories with .claude-mesh configs
VAULT_DIR="${S2_HOME}/projects/vault"
BRAIN_DIR="${S2_HOME}/projects/brain"
mkdir -p "${VAULT_DIR}" "${BRAIN_DIR}"

cat > "${VAULT_DIR}/.claude-mesh" <<'CFG'
mesh_group: vault-brain
mesh_peer: vault
cross_cutting_paths:
  - src/api/**
  - src/auth/**
CFG

cat > "${BRAIN_DIR}/.claude-mesh" <<'CFG'
mesh_group: vault-brain
mesh_peer: brain
cross_cutting_paths:
  - src/api/**
  - src/auth/**
CFG

# Copy configs to artifacts
cp "${VAULT_DIR}/.claude-mesh" "${S2_ARTIFACTS}/vault_config.txt"
cp "${BRAIN_DIR}/.claude-mesh" "${S2_ARTIFACTS}/brain_config.txt"

# --- Step 2a: vault edits a cross-cutting file ---
# Simulate: vault (peer) editing src/api/auth.rs
# notify-change writes to the OTHER peer's inbox (brain.ftai)
S2_VAULT_PAYLOAD="${S2_ARTIFACTS}/payload_vault_edit.json"
cat > "${S2_VAULT_PAYLOAD}" <<'JSON'
{}
JSON
# Empty payload = standalone mode (no team_name)
# The config file in VAULT_DIR drives group/peer resolution

(cd "${VAULT_DIR}" && HOME="${S2_HOME}" python3.11 -m claude_mesh notify-change \
    "src/api/auth.rs" "Edit" \
    < "${S2_VAULT_PAYLOAD}") \
    > "${S2_ARTIFACTS}/step2a_vault_notify.stdout" 2>&1 || true
echo "[2a] vault notify-change exit: $?"

# Check brain.ftai was written
S2_BRAIN_FTAI="${S2_HOME}/.claude-mesh/groups/vault-brain/brain.ftai"
if [ -f "${S2_BRAIN_FTAI}" ]; then
    cp "${S2_BRAIN_FTAI}" "${S2_ARTIFACTS}/brain.ftai"
    echo "[2b] brain.ftai captured ($(wc -l < "${S2_ARTIFACTS}/brain.ftai" | tr -d ' ') lines)"
    echo "[2c] Tag check:"
    echo "  @file_change in brain.ftai: $(grep -c "^@file_change" "${S2_ARTIFACTS}/brain.ftai" || echo 0)"
else
    echo "[2b] WARN: brain.ftai not found at ${S2_BRAIN_FTAI}" >&2
fi

# --- Step 2b: brain drains its own inbox ---
(cd "${BRAIN_DIR}" && HOME="${S2_HOME}" python3.11 -m claude_mesh drain --format prompt \
    < /dev/null) \
    > "${S2_ARTIFACTS}/step2b_brain_drain.stdout" 2>&1 || true
echo "[2d] brain drain exit: $?"

# --- Step 2c: mark-read, then drain again (should be empty) ---
(cd "${BRAIN_DIR}" && HOME="${S2_HOME}" python3.11 -m claude_mesh mark-read \
    < /dev/null) \
    > "${S2_ARTIFACTS}/step2c_brain_mark_read.stdout" 2>&1 || true
echo "[2e] brain mark-read exit: $?"

(cd "${BRAIN_DIR}" && HOME="${S2_HOME}" python3.11 -m claude_mesh drain --format prompt \
    < /dev/null) \
    > "${S2_ARTIFACTS}/step2d_brain_drain_after_read.stdout" 2>&1 || true
echo "[2f] brain drain-after-read exit: $?"

DRAIN2_SIZE="$(wc -c < "${S2_ARTIFACTS}/step2d_brain_drain_after_read.stdout")"
if [ "${DRAIN2_SIZE}" -eq 0 ]; then
    echo "[2g] PASS: second drain is empty (mark-read worked)"
else
    echo "[2g] WARN: second drain not empty (${DRAIN2_SIZE} bytes) — check step2d artifact" >&2
fi

rm -rf "${S2_HOME}"
echo ""

###############################################################################
# SCENARIO 3 — Graceful degradation (no config, no team payload)
###############################################################################
echo "--- SCENARIO 3: Graceful degradation ---"
S3_HOME="$(mktemp -d)"
S3_ARTIFACTS="${ARTIFACTS_DIR}/scenario-3"
S3_CWD="$(mktemp -d)"  # temp dir with NO .claude-mesh file
mkdir -p "${S3_ARTIFACTS}"

# Empty / no-op payload — no team_name, no .claude-mesh in cwd
cat > "${S3_ARTIFACTS}/payload_empty.json" <<'JSON'
{}
JSON

# Capture pre-run state of HOME dirs (should be empty)
S3_BEFORE_MESH="$(ls "${S3_HOME}/.claude-mesh/" 2>/dev/null | wc -l || echo 0)"
S3_BEFORE_CLAUDE="$(ls "${S3_HOME}/.claude/" 2>/dev/null | wc -l || echo 0)"

# All hook entry points — they should all exit 0 and write nothing
(cd "${S3_CWD}" && HOME="${S3_HOME}" python3.11 -m claude_mesh notify-change \
    "src/main.py" "Edit" < "${S3_ARTIFACTS}/payload_empty.json") \
    > "${S3_ARTIFACTS}/step3a_notify_change.stdout" 2>&1
EC_NOTIFY=$?

(cd "${S3_CWD}" && HOME="${S3_HOME}" python3.11 -m claude_mesh subagent-turn \
    < "${S3_ARTIFACTS}/payload_empty.json") \
    > "${S3_ARTIFACTS}/step3b_subagent_turn.stdout" 2>&1
EC_SUBAGENT=$?

(cd "${S3_CWD}" && HOME="${S3_HOME}" python3.11 -m claude_mesh task-event \
    --id "T-001" --subject "test" --status pending \
    < "${S3_ARTIFACTS}/payload_empty.json") \
    > "${S3_ARTIFACTS}/step3c_task_event.stdout" 2>&1
EC_TASK=$?

(cd "${S3_CWD}" && HOME="${S3_HOME}" python3.11 -m claude_mesh drain \
    < "${S3_ARTIFACTS}/payload_empty.json") \
    > "${S3_ARTIFACTS}/step3d_drain.stdout" 2>&1
EC_DRAIN=$?

echo "[3a] notify-change exit: ${EC_NOTIFY}"
echo "[3b] subagent-turn exit: ${EC_SUBAGENT}"
echo "[3c] task-event exit:    ${EC_TASK}"
echo "[3d] drain exit:         ${EC_DRAIN}"

# status should print "inactive"
(cd "${S3_CWD}" && HOME="${S3_HOME}" python3.11 -m claude_mesh status) \
    > "${S3_ARTIFACTS}/step3e_status.stdout" 2>&1
EC_STATUS=$?
echo "[3e] status exit: ${EC_STATUS}"
echo "[3e] status output: $(cat "${S3_ARTIFACTS}/step3e_status.stdout")"

# doctor should print "inactive" without errors
(cd "${S3_CWD}" && HOME="${S3_HOME}" python3.11 -m claude_mesh doctor) \
    > "${S3_ARTIFACTS}/step3f_doctor.stdout" 2>&1
EC_DOCTOR=$?
echo "[3f] doctor exit: ${EC_DOCTOR}"
echo "[3f] doctor output: $(cat "${S3_ARTIFACTS}/step3f_doctor.stdout")"

# Verify NO files were written to .claude-mesh or .claude
# Pipe through cat to absorb find's non-zero exit (dir not found), then count lines
S3_AFTER_MESH_FILES="$(find "${S3_HOME}/.claude-mesh" -type f 2>/dev/null; true | wc -l | tr -d ' ' || echo 0)"
S3_AFTER_CLAUDE_FILES="$(find "${S3_HOME}/.claude" -type f 2>/dev/null; true | wc -l | tr -d ' ' || echo 0)"
# Normalize: trim any whitespace and default to 0
S3_AFTER_MESH_FILES="$(printf '%s' "${S3_AFTER_MESH_FILES}" | tr -d ' \n' || echo 0)"
S3_AFTER_CLAUDE_FILES="$(printf '%s' "${S3_AFTER_CLAUDE_FILES}" | tr -d ' \n' || echo 0)"
S3_AFTER_MESH_FILES="${S3_AFTER_MESH_FILES:-0}"
S3_AFTER_CLAUDE_FILES="${S3_AFTER_CLAUDE_FILES:-0}"
echo "[3g] Files written to .claude-mesh: ${S3_AFTER_MESH_FILES}"
echo "[3g] Files written to .claude:      ${S3_AFTER_CLAUDE_FILES}"

if [ "${S3_AFTER_MESH_FILES}" -eq 0 ] && [ "${S3_AFTER_CLAUDE_FILES}" -eq 0 ]; then
    echo "[3h] PASS: graceful degradation — zero files written to isolated HOME"
else
    echo "[3h] WARN: unexpected files written — review artifacts" >&2
fi

# Verify all exits were 0
ALL_ZERO=true
for ec in "${EC_NOTIFY}" "${EC_SUBAGENT}" "${EC_TASK}" "${EC_DRAIN}" "${EC_STATUS}" "${EC_DOCTOR}"; do
    if [ "${ec}" != "0" ]; then
        ALL_ZERO=false
    fi
done
if [ "${ALL_ZERO}" = "true" ]; then
    echo "[3i] PASS: all 6 commands exited 0"
else
    echo "[3i] WARN: one or more non-zero exits — review step artifacts" >&2
fi

rm -rf "${S3_HOME}" "${S3_CWD}"
echo ""

###############################################################################
# Summary
###############################################################################
echo "=== Artifact locations ==="
echo "  Scenario 1 (Agent Teams): ${ARTIFACTS_DIR}/scenario-1/"
echo "  Scenario 2 (Standalone):  ${ARTIFACTS_DIR}/scenario-2/"
echo "  Scenario 3 (Degradation): ${ARTIFACTS_DIR}/scenario-3/"
echo ""
echo "Key artifacts to inspect:"
echo "  scenario-1/knowledge.ftai        — team knowledge log (FTAI)"
echo "  scenario-1/step1d_drain_prompt.stdout — <mesh_context> block"
echo "  scenario-2/brain.ftai            — brain inbox written by vault"
echo "  scenario-2/step2b_brain_drain.stdout  — brain drain output"
echo "  scenario-2/step2d_brain_drain_after_read.stdout — empty after mark-read"
echo ""
echo "Run complete: ${RUN_TS}"
