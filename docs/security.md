# Security and approvals

## Secrets

Do not commit populated `.env` files, bot tokens, OpenRouter keys, Composio keys,
Notion tokens, Orgo keys, memories, session data, Graphify indexes, or logs.
Orgo injects launch secrets only after restoring a computer; the bootstrap copies
them to the Hermes environment with mode `0600`.

Use a distinct Slack bot token, Composio entity, and least-privilege tool
connection per agent. A compromised marketing agent must not inherit developer
repository access or Ops infrastructure access. The temporary Notion integration
token belongs only to the PM-owned control-plane adapter, not every worker.
Notion does not provide the row-level worker authorization needed for the final
system; the custom backend will enforce it.

## Human approval

The `composio-approval` plugin permits conservative read actions automatically.
All unknown or state-changing Composio actions stop and ask the owner for an
inline Slack approval. Timeout, missing UI, or plugin exception fails closed.
Slack intake runs over Socket Mode: a missed event during downtime is not
replayed on reconnect, so intake completeness depends on process uptime.
Connection resets are also gated. Approval must describe the exact action;
approval is not a blanket access grant.

Agent roles with financial work never receive payment or transfer capabilities.
The Ops Provisioner is the only default Orgo-capable role; it must ask for
approval before any state-changing Orgo action. Database deletion always needs
separate explicit human authorization.

## Network and lifecycle

The Orgo template starts with an allow-list egress policy. Add domains only when
the capability pack needs them and record why. Rotate a secret by replacing it
in Orgo and restoring/reseeding the affected computer; do not put it in Git.
