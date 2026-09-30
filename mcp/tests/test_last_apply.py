"""last_apply_info from a local file mtime and from an S3 LastModified."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tfstate_health.config import Settings
from tfstate_health.loader import StateLoadError, last_apply_info

FIXTURE = Path(__file__).parent / "fixtures" / "sample.tfstate.json"


def test_local_file_reports_serial_lineage_and_minutes(tmp_path: Path):
    path = tmp_path / "demo.tfstate.json"
    path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    written = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)
    os.utime(path, (written.timestamp(), written.timestamp()))
    settings = Settings(
        state_file=str(path),
        state_bucket=None,
        state_key=None,
        region=None,
        profile=None,
    )
    info = last_apply_info("demo", settings, now=written + timedelta(minutes=12, seconds=40))
    assert info["serial"] == 3
    assert info["lineage"] == "11111111-2222-3333-4444-555555555555"
    assert info["minutes_since_last_apply"] == 12
    assert info["last_modified"] == "2026-09-30T10:00:00+00:00"


def test_s3_last_modified_is_minutes_since_apply():
    body = MagicMock()
    body.read.return_value = FIXTURE.read_bytes()
    written = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    client = MagicMock()
    client.get_object.return_value = {"Body": body, "LastModified": written}
    session = MagicMock()
    session.client.return_value = client
    settings = Settings(
        state_file=None,
        state_bucket="state-bucket",
        state_key="demo/terraform.tfstate",
        region="eu-central-1",
        profile=None,
    )
    with patch("boto3.Session", return_value=session):
        info = last_apply_info("demo", settings, now=written + timedelta(minutes=5))
    assert info["minutes_since_last_apply"] == 5
    assert info["serial"] == 3


def test_s3_object_without_last_modified_is_an_error():
    body = MagicMock()
    body.read.return_value = FIXTURE.read_bytes()
    client = MagicMock()
    client.get_object.return_value = {"Body": body}
    session = MagicMock()
    session.client.return_value = client
    settings = Settings(
        state_file=None,
        state_bucket="state-bucket",
        state_key="demo/terraform.tfstate",
        region=None,
        profile=None,
    )
    with patch("boto3.Session", return_value=session):
        with pytest.raises(StateLoadError, match="last-modified"):
            last_apply_info("demo", settings)
