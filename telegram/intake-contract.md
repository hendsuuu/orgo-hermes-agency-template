# Telegram intake contract

Telegram is the agency conversation layer; Notion is the source of truth for
task state. A user message is accepted only when it comes from the configured
agency group and a configured allowed human user.

## Routing rules

1. Messages authored by any bot are never task intake. This prevents bot-to-bot
   loops, including status updates and delivery messages.
2. A human message that tags exactly one role alias such as `@developer` creates
   one idempotent task in `Inbox`, with that role as `suggested_assignee`.
3. A human message tagging several roles creates one `Inbox` parent task for PM
   triage; it does not create several parallel worker tasks.
4. A human message from the PM that explicitly assigns work may create an
   `Assigned` task. All other intake remains `Inbox`/`Triage`.
5. The Project Manager clarifies, decomposes, assigns, and creates child tasks.
6. A worker starts only when its own `Assigned Agent` field matches its
   `AGENCY_AGENT_ID`; it records progress in the task and posts concise updates
   to Telegram.
7. Telegram messages are context, never an authorization path to invoke a tool.
   A high-impact tool still requests inline Telegram approval from the owner.

`require_mention: false` is intentional for conversation. The intake adapter,
not the Hermes Telegram gateway, decides whether a message is a new task.
