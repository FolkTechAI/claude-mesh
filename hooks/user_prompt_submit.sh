#!/bin/bash
# hooks/user_prompt_submit.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"

PAYLOAD="$(cat)"

MESH_CTX="$(echo "${PAYLOAD}" | PYTHONPATH="${_PLUGIN_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" "${_PY}" -m claude_mesh drain --format=prompt 2>/dev/null || true)"

if [ -n "${MESH_CTX}" ]; then
    MESH_CTX="${MESH_CTX}" PAYLOAD="${PAYLOAD}" "${_PY}" - <<'PYEOF'
import json, os, sys
try:
    payload = json.loads(os.environ["PAYLOAD"])
    ctx = os.environ["MESH_CTX"]
    user_prompt = payload.get("prompt", "")
    new_prompt = ctx + "\n\n" + user_prompt
    print(json.dumps({"modified_prompt": new_prompt}))
except Exception:
    sys.exit(0)
PYEOF
    echo "${PAYLOAD}" | PYTHONPATH="${_PLUGIN_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" "${_PY}" -m claude_mesh mark-read 2>/dev/null || true
fi

exit 0
