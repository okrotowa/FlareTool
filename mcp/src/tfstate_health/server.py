"""FastMCP server: facts about resources a Terraform stack owns."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from tfstate_health.config import load_settings
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


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
