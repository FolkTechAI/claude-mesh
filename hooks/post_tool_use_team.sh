#!/bin/bash
# hooks/post_tool_use_team.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"

PAYLOAD="$(cat)"
TEAM_NAME="$(PAYLOAD="${PAYLOAD}" "${_PY}" - <<'PYEOF'
import json, os
try:
    d = json.loads(os.environ["PAYLOAD"])
    inp = d.get("tool_input", {}) or {}
    print(inp.get("team_name", ""))
except Exception:
    pass
PYEOF
)"

if [ -n "${TEAM_NAME}" ]; then
    mkdir -p "${HOME}/.claude/teams/${TEAM_NAME}" 2>/dev/null || true
fi
exit 0
