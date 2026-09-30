"""Load a Terraform state document from a local file or S3."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from tfstate_health.config import STATE_BUCKET, STATE_FILE, STATE_KEY, ConfigError, Settings
from tfstate_health.state import StateParseError, check_env_name


class StateLoadError(Exception):
    """Raised when state cannot be read or is not JSON."""


@dataclass(frozen=True)
class StateSnapshot:
    document: dict[str, Any]
    last_modified: datetime | None


def load_state(env: str, settings: Settings) -> dict[str, Any]:
    """Read the state document for `env`. Local STATE_FILE overrides S3."""
    return load_state_snapshot(env, settings).document


def load_state_snapshot(env: str, settings: Settings) -> StateSnapshot:
    """Read the state document and when that object was last written."""
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


def last_apply_info(env: str, settings: Settings, now: datetime | None = None) -> dict[str, Any]:
    """Serial, lineage, and how long ago the state object was written.

    For S3, last-modified is the object timestamp from the last apply.
    For a local file, it is the file's mtime.
    """
    snapshot = load_state_snapshot(env, settings)
    if snapshot.last_modified is None:
        raise StateLoadError("State was read, but it has no last-modified time.")
    modified = _as_utc(snapshot.last_modified)
    current = _as_utc(now or datetime.now(timezone.utc))
    elapsed = int((current - modified).total_seconds() // 60)
    serial = snapshot.document.get("serial")
    lineage = snapshot.document.get("lineage")
    return {
        "last_modified": modified.isoformat(timespec="seconds"),
        "serial": serial if isinstance(serial, int) else None,
        "lineage": lineage if isinstance(lineage, str) and lineage else None,
        "minutes_since_last_apply": max(elapsed, 0),
    }


def _load_file(path: str | None) -> StateSnapshot:
    if not path:
        raise ConfigError(f"{STATE_FILE} is empty.")
    try:
        mtime = os.stat(path).st_mtime
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
    except FileNotFoundError as exc:
        raise StateLoadError(f"State file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StateLoadError(f"State file is not JSON: {path}") from exc
    if not isinstance(document, dict):
        raise StateParseError(f"State file {path} is not a JSON object.")
    modified = datetime.fromtimestamp(mtime, tz=timezone.utc)
    return StateSnapshot(document, modified)


def _load_s3(bucket: str, key: str, region: str | None, profile: str | None) -> StateSnapshot:
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
    last_modified = response.get("LastModified")
    if isinstance(last_modified, datetime):
        last_modified = _as_utc(last_modified)
    else:
        last_modified = None
    return StateSnapshot(document, last_modified)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
