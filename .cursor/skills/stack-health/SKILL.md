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

Use this shape every time:

1. One-line verdict: 🔴 if any `error`, otherwise 🟡 if any `warn`, otherwise 🟢.
2. A table grouped by module: address and status. Put the root module first.
3. Details for `warn` and `error` resources only: the one-line reason, plus the log or alarm finding.
4. One suggested next step. On a green report, the next step is none.

On a green report, stop after the verdict and the table.

## Loop

When this run comes from `/loop`, compare with the previous report in the conversation. Report only resources whose status or reason changed. If nothing changed, reply with one line and stop.
