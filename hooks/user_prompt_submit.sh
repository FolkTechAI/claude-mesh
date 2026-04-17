#!/bin/bash
# hooks/user_prompt_submit.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/_common.sh"

# Read the full hook payload from stdin once
PAYLOAD="$(cat)"

# Drain mesh context and prepend if anything unread
# Pass payload via stdin to the drain command
MESH_CTX="$(echo "${PAYLOAD}" | python3.11 -m claude_mesh drain --format=prompt 2>/dev/null || true)"

if [ -n "${MESH_CTX}" ]; then
    # Emit modified prompt via the hook output protocol
    # Claude Code expects a JSON response with a modified prompt field
    # Pass PAYLOAD and MESH_CTX via env vars to avoid heredoc interpolation issues with special chars
    MESH_CTX="${MESH_CTX}" PAYLOAD="${PAYLOAD}" python3.11 - <<'PYEOF'
import json, os, sys
try:
    payload = json.loads(os.environ["PAYLOAD"])
    ctx = os.environ["MESH_CTX"]
    user_prompt = payload.get("prompt", "")
    new_prompt = ctx + "\n\n" + user_prompt
    print(json.dumps({"modified_prompt": new_prompt}))
except Exception as e:
    sys.exit(0)
PYEOF
    # Advance the read marker now that events are injected
    echo "${PAYLOAD}" | python3.11 -m claude_mesh mark-read 2>/dev/null || true
fi

exit 0
