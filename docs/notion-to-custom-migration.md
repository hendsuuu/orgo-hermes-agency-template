# Notion to custom Kanban migration

The portable `AgencyTask` contract in `control-plane/contracts/task.schema.json`
is the integration boundary. The Telegram intake and every worker should depend
on that contract, not on Notion property names.

## Phase 1 — Notion

Use Notion Tasks as the source of truth. A single adapter serializes writes,
maps fields using `control-plane/notion/task-property-map.md`, and polls changes
at a conservative interval. This is appropriate while the team needs visibility
more than high-volume automation.

## Phase 2 — custom control plane

Build a small service with PostgreSQL, an append-only task event table, an API,
and a dashboard. Keep task IDs and state transitions identical. The custom
adapter becomes authoritative; Notion receives a one-way mirrored project view
for human planning and documents.

## Phase 3 — operational hardening

Add agent leases, retries, dead-letter handling, rate limiting, audit events,
and per-project permissions. Workers still use the same task contract, so their
Hermes role templates do not need to be redesigned.
