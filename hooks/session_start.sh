#!/bin/bash
# hooks/session_start.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/_common.sh"
# Prints status line; discard output if we're in auto-run context where stdout is not surfaced
run_py status || true
exit 0
