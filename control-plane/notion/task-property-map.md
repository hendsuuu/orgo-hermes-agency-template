# Task property map

The adapter (`control-plane/adapter/notion_backend.py`) reads and writes the
machine properties in the table below. Human-facing **relation** properties
(Assigned Agent, Suggested Assignee, Parent Task, Project) may be kept alongside
for planning views; the adapter does not depend on them, so the fleet needs no
per-agent Notion page IDs to run. Keep property names exactly as written here.

| Contract field | Notion property | Type | Writer |
| --- | --- | --- | --- |
| `task_id` | Task ID | Rich text | Intake adapter |
| `title` | Title | Title | Intake adapter / PM |
| `project` | Project | Select | PM |
| `status` | Status | Status | PM or assigned worker (limited transitions) |
| `priority` | Priority | Select | PM |
| `requested_by` | Requested By | Rich text | Intake adapter |
| `source` | Source | Select | Intake adapter |
| `suggested_assignee` | Suggested Assignee ID | Rich text | Intake adapter |
| `assigned_agent` | Assigned Agent ID | Rich text | PM / control-plane only |
| `parent_task_id` | Parent Task ID | Rich text | PM |
| `description` | Description | Rich text | Intake / worker |
| `acceptance_criteria` | Acceptance Criteria | Rich text (newline list) | PM |
| `approval_required` | Approval Required | Checkbox | PM or approval policy |
| `result_ref` | Result Ref | Rich text | Assigned worker |
| `tokens_used` | Tokens Used | Number | Assigned worker (cost meter) |
| `telegram` | Telegram Message | Rich text (`chat_id:message_id`) | Intake adapter |
| `idempotency_key` | Idempotency Key | Rich text | Intake adapter |
| `lease.owner` | Lease Owner | Rich text | control-plane |
| `lease.expires_at` | Lease Expires | Date | control-plane |
| timestamps | Created At / Updated At | Created time / Last edited time | Notion (auto) |

`Status` options must be exactly, in order: `Inbox`, `Triage`, `Assigned`,
`In Progress`, `Blocked`, `Review`, `Done`, `Cancelled`.

The adapter carries idempotency key `telegram:<chat_id>:<message_id>` for Telegram
intake and derives a deterministic `Task ID` from it, so replaying the same
update locates the existing task rather than creating another one.
