# archolith-audit WSL plugin verification

Use this before a full VM. It verifies the standalone plugin repos in a clean Linux home
without depending on the source checkout.

## Preconditions

- WSL distro installed, preferably Ubuntu 24.04.
- `git`, Python 3.11+, and Node.js available inside WSL.
- Optional live-agent CLIs installed/authenticated for full runtime checks.

## Clean smoke check

Run from PowerShell:

```powershell
wsl.exe bash -lc '
set -euo pipefail
ROOT="$(mktemp -d)"
export HOME="$ROOT/home"
mkdir -p "$HOME"
cd "$ROOT"
PYTHON_BIN="${PYTHON_BIN:-python3}"

for repo in \
  archolith-audit-plugin-claude \
  archolith-audit-plugin-codex \
  archolith-audit-plugin-gemini \
  archolith-audit-plugin-opencode
do
  git clone "https://github.com/Archolith/$repo.git"
done

for repo in archolith-audit-plugin-*; do
  cd "$ROOT/$repo"
  "$PYTHON_BIN" -m venv .venv
  . .venv/bin/activate
  python -m pip install -q -r requirements.txt
  python - <<PY
import archolith_mcp_audit
from archolith_mcp_audit.telemetry_bridge import FileTelemetrySource
print("import ok", archolith_mcp_audit.__name__)
PY
  deactivate
  test -f LICENSE
  test -f THIRD-PARTY-LICENSES.md
  test -f requirements.txt
done

cd "$ROOT/archolith-audit-plugin-codex"
printf "%s\n" "{\"tool_name\":\"mcp__demo__status\",\"tool_result\":\"ok\",\"session_id\":\"wsl-smoke\"}" \
  | .venv/bin/python hook_observer_codex.py
test -s "$HOME/.archolith/sessions/wsl-smoke.jsonl"

cd "$ROOT/archolith-audit-plugin-gemini"
printf "%s\n" "{\"tool_name\":\"mcp__demo__status\",\"tool_result\":\"ok\",\"session_id\":\"wsl-smoke\"}" \
  | node hooks/after-tool.js

echo "WSL plugin smoke passed at $ROOT"
'
```

## Acceptance

- All four public repos clone from GitHub.
- Each repo declares Python runtime dependencies in `requirements.txt`.
- Bundled `archolith_mcp_audit` imports from a clean venv without editable install.
- Each bundle has `LICENSE` and `THIRD-PARTY-LICENSES.md`.
- Hook smoke writes a non-empty file under `~/.archolith/sessions/`.

## Full runtime check

After smoke passes, run `.agent/workflows/plugin_runtime_verification.md` inside WSL for any
agent CLI that is installed and authenticated there.
