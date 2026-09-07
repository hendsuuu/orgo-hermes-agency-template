# Review-first deployment procedure

This repository becomes an Orgo template only after it is reviewed, committed,
and pushed to its private GitHub source.

## Once the template is approved

1. Run `scripts/validate.sh`, commit the reviewed template, and push it.
2. Publish `orgo/agency-base.template.yaml` through Orgo. Its build produces a
   golden base with Hermes, the common runtime, and no agent identity.
3. For each role, create a computer from the golden template and enter the
   declared launch secrets in Orgo. Each computer needs a unique
   `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`. Only the PM/control-plane computer receives the Notion
   token and Tasks database ID; only Ops receives `ORGO_API_KEY`.
4. Using the restricted Ops/Provisioner pathway, run:

   ```bash
   /opt/agency/bootstrap/seed-agent.sh --agent-id developer-01 --role developer
   /opt/agency/bootstrap/verify-agent.sh
   ```

5. Only after verification succeeds, allow the supervised Hermes gateway to
   start. Add the bot to the agency Slack channel and test one PM-assigned task.

The seed step happens after Orgo restores the base and injects secrets. This is
important: credentials and an individual bot identity never enter the golden
snapshot.

## Control-plane wiring (task transport)

The `agency-runtime` service starts automatically beside the Hermes gateway and
picks its job from the seeded role (see `docs/control-plane-runtime.md`). Set
these launch secrets so it can run:

- **Every computer:** `AGENCY_CONTROL_PLANE_TOKEN` (shared bearer).
- **PM / control-plane computer only:** `NOTION_API_KEY`, `NOTION_TASKS_DATABASE_ID`,
  and optionally `AGENCY_PM_TOKEN` and `SLACK_PM_USER_IDS`.
- **Worker computers only:** `AGENCY_CONTROL_PLANE_URL` (the PM service's reachable
  URL) and `AGENCY_EXECUTOR_CMD` (your headless Hermes task command). Add the
  control-plane host to the template `egress_policy` so workers can reach it.

Create the Notion Tasks properties exactly as listed in
`control-plane/notion/task-property-map.md` before starting the PM service; the
adapter reads and writes those property names.

## Role-to-computer starting fleet

| Computer / agent ID | Role | Special capability |
| --- | --- | --- |
| `ceo-01` | CEO | policy and strategic approvals |
| `pm-01` | Project Manager | sole task dispatcher |
| `developer-01` | Developer | Graphify and approved repository tooling |
| `marketing-01` | Marketing | approved marketing connections |
| `content-01` | Content Creator | approved content workflows |
| `accountant-01` | Accountant | read/report only financial controls |
| `researcher-01` | Researcher | research workflow |
| `ops-01` | Ops Provisioner | approved Orgo MCP operations only |
