#!/bin/bash
# hooks/post_tool_use_edit.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/_common.sh"

PAYLOAD="$(cat)"

# Extract path + tool from payload
INFO="$(PAYLOAD="${PAYLOAD}" python3.11 - <<'PYEOF'
import json, os, sys
try:
    d = json.loads(os.environ["PAYLOAD"])
    tool = d.get("tool_name", "") or d.get("tool", "")
    inp = d.get("tool_input", {}) or {}
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    print(tool + "\t" + path)
except Exception:
    pass
PYEOF
)"

IFS=$'\t' read -r TOOL FILE_PATH <<< "${INFO}"

if [ -z "${FILE_PATH}" ] || [ -z "${TOOL}" ]; then
    exit 0
fi

# Convert absolute path to relative if possible
if [[ "${FILE_PATH}" = /* ]]; then
    FILE_PATH="${FILE_PATH#${PWD}/}"
fi

echo "${PAYLOAD}" | python3.11 -m claude_mesh notify-change "${FILE_PATH}" "${TOOL}" 2>>"${_log_dir}" || true
exit 0
