#!/bin/bash
# hooks/task_created.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"
PAYLOAD="$(cat)"
INFO="$(PAYLOAD="${PAYLOAD}" python3.11 - <<'PYEOF'
import json, os, sys
try:
    d = json.loads(os.environ["PAYLOAD"])
    print(d.get("task_id", "") + "\t" + d.get("task_subject", ""))
except Exception:
    print("\t")
PYEOF
)"
IFS=$'\t' read -r TID TSUBJ <<< "${INFO}"
if [ -n "${TID}" ]; then
    echo "${PAYLOAD}" | python3.11 -m claude_mesh task-event --id "${TID}" --subject "${TSUBJ}" --status pending 2>>"${_log_dir}" || true
fi
exit 0
