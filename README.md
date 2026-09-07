# Orgo Hermes Agency Template

Portable foundation for an AI agency where one Orgo computer runs exactly one
Hermes identity. The initial shared Kanban authority is Notion; the agent-facing
task contract is deliberately provider-neutral so it can move to a custom
Postgres backend later.

## Non-negotiable operating model

1. A Slack message is never delivered straight to a worker session.
2. A PM assignment or a human `@agent` tag creates a task record first.
3. Only a PM can move a task from `triage` to `assigned`.
4. Workers only execute tasks assigned to their own `agent_id`.
5. Bot-authored Slack messages are never ingested as new work.

## Repository layout

| Path | Purpose |
|---|---|
| `orgo/` | Orgo golden-image manifest and launch notes. |
| `bootstrap/` | Idempotent per-computer setup, service launcher, verification. |
| `config/` | Secret-free Hermes and environment templates. |
| `roles/` | Role packs for each one-agent computer. |
| `plugins/agency-task/` | Hermes plugin contract and task-entry guardrails. |
| `control-plane/` | Notion schema, backend-neutral task contract, and the `adapter/` runtime (intake, HTTP task interface, worker poller, lease reaper). See `docs/control-plane-runtime.md`. |
| `slack/` | Channel routing and intake policy. |
| `docs/capability-packs.md` | Base runtime, tool boundaries, and role scopes. |

## Deploy sequence

1. Review and push this repository privately.
2. Validate and publish the Orgo template. It contains no credentials.
3. Create one Orgo computer per role from the same template.
4. Inject launch secrets through the Orgo vault.
5. Use the Orgo MCP only to run `seed-agent.sh --role <role>` on a new
   computer, then complete its Notion/Slack registration.
6. Run `verify-agent.sh` before marking that agent ready in Notion.

See `docs/deployment.md`, `docs/security.md`, and
`control-plane/notion/README.md` before deployment.
