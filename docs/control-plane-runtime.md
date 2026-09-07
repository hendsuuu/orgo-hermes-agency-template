# Control-plane runtime (intake adapter + worker poller)

This is the phase-1 transport that makes the fleet actually move work. It lives
in `control-plane/adapter/` and is pure, deterministic, non-LLM code. A language
model is spent only inside the worker **executor**, when a claimed task is worked.

## What runs where

Two managed services run on every computer (see `orgo/agency-base.template.yaml`):

| Service | Script | Job |
|---|---|---|
| `hermes-gateway` | `bootstrap/start-gateway.sh` | Hermes Slack conversation runtime |
| `agency-runtime` | `bootstrap/start-agency-runtime.sh` | picks its job from the seeded role |

`agency-runtime` branches on role:

- **project-manager** → runs `adapter.cli serve`: the HTTP task interface, the
  Slack intake loop, and the lease reaper. This is the only computer that
  holds the Notion token.
- **every other role** → runs `adapter.cli poll`: the worker transport loop. It
  talks only to the control-plane over HTTP and never sees the Notion token.

## Flow

```
Slack (allowed human) ──► intake.classify ──► backend.create (Inbox)
                                                      │
PM triages + assigns (admin endpoints / /assign) ────┤ status: Assigned, Assigned Agent ID
                                                      ▼
worker poller ──► POST /tasks/{id}/lease ──► In Progress (+lease)
        │                                         │  heartbeat renews lease
        ▼                                         ▼
   executor.run (Hermes, the only token spend)   reaper reclaims expired leases → Blocked
        │
        ▼
POST /tasks/{id}/status  ──►  Review (result_ref, tokens_used)  or  Blocked (note)
```

## HTTP interface

Worker endpoints (bearer = `AGENCY_CONTROL_PLANE_TOKEN`, header `X-Agent-Id`):

- `GET  /tasks/assigned` — this worker's Assigned + own In Progress tasks.
- `POST /tasks/{id}/lease` — claim/renew a lease; Assigned → In Progress.
- `POST /tasks/{id}/heartbeat` — extend the lease while working.
- `POST /tasks/{id}/status` — worker-legal transition (`{status, result_ref?, tokens_used?}`).

PM/admin endpoints (bearer = `AGENCY_PM_TOKEN`, falls back to control-plane token):

- `POST /admin/tasks` — create a task.
- `POST /admin/tasks/{id}/assign` — Triage → Assigned + set Assigned Agent ID.
- `POST /admin/tasks/{id}/transition` — any PM-legal transition.
- `GET  /admin/tasks?status=triage,assigned` — list for triage tooling.

The service enforces the operating model in code: a worker can act only on its
own task and only through the worker transition table in
`control-plane/adapter/contract.py`; assignment fields are PM-only.

## PM triage in phase 1

The PM moves work from Triage to Assigned through the admin endpoints — from a
small PM tool, a script, or a `/assign <agent-id> <title>` Slack message from
a configured `SLACK_PM_USER_IDS` user. Autonomous LLM triage by the PM agent
is a later phase; the seam (admin endpoints) is already in place for it.

## Cost meter

Workers report `tokens_used` on completion; it is stored on the task
(`Tokens Used`). Sum it per agent/project for a first spend view. For richer
per-request cost, put OpenRouter behind Helicone and set the workers'
`OPENROUTER_BASE_URL` to the Helicone gateway — no code change here.

## Executor wiring (the one integration point)

`AGENCY_EXECUTOR_CMD` must run your Hermes build headless on one task. It receives
`AGENCY_TASK_ID`, `AGENCY_TASK_FILE` (task JSON), and `AGENCY_TASK_BRIEF` (also on
stdin), and should print a final JSON line `{"result_ref": "...", "tokens_used": N}`.
If it prints none, stdout is saved to a file and used as the result reference.
Keep `AGENCY_LEASE_TTL` larger than the longest task run (the heartbeat renews,
but give headroom).

## Phase 2

Swap `NotionTaskBackend` for a Postgres backend implementing the same
`TaskBackend` interface. Workers, intake, contract, and the HTTP interface are
unchanged — that is the point of the seam.
