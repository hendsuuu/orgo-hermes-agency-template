#!/usr/bin/env bash
set -euo pipefail

[[ -f /opt/agency-runtime/.agent-ready ]] || { echo "Agent is not seeded" >&2; exit 1; }
set -a
source /root/.env
source /root/.hermes/.env
set +a

HERMES=/root/.hermes/hermes-agent/venv/bin/hermes
PYTHON=/root/.hermes/hermes-agent/venv/bin/python

"$HERMES" --version
"$HERMES" memory status
"$PYTHON" -c 'import composio, graphifyy; print("Composio and Graphify runtime imports: OK")'
"$PYTHON" -c 'import slack_sdk; print("Slack runtime import: OK")'

if [[ -n "${COMPOSIO_MCP_URL:-}" ]]; then
  echo "Composio MCP endpoint is configured. Connection/action tests require an approved task."
fi
echo "Static agent verification passed."
