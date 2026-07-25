# hooks-grok/_common.sh
# shellcheck shell=bash
# Common helpers for the Grok Build mesh adapter.
# Source this file; do not execute directly.
#
# Grok Build differs from Claude Code in three ways that matter here:
#   1. stdin envelope keys are camelCase (toolName, toolInput, cwd, workspaceRoot)
#   2. edit tools are named search_replace / write_file / apply_patch, not Edit/Write
#   3. only Stop and SubagentStop can inject context; every other event is
#      passive and its stdout is discarded
set -eu

mkdir -p "${HOME}/.claude-mesh" 2>/dev/null || true
_log_dir="${HOME}/.claude-mesh/errors.log"
log_error() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [grok] $*" >> "${_log_dir}" 2>/dev/null || true
}

# hooks-grok/_common.sh -> hooks-grok/ -> plugin root
_PLUGIN_ROOT="${CLAUDE_MESH_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

_py() {
    if command -v python3 >/dev/null 2>&1; then echo "python3"
    elif command -v python >/dev/null 2>&1; then echo "python"
    else echo ""; fi
}
_PY="$(_py)"

# Run the mesh CLI. Always with stdin closed: the hook already consumed the
# envelope, and an inherited never-EOF pipe would otherwise stall the turn.
run_mesh() {
    if [ -z "${_PY}" ]; then
        log_error "no python3 on PATH"
        return 0
    fi
    PYTHONPATH="${_PLUGIN_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
        "${_PY}" -m claude_mesh "$@" </dev/null 2>>"${_log_dir}" \
        || log_error "claude-mesh $* failed"
}

# Same, but returns stdout to the caller.
run_mesh_capture() {
    if [ -z "${_PY}" ]; then echo ""; return 0; fi
    PYTHONPATH="${_PLUGIN_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
        "${_PY}" -m claude_mesh "$@" </dev/null 2>>"${_log_dir}" || true
}

# Read a top-level string field out of the JSON envelope in $1.
json_field() {
    PAYLOAD="$1" FIELD="$2" "${_PY}" - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    d = json.loads(os.environ["PAYLOAD"])
    v = d.get(os.environ["FIELD"], "")
    print("" if v is None else (str(v).lower() if isinstance(v, bool) else str(v)))
except Exception:
    print("")
PYEOF
}
