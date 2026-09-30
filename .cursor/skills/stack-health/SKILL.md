---
name: stack-health
description: >-
  Reports health for the resources a Terraform stack owns and explains anything
  that is wrong. Use when the user asks how the stack is doing, how resources
  are doing, about stack health, or whether a deploy broke anything.
---

# Stack health

Read-only. Never run `terraform apply` or `terraform destroy`. Never change AWS resources. Only investigate resources returned by `get_stack_health`.

Use the `tfstate-health` MCP tools. Pass `env` as `demo` unless the user names another environment. The state key for this repo does not change with `env`.

## Workflow

1. Call `last_apply_info`, then `get_stack_health` (default `since_minutes` 60).
2. `unknown` means no checker for that type, or that one AWS call failed. It does not by itself make the stack unhealthy.
3. If there is no `warn` or `error`, give the short green report and stop. Do not call CloudWatch.
4. For `warn` and `error` resources only, investigate with the `awslabs-cloudwatch` MCP:
   - Alarm named in the reason: `get_alarm_history` for that alarm.
   - Lambda: `analyze_log_group` on `/aws/lambda/{id}` for the same window. Use `execute_log_insights_query` only if the analysis does not name the error.
   - Do not query log groups, metrics, or alarms for resources that are not in the state report.
5. Compare failure timestamps with `last_modified`. If the problem started after that time, say it started after the last apply.

## Report

The report is a canvas, not a markdown table in chat. Read the canvas skill and follow it, including its file location, imports, and design rules. Write `{env}-stack-health.canvas.tsx`. Embed the data inline.

The chat reply is one sentence: the verdict, then a markdown link to that canvas. Do not paste the resource table in chat.

Verdict tone: `danger` if any `error`, otherwise `warning` if any `warn`, otherwise `success`. No emoji.

Layout, top to bottom:

1. Title and a caption: environment, snapshot time, CloudWatch window, `last_modified`, and serial.
2. One callout in the verdict tone. Name each `warn` and `error` resource, the reason, and the log or alarm finding. Say when it started after `last_modified`. On a green report the callout is the verdict only.
3. Counts for error, ok, warn, and unknown, and a usage bar of those counts. Caption the source and window. Omit a count that is zero.
4. One card per `warn` or `error` resource, with the finding and a short timeline against `last_modified`. One next step, on the first of those cards. Green reports omit the cards and the next step.
5. When any resource is `unknown`, a short note and a table grouped by type (type, count, role). Unknown means no checker for that type, or that one AWS call failed. Checked types are Lambda (Errors and Throttles), EC2 (state and status checks), RDS (status and CPU), and S3 (exists and public access block). A CloudWatch alarm in ALARM also marks any resource `error` when a dimension matches its id or ARN. Omit this section when every resource was checked.
6. A resource table with filters Checked, Unknown, and All. Default to Checked when any resource is unknown. Sort `error`, then `warn`, then `ok`, then `unknown`. Row tones: `danger`, `warning`, `success`, `neutral`.

On a green report, still write the canvas, and stop after the counts and the table. Do not call CloudWatch.

## Loop

When this run comes from `/loop`, compare with the previous report in the conversation. If nothing changed, reply with one line and do not rewrite the canvas. If something changed, update the canvas and mention only the resources whose status or reason changed.
