# Agency architecture

```text
Human in Slack channel
        │  tag / PM assignment
        ▼
Slack intake adapter ── idempotent create ──► Notion Tasks (authority)
                                                     │
                                    PM triage + assignment only
                                                     │
      ┌──────────────────────────────┬──────────────┴──────────────┐
      ▼                              ▼                             ▼
Orgo computer: CEO              Orgo computer: Developer     Orgo computer: Marketing
Hermes + private memory         Hermes + Graphify             Hermes + private memory
Honcho + Composio               Honcho + Composio             Honcho + Composio
      │                              │                             │
      └──── concise status / result back to Slack + task record ┘
```

Each computer owns exactly one Hermes profile and one Slack bot token. This
prevents identity, tool credential, and private-memory leakage between roles.
All fleet coordination travels through the task contract, rather than invisible
prompt-to-prompt delegation.

## Trust boundaries

| Boundary | Rule |
| --- | --- |
| Slack | Human conversation, intake, delivery, and approval surface—not shared state authority. |
| Notion | Initial shared task authority; one serialized adapter owns writes. |
| Hermes computer | One role; local filesystem and Graphify index are private to that agent. |
| Honcho | Per-agent private namespace by default; PM/CEO explicitly promotes durable shared knowledge. |
| Composio | Separate entity/connection scope per agent; writes require inline Slack approval. |
| Orgo MCP | Held only by Ops Provisioner/CEO; all mutations require approval. |

## Models

The template connects Hermes directly to OpenRouter. A role gets its model from
`AGENCY_MODEL` at seed time. That removes 9router from the intended fleet while
allowing a chosen OpenRouter model slug to change without rebuilding the golden
template.
