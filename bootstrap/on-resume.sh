#!/usr/bin/env bash
set -euo pipefail

# Orgo runs this after a computer is restored and its launch secrets are injected.
# Identity-specific setup stays explicit in seed-agent.sh, so a snapshot can never
# accidentally become a second agent with the wrong Telegram identity.
if [[ -f /opt/agency-runtime/.agent-ready ]]; then
  echo "Hermes agency identity is already seeded. Starting managed services."
else
  echo "Hermes agency base is ready; run /opt/agency/bootstrap/seed-agent.sh before enabling this agent."
fi
