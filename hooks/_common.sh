# hooks/_common.sh
# Common helpers for all claude-mesh hook wrappers.
# Source this file; do not execute directly.
set -eu

# Ensure log dir exists before we try to write to it
mkdir -p "${HOME}/.claude-mesh" 2>/dev/null || true

_log_dir="${HOME}/.claude-mesh/errors.log"
log_error() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> "${_log_dir}" 2>/dev/null || true
}

run_py() {
    # Forward stdin to python module; swallow exit codes to never block
    python3.11 -m claude_mesh "$@" 2>>"${_log_dir}" || log_error "claude-mesh $* failed"
}
