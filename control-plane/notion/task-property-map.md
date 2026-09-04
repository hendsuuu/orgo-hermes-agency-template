# Task property map

| Contract field | Notion property | Type | Writer |
| --- | --- | --- | --- |
| `task_id` | Task ID | Rich text | Intake adapter |
| `title` | Title | Title | Intake adapter / PM |
| `project` | Project | Relation or select | PM |
| `status` | Status | Status | PM or assigned worker (limited transitions) |
| `priority` | Priority | Select | PM |
| `requested_by` | Requested By | Rich text | Intake adapter |
| `source` | Source | Select | Intake adapter |
| `suggested_assignee` | Suggested Assignee | Relation | Intake adapter |
| `assigned_agent` | Assigned Agent | Relation | PM only |
| `telegram.message_id` | Telegram Message | Rich text/URL | Intake adapter |
| `approval_required` | Approval Required | Checkbox | PM or approval policy |
| `parent_task_id` | Parent Task | Relation | PM |
| timestamps | Created At / Updated At | Created time / Last edited time | Notion |

An adapter carries idempotency key `telegram:<chat_id>:<message_id>` for Telegram
intake. Replaying the same update must locate the existing task rather than
creating another one.
