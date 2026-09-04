# Review-first deployment procedure

This repository becomes an Orgo template only after it is reviewed, committed,
and pushed to its private GitHub source.

## Once the template is approved

1. Run `scripts/validate.sh`, commit the reviewed template, and push it.
2. Publish `orgo/agency-base.template.yaml` through Orgo. Its build produces a
   golden base with Hermes, the common runtime, and no agent identity.
3. For each role, create a computer from the golden template and enter the
   declared launch secrets in Orgo. Each computer needs a unique
   `TELEGRAM_BOT_TOKEN`. Only the PM/control-plane computer receives the Notion
   token and Tasks database ID; only Ops receives `ORGO_API_KEY`.
4. Using the restricted Ops/Provisioner pathway, run:

   ```bash
   /opt/agency/bootstrap/seed-agent.sh --agent-id developer-01 --role developer
   /opt/agency/bootstrap/verify-agent.sh
   ```

5. Only after verification succeeds, allow the supervised Hermes gateway to
   start. Add the bot to the agency Telegram group and test one PM-assigned task.

The seed step happens after Orgo restores the base and injects secrets. This is
important: credentials and an individual bot identity never enter the golden
snapshot.

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
