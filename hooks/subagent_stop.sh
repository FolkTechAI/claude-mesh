#!/bin/bash
# hooks/subagent_stop.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/_common.sh"
PAYLOAD="$(cat)"
echo "${PAYLOAD}" | python3.11 -m claude_mesh subagent-turn 2>>"${_log_dir}" || true
exit 0
