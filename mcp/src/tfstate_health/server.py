"""FastMCP server: facts about resources a Terraform stack owns."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from tfstate_health.config import load_settings
from tfstate_health.health import get_stack_health as collect_stack_health
from tfstate_health.loader import last_apply_info as read_last_apply
from tfstate_health.loader import load_state
from tfstate_health.state import list_resources_from_state

# MCP Python SDK 2 renamed FastMCP to MCPServer. Decorators are unchanged.
mcp = MCPServer("tfstate-health", version="0.1.0")


@mcp.tool()
def list_stack_resources(env: str) -> list[dict]:
    """List managed resources owned by the Terraform stack for one environment.

    Reads Terraform state from STATE_FILE, or from S3 (STATE_BUCKET + STATE_KEY).
    Skips data sources. Each record has address, type, module, id, and arn.
    Does not return resource attribute dumps.

    env: environment name interpolated into STATE_FILE or STATE_KEY wherever
    the literal {env} appears. Example: STATE_KEY=envs/{env}/terraform.tfstate
    and env=prod reads envs/prod/terraform.tfstate.
    """
    state = load_state(env, load_settings())
    return list_resources_from_state(state)


@mcp.tool()
def last_apply_info(env: str) -> dict:
    """When the Terraform state for this environment was last written.

    Returns last_modified (UTC), serial, lineage, and minutes_since_last_apply.
    S3 uses the state object's LastModified. A local STATE_FILE uses the file mtime.

    env: same value as list_stack_resources. With this project's STATE_KEY it does
    not change the object path; pass demo.
    """
    return read_last_apply(env, load_settings())


@mcp.tool()
def get_stack_health(env: str, since_minutes: int = 60) -> dict:
    """Health of every managed resource in the Terraform state, grouped by module.

    status is ok, warn, error, or unknown. unknown means this server has no
    checker for that type, or the AWS call failed. It is not by itself a failure.
    since_minutes is the CloudWatch window (default 60, max 10080).

    Checked types: aws_lambda_function (Errors and Throttles), aws_instance
    (state and status checks), aws_db_instance (status and CPUUtilization),
    aws_s3_bucket (exists and public access block). Any type is error when a
    CloudWatch alarm in ALARM has a dimension equal to the resource id or arn.
    """
    return collect_stack_health(env, since_minutes)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
