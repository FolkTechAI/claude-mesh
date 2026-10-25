#!/bin/bash
# hooks/user_prompt_submit.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"

PAYLOAD="$(cat)"

MESH_CTX="$(echo "${PAYLOAD}" | PYTHONPATH="${_PLUGIN_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" "${_PY}" -m claude_mesh drain --format=prompt 2>/dev/null || true)"

if [ -n "${MESH_CTX}" ]; then
    # Only consume mail after the injection JSON actually lands on stdout.
    # The previous `except: sys.exit(0)` + unconditional mark-read lost mail
    # whenever the envelope failed to parse (truncated env, hostile stdin).
    INJECTED="$(
        MESH_CTX="${MESH_CTX}" PAYLOAD="${PAYLOAD}" "${_PY}" - <<'PYEOF' 2>>"${_log_dir}"
import json, os, sys
try:
    payload = json.loads(os.environ["PAYLOAD"])
    if not isinstance(payload, dict):
        raise ValueError("hook payload is not an object")
    ctx = os.environ["MESH_CTX"]
    user_prompt = payload.get("prompt", "")
    print(json.dumps({"modified_prompt": ctx + "\n\n" + user_prompt}))
except Exception as exc:
    print(f"claude-mesh hook: prompt merge failed: {exc}", file=sys.stderr)
    sys.exit(1)
PYEOF
    )" || {
        log_error "prompt merge failed; leaving mail unread"
        exit 0
    }
    if [ -z "${INJECTED}" ]; then
        log_error "prompt merge produced no output; leaving mail unread"
        exit 0
    fi
    printf '%s\n' "${INJECTED}"
    echo "${PAYLOAD}" | PYTHONPATH="${_PLUGIN_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" "${_PY}" -m claude_mesh mark-read 2>>"${_log_dir}" || true
fi

exit 0
