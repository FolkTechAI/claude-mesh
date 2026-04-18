#!/bin/bash
# hooks/task_created.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"

PAYLOAD="$(cat)"
INFO="$(PAYLOAD="${PAYLOAD}" "${_PY}" - <<'PYEOF'
import json, os
try:
    d = json.loads(os.environ["PAYLOAD"])
    print(d.get("task_id", "") + "\t" + d.get("task_subject", ""))
except Exception:
    print("\t")
PYEOF
)"

IFS=$'\t' read -r TID TSUBJ <<< "${INFO}"
if [ -n "${TID}" ]; then
    echo "${PAYLOAD}" | PYTHONPATH="${_PLUGIN_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" "${_PY}" -m claude_mesh task-event --id "${TID}" --subject "${TSUBJ}" --status pending 2>>"${_log_dir}" || true
fi
exit 0
