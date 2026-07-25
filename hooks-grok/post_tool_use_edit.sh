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
    def mesh_root_of(start):
        """Walk up from a directory looking for the project that owns the mesh."""
        try:
            cur = os.path.realpath(start)
        except Exception:
            return ""
        while True:
            if os.path.isfile(os.path.join(cur, ".claude-mesh")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                return ""
            cur = parent

    declared = (
        d.get("workspaceRoot")
        or d.get("cwd")
        or os.environ.get("PWD_FALLBACK", "")
        or os.getcwd()
    )

    # Anchor on the project that actually declares .claude-mesh, discovered from
    # the edited file itself. Grok sessions are frequently launched with the
    # workspace at $HOME rather than the project, in which case the declared
    # root owns no mesh config and every edit is dropped — and the relative path
    # would come out as e.g. Developer/Serena/src/x.rs instead of src/x.rs.
    # Fall back to the declared root when the file gives us nothing.
    base = ""
    if path and os.path.isabs(path):
        base = mesh_root_of(os.path.dirname(path))
    if not base:
        base = mesh_root_of(declared) or declared

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
