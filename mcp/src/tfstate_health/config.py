"""Environment configuration for where Terraform state lives."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

# Env names are part of the public contract (README, Cursor mcp.json).
STATE_BUCKET = "STATE_BUCKET"
STATE_KEY = "STATE_KEY"
STATE_FILE = "STATE_FILE"
AWS_REGION = "AWS_REGION"
AWS_PROFILE = "AWS_PROFILE"


class ConfigError(Exception):
    """Raised when the server is missing the settings it needs to find state."""


@dataclass(frozen=True)
class Settings:
    """Where to read state, and which AWS credentials to use for S3.

    `state_file` wins over S3. It may contain the literal `{env}`, replaced
    with the tool's env argument. `state_key` works the same way: a key
    without `{env}` is used as written (one state for every env argument).
    """

    state_file: str | None
    state_bucket: str | None
    state_key: str | None
    region: str | None
    profile: str | None

    def resolve_state_file(self, env: str) -> str | None:
        if self.state_file is None:
            return None
        return self.state_file.replace("{env}", env)

    def resolve_state_key(self, env: str) -> str:
        if not self.state_key:
            raise ConfigError(
                f"Set {STATE_KEY} to the object key of the Terraform state. "
                "Include {env} when each environment has its own key, "
                "for example envs/{{env}}/terraform.tfstate."
            )
        return self.state_key.replace("{env}", env)


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    return Settings(
        state_file=_blank_to_none(env.get(STATE_FILE)),
        state_bucket=_blank_to_none(env.get(STATE_BUCKET)),
        state_key=_blank_to_none(env.get(STATE_KEY)),
        region=_blank_to_none(env.get(AWS_REGION)) or _blank_to_none(env.get("AWS_DEFAULT_REGION")),
        profile=_blank_to_none(env.get(AWS_PROFILE)),
    )


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
