#!/bin/bash
# hooks-grok/post_tool_use_edit.sh
# Grok Build PostToolUse -> claude-mesh notify-change
#
# PostToolUse is passive in Grok (stdout ignored), which is fine: publishing
# needs no return value. Always exits 0 — hooks never block a turn.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"

PAYLOAD="$(cat)"

# Grok's envelope is camelCase and its edit tools carry the path under
# assorted keys depending on the tool, so probe all the plausible ones.
INFO="$(PAYLOAD="${PAYLOAD}" PWD_FALLBACK="${PWD}" "${_PY}" - <<'PYEOF'
import json, os
try:
    d = json.loads(os.environ["PAYLOAD"])
    # camelCase first (grok), snake_case fallback (claude/SDK-normalized)
    tool = d.get("toolName") or d.get("tool_name") or d.get("tool") or ""
    inp = d.get("toolInput") or d.get("tool_input") or {}
    if not isinstance(inp, dict):
        inp = {}
    path = ""
    for key in (
        "file_path", "filePath", "path", "target_file", "targetFile",
        "notebook_path", "notebookPath",
    ):
        v = inp.get(key)
        if isinstance(v, str) and v:
            path = v
            break
    # Prefer the workspace root so paths are stable regardless of the
    # subdirectory a tool happened to run in.
    base = (
        d.get("workspaceRoot")
        or d.get("cwd")
        or os.environ.get("PWD_FALLBACK", "")
        or os.getcwd()
    )
    if path and os.path.isabs(path):
        try:
            rp = os.path.realpath(path)
            rc = os.path.realpath(base)
            if rp == rc:
                path = ""
            elif rp.startswith(rc + os.sep):
                path = rp[len(rc) + 1:]
        except Exception:
            pass
    print(tool + "\t" + path + "\t" + (base or ""))
except Exception:
    pass
PYEOF
)"

IFS=$'\t' read -r TOOL FILE_PATH BASE_DIR <<< "${INFO}"

[ -z "${FILE_PATH:-}" ] && exit 0
[ -z "${TOOL:-}" ] && exit 0

# Still absolute means the edit landed outside the project — not our business.
case "${FILE_PATH}" in
    /*) exit 0 ;;
esac

# Only these tools mutate files. The `matcher` in settings.json should filter
# too, but re-check here so a broad registration can't publish noise.
case "${TOOL}" in
    search_replace|write_file|create_file|edit_file|apply_patch|str_replace|multi_edit|Edit|Write|NotebookEdit) ;;
    *) exit 0 ;;
esac

# Run from the workspace root so `.claude-mesh` discovery walks the right tree.
if [ -n "${BASE_DIR:-}" ] && [ -d "${BASE_DIR}" ]; then
    cd "${BASE_DIR}" || exit 0
fi

run_mesh notify-change "${FILE_PATH}" "${TOOL}"
exit 0
