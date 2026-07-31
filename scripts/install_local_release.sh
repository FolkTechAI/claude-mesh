#!/usr/bin/env bash
# Install the exact validated checkout for the global CLI and new Claude/Grok sessions.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${MESH_PYTHON_BIN:-/opt/homebrew/bin/python3.11}"
VERSION="$(
  PYTHONPATH="${ROOT}/src" "${PYTHON_BIN}" -c \
    'from claude_mesh import __version__; print(__version__)'
)"
CLAUDE_CACHE_ROOT="${HOME}/.claude/plugins/cache/folktechai/claude-mesh"
CLAUDE_TARGET="${CLAUDE_CACHE_ROOT}/${VERSION}"
INSTALLED_PLUGINS="${HOME}/.claude/plugins/installed_plugins.json"
STAGE="$(mktemp -d /tmp/folktech-mesh-install.XXXXXX)"

cleanup() {
  rm -rf "${STAGE}"
}
trap cleanup EXIT

if [ ! -x "${PYTHON_BIN}" ]; then
  echo "error: Python not executable: ${PYTHON_BIN}" >&2
  exit 1
fi
if [ ! -f "${INSTALLED_PLUGINS}" ]; then
  echo "error: Claude installed plugin registry not found: ${INSTALLED_PLUGINS}" >&2
  exit 1
fi

echo "Building FolkTech Mesh ${VERSION}..."
"${PYTHON_BIN}" -m pip wheel \
  "${ROOT}" --no-deps --no-build-isolation --wheel-dir "${STAGE}/wheel" >/dev/null
WHEEL="$(find "${STAGE}/wheel" -maxdepth 1 -name '*.whl' -print -quit)"
if [ -z "${WHEEL}" ]; then
  echo "error: wheel build produced no artifact" >&2
  exit 1
fi

echo "Installing global CLI from ${WHEEL}..."
"${PYTHON_BIN}" -m pip install --no-deps --force-reinstall "${WHEEL}" >/dev/null

echo "Staging Claude adapter..."
PLUGIN_STAGE="${STAGE}/plugin"
mkdir -p "${PLUGIN_STAGE}"
for item in .claude-plugin commands hooks src LICENSE README.md CHANGELOG.md pyproject.toml; do
  cp -R "${ROOT}/${item}" "${PLUGIN_STAGE}/"
done
find "${PLUGIN_STAGE}" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "${PLUGIN_STAGE}" -name '*.pyc' -type f -delete

mkdir -p "${CLAUDE_CACHE_ROOT}"
if [ -e "${CLAUDE_TARGET}" ]; then
  BACKUP_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  PLUGIN_BACKUP_ROOT="${HOME}/.claude/plugins/backups/claude-mesh"
  PLUGIN_BACKUP="${PLUGIN_BACKUP_ROOT}/${BACKUP_STAMP}-${VERSION}"
  mkdir -p "${PLUGIN_BACKUP_ROOT}"
  mv "${CLAUDE_TARGET}" "${PLUGIN_BACKUP}"
  echo "Backed up previous Claude adapter to ${PLUGIN_BACKUP}"
fi
mv "${PLUGIN_STAGE}" "${CLAUDE_TARGET}"
chmod -R go-w "${CLAUDE_TARGET}"

REGISTRY_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REGISTRY_BACKUP="${INSTALLED_PLUGINS}.before-mesh-${VERSION}-${REGISTRY_STAMP}"
cp "${INSTALLED_PLUGINS}" "${REGISTRY_BACKUP}"
INSTALL_PATH="${CLAUDE_TARGET}" VERSION="${VERSION}" REGISTRY="${INSTALLED_PLUGINS}" \
  "${PYTHON_BIN}" - <<'PY'
import datetime
import json
import os
from pathlib import Path

path = Path(os.environ["REGISTRY"])
data = json.loads(path.read_text(encoding="utf-8"))
entries = data.get("plugins", {}).get("claude-mesh@folktechai")
if not isinstance(entries, list) or not entries:
    raise SystemExit("claude-mesh@folktechai is not installed")
entry = entries[0]
entry["installPath"] = os.environ["INSTALL_PATH"]
entry["version"] = os.environ["VERSION"]
entry["lastUpdated"] = (
    datetime.datetime.now(datetime.timezone.utc)
    .isoformat(timespec="milliseconds")
    .replace("+00:00", "Z")
)
entry.pop("gitCommitSha", None)
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
os.replace(tmp, path)
PY

echo "Refreshing Grok adapter..."
"${ROOT}/scripts/install_grok_adapter.sh" >/dev/null

echo "Installed FolkTech Mesh ${VERSION}:"
echo "  CLI: $("${PYTHON_BIN}" -m claude_mesh --version)"
echo "  Claude: ${CLAUDE_TARGET}"
echo "  Grok: ${HOME}/.grok/hooks/claude-mesh.json"
echo "  Registry backup: ${REGISTRY_BACKUP}"
echo "Restart Claude and Grok sessions to load the new adapter."
