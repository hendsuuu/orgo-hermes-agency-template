# Common runtime and role capability packs

Every computer begins with the same base image. Role differentiation comes from
the SOUL file, separate secrets, Composio entity/tool scopes, and explicit
capability packs—not a different copy of Hermes.

| Component | Base template behavior | Scope |
| --- | --- | --- |
| Hermes | Gateway and Telegram conversation runtime | one profile per computer |
| OpenRouter | Direct native provider through `OPENROUTER_API_KEY` | model selected per seeded agent |
| Honcho | Agent-private long-term memory namespace | private; curated promotion only |
| Graphify | Local code/project intelligence runtime | developer by default; per-workspace index |
| Composio | Connected tool bridge | distinct entity and least-privilege connections |
| `agency-task` | Shared task contract instructions | every role |
| `composio-approval` | Inline Telegram approval for writes | every role with Composio |
| Notion adapter | Shared Kanban transport | PM/intake is authoritative |

Suggested initial scopes:

| Role | Additions | Explicit exclusions |
| --- | --- | --- |
| CEO | project visibility, approval surface | no routine repo or infrastructure write |
| Project Manager | task-board write and all project visibility | no direct worker execution |
| Developer | Graphify, approved GitHub/tool access | no Orgo credential by default |
| Marketing / Content | approved marketing and publishing connectors | publishing remains approval-gated |
| Accountant | reporting data connectors | payments/transfers always excluded |
| Researcher | browser/research tools | external mutation excluded |
| Ops Provisioner | Orgo MCP | only approval-gated infrastructure mutation |

New skills belong in a versioned `skills/<name>/` directory in this template,
with installation and role eligibility documented beside the skill. Do not copy
private Hermes sessions, downloaded memories, or user-specific skill settings
into the repository.
