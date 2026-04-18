# hooks/_common.sh
# shellcheck shell=bash
# Common helpers for all claude-mesh hook wrappers.
# Source this file; do not execute directly.
set -eu

# Ensure log dir exists before we try to write to it
mkdir -p "${HOME}/.claude-mesh" 2>/dev/null || true

_log_dir="${HOME}/.claude-mesh/errors.log"
log_error() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> "${_log_dir}" 2>/dev/null || true
}

# Resolve plugin root whether or not Claude Code sets CLAUDE_PLUGIN_ROOT.
# BASH_SOURCE[0] is _common.sh; parent is hooks/; parent of that is the plugin root.
_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# Pick any reasonable python. Our code needs stdlib only and uses
# `from __future__ import annotations` so it runs on python3.9+.
_py() {
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
    elif command -v python >/dev/null 2>&1; then
        echo "python"
    else
        echo ""
    fi
}
_PY="$(_py)"

run_py() {
    if [ -z "${_PY}" ]; then
        log_error "no python3 found on PATH"
        return 0
    fi
    # Make the vendored package importable without pip install.
    PYTHONPATH="${_PLUGIN_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
        "${_PY}" -m claude_mesh "$@" 2>>"${_log_dir}" \
        || log_error "claude-mesh $* failed"
}
