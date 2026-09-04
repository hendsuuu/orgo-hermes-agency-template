# Notion Kanban: initial control plane

Notion is the shared task authority during the first phase. Hermes computers do
not use their local SQLite stores as a shared task board: each computer is
isolated, so a local database would create conflicting copies of the truth.

Create one agency workspace with these databases:

| Database | Purpose | Minimum properties |
| --- | --- | --- |
| Tasks | Work queue and audit trail | Task ID, Title, Project, Status, Priority, Assigned Agent, Suggested Assignee, Source, Requested By, Telegram Message, Approval Required, Parent Task, Created At, Updated At |
| Projects | Portfolio and objectives | Project, Owner, Status, Objective, Target Date |
| Agents | Fleet directory | Agent ID, Role, Computer ID, Telegram Bot, Availability, Current Task, Capability Pack |

`Status` must use this exact order: `Inbox`, `Triage`, `Assigned`, `In Progress`,
`Blocked`, `Review`, `Done`, `Cancelled`.

Only the Project Manager changes a task from `Triage` to `Assigned`; a worker
may update only its own assigned task to `In Progress`, `Blocked`, `Review`, or
`Done`. The Notion adapter must reject direct worker writes to assignment fields.

Run a single serialized adapter/queue under the Project Manager (or as a
separate control-plane service) for all Notion writes and poll changes at 60
seconds or slower. Worker computers do not receive the Notion token; they use
the adapter's task interface. This keeps the early fleet beneath Notion's
published request limits while retaining an idempotent task audit trail.

The required property mapping appears in [task-property-map.md](task-property-map.md).
