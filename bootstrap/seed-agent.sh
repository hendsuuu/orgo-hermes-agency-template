#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 --agent-id <id> --role <role> [--model <openrouter-model>]" >&2
  exit 64
}

AGENT_ID=
ROLE=
MODEL=
while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent-id) AGENT_ID=${2:-}; shift 2 ;;
    --role) ROLE=${2:-}; shift 2 ;;
    --model) MODEL=${2:-}; shift 2 ;;
    *) usage ;;
  esac
done
[[ -n "$AGENT_ID" && -n "$ROLE" ]] || usage

ROLE_FILE="/opt/agency/roles/${ROLE}.md"
[[ -f "$ROLE_FILE" ]] || { echo "Unknown role: $ROLE" >&2; exit 65; }
[[ -f /root/.env ]] || { echo "Missing Orgo secret environment at /root/.env" >&2; exit 66; }

set -a
source /root/.env
set +a
for key in OPENROUTER_API_KEY SLACK_BOT_TOKEN SLACK_APP_TOKEN SLACK_CHANNEL_ID COMPOSIO_API_KEY COMPOSIO_MCP_URL; do
  [[ -n "${!key:-}" ]] || { echo "Required launch secret is absent: $key" >&2; exit 67; }
done
if [[ "$ROLE" == "project-manager" ]]; then
  for key in NOTION_API_KEY NOTION_TASKS_DATABASE_ID; do
    [[ -n "${!key:-}" ]] || { echo "Project Manager requires: $key" >&2; exit 67; }
  done
fi
if [[ "$ROLE" == "ops-provisioner" && -z "${ORGO_API_KEY:-}" ]]; then
  echo "Ops Provisioner requires ORGO_API_KEY" >&2
  exit 67
fi

# Resolve the model: explicit --model wins, then AGENCY_MODEL, then the per-role
# default from config/model-routing.map, then a conservative fallback.
if [[ -z "$MODEL" ]]; then
  MODEL="${AGENCY_MODEL:-}"
fi
if [[ -z "$MODEL" ]]; then
  MAP=/opt/agency/config/model-routing.map
  if [[ -f "$MAP" ]]; then
    MODEL=$(grep -E "^${ROLE}=" "$MAP" | head -1 | cut -d= -f2-)
    [[ -n "$MODEL" ]] || MODEL=$(grep -E "^default=" "$MAP" | head -1 | cut -d= -f2-)
  fi
fi
if [[ -z "$MODEL" ]]; then
  MODEL="deepseek/deepseek-v4-flash-0731"
fi

install -d -m 700 /root/.hermes /root/.hermes/plugins /root/.hermes/skills /opt/agency-runtime
cp /root/.env /root/.hermes/.env
chmod 600 /root/.hermes/.env

cp -R /opt/agency/plugins/agency-task /root/.hermes/plugins/
cp -R /opt/agency/plugins/composio-approval /root/.hermes/plugins/
cp "$ROLE_FILE" "/root/.hermes/SOUL-${ROLE}.md"

export AGENCY_AGENT_ID="$AGENT_ID"
export AGENCY_ROLE="$ROLE"
export AGENCY_MODEL="$MODEL"
export AGENCY_TASK_BACKEND="${AGENCY_TASK_BACKEND:-notion}"

/usr/local/lib/hermes-agent/venv/bin/python - <<'PY'
import os
from pathlib import Path

source = Path('/opt/agency/config/config.template.yaml').read_text()
for key, value in os.environ.items():
    source = source.replace('${' + key + '}', value)
Path('/root/.hermes/config.yaml').write_text(source)
PY

printf 'agent_id=%s\nrole=%s\nmodel=%s\nseeded_at=%s\n' \
  "$AGENT_ID" "$ROLE" "$MODEL" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  > /opt/agency-runtime/.agent-ready
chmod 600 /opt/agency-runtime/.agent-ready

echo "Seeded ${AGENT_ID} as ${ROLE}. Run /opt/agency/bootstrap/verify-agent.sh before enabling work."
