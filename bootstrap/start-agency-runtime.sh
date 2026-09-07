#!/usr/bin/env bash
set -euo pipefail

# Second managed service on every computer. It selects its job from the seeded
# role: the Project Manager computer runs the control-plane (HTTP task interface
# + Slack intake + lease reaper); every other role runs the worker poller.
#
# This is separate from start-gateway.sh (the Hermes conversation gateway) so
# task transport and conversation fail and restart independently.

READY_FILE=/opt/agency-runtime/.agent-ready
[[ -f "$READY_FILE" ]] || { echo "Agent is not seeded; agency runtime stays stopped." >&2; exit 1; }

set -a
source /root/.env
source /root/.hermes/.env
set +a

ROLE=$(sed -n 's/^role=//p' "$READY_FILE")
PYTHON=/opt/agency-runtime/bin/python
cd /opt/agency/control-plane

if [[ "$ROLE" == "project-manager" ]]; then
  echo "[agency-runtime] starting control-plane (serve)"
  exec "$PYTHON" -m adapter.cli serve
fi

if [[ -z "${AGENCY_CONTROL_PLANE_URL:-}" || -z "${AGENCY_CONTROL_PLANE_TOKEN:-}" ]]; then
  echo "[agency-runtime] worker role '$ROLE' needs AGENCY_CONTROL_PLANE_URL and AGENCY_CONTROL_PLANE_TOKEN" >&2
  exit 1
fi
if [[ -z "${AGENCY_EXECUTOR_CMD:-}" ]]; then
  echo "[agency-runtime] AGENCY_EXECUTOR_CMD is not set; refusing to start a poller that cannot execute work" >&2
  exit 1
fi

echo "[agency-runtime] starting worker poller for role '$ROLE'"
exec "$PYTHON" -m adapter.cli poll
