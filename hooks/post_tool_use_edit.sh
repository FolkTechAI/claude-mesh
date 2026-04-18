#!/bin/bash
# hooks/post_tool_use_edit.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"

PAYLOAD="$(cat)"

# Extract tool + file_path, making the path project-relative when possible.
# We use Python's os.path.realpath on both sides so symlink-resolved paths
# (e.g. macOS /private/tmp vs /tmp) collapse correctly.
INFO="$(PAYLOAD="${PAYLOAD}" PWD_FALLBACK="${PWD}" "${_PY}" - <<'PYEOF'
import json, os
try:
    d = json.loads(os.environ["PAYLOAD"])
    tool = d.get("tool_name", "") or d.get("tool", "")
    inp = d.get("tool_input", {}) or {}
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    cwd = d.get("cwd", "") or os.environ.get("PWD_FALLBACK", "") or os.getcwd()
    if path and os.path.isabs(path):
        try:
            rp = os.path.realpath(path)
            rc = os.path.realpath(cwd)
            if rp == rc:
                path = ""
            elif rp.startswith(rc + os.sep):
                path = rp[len(rc) + 1:]
        except Exception:
            pass
    print(tool + "\t" + path)
except Exception:
    pass
PYEOF
)"

IFS=$'\t' read -r TOOL FILE_PATH <<< "${INFO}"

if [ -z "${FILE_PATH}" ] || [ -z "${TOOL}" ]; then
    exit 0
fi

# If still absolute at this point, the edit was outside the project — skip it.
if [[ "${FILE_PATH}" = /* ]]; then
    exit 0
fi

echo "${PAYLOAD}" | PYTHONPATH="${_PLUGIN_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" "${_PY}" -m claude_mesh notify-change "${FILE_PATH}" "${TOOL}" 2>>"${_log_dir}" || true
exit 0
