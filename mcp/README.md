# tfstate-health

Read-only MCP server. Terraform state decides which resources belong to the stack.

Built on the MCP Python SDK. SDK 2 renamed `FastMCP` to `MCPServer`; the `@mcp.tool()` style is the same.

## Tools

`list_stack_resources(env)` returns managed resources only (data sources are skipped).
Each record is `address`, `type`, `module`, `id`, `arn`. Full attribute dumps are not returned.

`last_apply_info(env)` returns `last_modified`, `serial`, `lineage`, and `minutes_since_last_apply`.

`get_stack_health(env, since_minutes=60)` returns one report for the whole stack, grouped by module.
Each resource is `ok`, `warn`, `error`, or `unknown` with a one-line reason. `unknown` means there is
no checker for that type, or that resource's AWS call failed. Lambda, EC2, RDS, and S3 are checked.
A CloudWatch alarm in ALARM whose dimension matches a resource id or ARN marks that resource `error`.

## Config

| Variable | Required | Purpose |
| --- | --- | --- |
| `STATE_FILE` | local mode | Path to a `.tfstate` file. `{env}` is replaced with the tool argument. When set, S3 is not used. |
| `STATE_BUCKET` | S3 mode | Bucket that holds the state object. |
| `STATE_KEY` | S3 mode | Object key. Include `{env}` when each environment has its own key, for example `envs/{env}/terraform.tfstate`. A key without `{env}` is used as written. |
| `AWS_REGION` | no | Region for the S3 client. Falls back to `AWS_DEFAULT_REGION`, then the AWS SDK default. |
| `AWS_PROFILE` | no | Named profile. Omit to use the default credential chain. |

`env` must match `[A-Za-z0-9_.-]+`.

## Cursor `mcp.json`

Project config lives in `.cursor/mcp.json`. It launches the virtualenv entry point created by the install below. No `AWS_PROFILE`: boto3 uses the same default credential chain as the AWS CLI (`~/.aws/credentials`).

```json
{
  "mcpServers": {
    "tfstate-health": {
      "command": "/absolute/path/to/FlareTool/mcp/.venv/bin/tfstate-health",
      "env": {
        "STATE_BUCKET": "flare-demo-state-732529885455",
        "STATE_KEY": "demo/terraform.tfstate",
        "AWS_REGION": "eu-central-1"
      }
    }
  }
}
```

`STATE_KEY` is the path of the state file inside the bucket. This stack has one file, so the key is written out in full. To point `env` at a different object per environment, put `{env}` in the key (for example `envs/{env}/terraform.tfstate`). Call the tool with `env` set to `demo` either way; with the key above, that argument does not change the path.

Local fixture, no AWS calls:

```json
{
  "mcpServers": {
    "tfstate-health": {
      "command": "/absolute/path/to/FlareTool/mcp/.venv/bin/tfstate-health",
      "env": {
        "STATE_FILE": "/absolute/path/to/FlareTool/mcp/tests/fixtures/sample.tfstate.json"
      }
    }
  }
}
```

Call the tool with any `env` value when `STATE_FILE` has no `{env}` placeholder (the same file is read).

## How to test

From the repo root. The first block needs no AWS credentials. The second reads the live state object.

```bash
cd mcp
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

```bash
cd mcp
STATE_BUCKET=flare-demo-state-732529885455 \
STATE_KEY=demo/terraform.tfstate \
AWS_REGION=eu-central-1 \
.venv/bin/python -c '
from tfstate_health.config import load_settings
from tfstate_health.loader import load_state
from tfstate_health.state import list_resources_from_state
rows = list_resources_from_state(load_state("demo", load_settings()))
for row in rows:
    print(f"{row[\"address\"]}  {row[\"id\"]}")
'
```
