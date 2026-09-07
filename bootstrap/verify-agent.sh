#!/usr/bin/env bash
set -euo pipefail

[[ -f /opt/agency-runtime/.agent-ready ]] || { echo "Agent is not seeded" >&2; exit 1; }
set -a
source /root/.env
source /root/.hermes/.env
set +a

HERMES=/usr/local/lib/hermes-agent/venv/bin/hermes

"$HERMES" --version
"$HERMES" memory status
"$HERMES" gateway list >/dev/null && echo "Slack gateway runtime: OK"
/opt/agency-runtime/bin/python -c 'import composio, graphifyy, slack_sdk; print("Composio, Graphify, and Slack runtime imports: OK")'

if [[ -n "${COMPOSIO_MCP_URL:-}" ]]; then
  echo "Composio MCP endpoint is configured. Connection/action tests require an approved task."
fi
echo "Static agent verification passed."
