#!/usr/bin/env bash
set -euo pipefail

READY_FILE=/opt/agency-runtime/.agent-ready
if [[ ! -f "$READY_FILE" ]]; then
  echo "Agent has not been seeded; gateway will remain stopped." >&2
  exit 1
fi

# Orgo injects secrets into /root/.env. Hermes itself reads its config from
# /root/.hermes/.env, which seed-agent.sh creates with restricted permissions.
set -a
source /root/.env
source /root/.hermes/.env
set +a

exec /root/.hermes/hermes-agent/venv/bin/hermes gateway run
