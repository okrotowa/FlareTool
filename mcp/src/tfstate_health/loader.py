"""Load a Terraform state document from a local file or S3."""

from __future__ import annotations

import json
from typing import Any

from tfstate_health.config import STATE_BUCKET, STATE_FILE, STATE_KEY, ConfigError, Settings
from tfstate_health.state import StateParseError, check_env_name


class StateLoadError(Exception):
    """Raised when state cannot be read or is not JSON."""


def load_state(env: str, settings: Settings) -> dict[str, Any]:
    """Read the state document for `env`. Local STATE_FILE overrides S3."""
    check_env_name(env)
    if settings.state_file:
        return _load_file(settings.resolve_state_file(env))
    if not settings.state_bucket:
        raise ConfigError(
            f"Set {STATE_FILE} to a local tfstate path, or {STATE_BUCKET} and {STATE_KEY} "
            "to read state from S3. STATE_KEY may include {env}."
        )
    key = settings.resolve_state_key(env)
    return _load_s3(settings.state_bucket, key, settings.region, settings.profile)


def _load_file(path: str | None) -> dict[str, Any]:
    if not path:
        raise ConfigError(f"{STATE_FILE} is empty.")
    try:
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
    except FileNotFoundError as exc:
        raise StateLoadError(f"State file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StateLoadError(f"State file is not JSON: {path}") from exc
    if not isinstance(document, dict):
        raise StateParseError(f"State file {path} is not a JSON object.")
    return document


def _load_s3(bucket: str, key: str, region: str | None, profile: str | None) -> dict[str, Any]:
    # Imported lazily so local-file use and unit tests do not need a session.
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    session_kwargs: dict[str, str] = {}
    if profile:
        session_kwargs["profile_name"] = profile
    if region:
        session_kwargs["region_name"] = region
    client = boto3.Session(**session_kwargs).client("s3")
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
    except (ClientError, BotoCoreError) as exc:
        raise StateLoadError(f"Failed to read s3://{bucket}/{key}: {exc}") from exc
    try:
        document = json.loads(body)
    except json.JSONDecodeError as exc:
        raise StateLoadError(f"s3://{bucket}/{key} is not JSON.") from exc
    if not isinstance(document, dict):
        raise StateParseError(f"s3://{bucket}/{key} is not a JSON object.")
    return document
