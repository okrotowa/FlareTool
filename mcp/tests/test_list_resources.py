"""list_stack_resources: local fixture, then the S3 read path."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tfstate_health.config import Settings, load_settings
from tfstate_health.loader import StateLoadError, load_state
from tfstate_health.state import StateParseError, list_resources_from_state

FIXTURE = Path(__file__).parent / "fixtures" / "sample.tfstate.json"


def _resources() -> list[dict]:
    state = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return list_resources_from_state(state)


def test_fixture_lists_managed_resources_only():
    resources = _resources()
    addresses = [item["address"] for item in resources]
    assert addresses == [
        "aws_iam_role_policy_attachment.lambda_logs",
        "aws_lambda_function.checkout",
        "aws_lambda_permission.traffic[\"catalog\"]",
        "aws_lambda_permission.traffic[\"checkout\"]",
        "module.compute.aws_instance.web[0]",
        "module.compute.aws_instance.web[1]",
        "module.edge.aws_s3_bucket.logs",
    ]
    assert all("aws_caller_identity" not in address for address in addresses)


def test_records_stay_compact():
    resources = _resources()
    checkout = next(item for item in resources if item["address"] == "aws_lambda_function.checkout")
    assert checkout == {
        "address": "aws_lambda_function.checkout",
        "type": "aws_lambda_function",
        "module": None,
        "id": "demo-checkout",
        "arn": "arn:aws:lambda:eu-central-1:123456789012:function:demo-checkout",
    }
    encoded = json.dumps(resources)
    assert "do-not-leak" not in encoded
    assert "timeout" not in encoded
    assert "user_data" not in encoded

    attachment = next(item for item in resources if item["type"] == "aws_iam_role_policy_attachment")
    assert attachment["id"].startswith("demo-lambda-exec/")
    assert attachment["arn"] is None

    bucket = next(item for item in resources if item["type"] == "aws_s3_bucket")
    assert bucket["module"] == "module.edge"


def test_rejects_state_without_resources_array():
    with pytest.raises(StateParseError):
        list_resources_from_state({"version": 4})


def test_load_state_from_local_file_with_env_placeholder(tmp_path: Path):
    target = tmp_path / "prod.tfstate"
    target.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    settings = Settings(
        state_file=str(tmp_path / "{env}.tfstate"),
        state_bucket="ignored-when-file-set",
        state_key="ignored",
        region=None,
        profile=None,
    )
    state = load_state("prod", settings)
    assert list_resources_from_state(state)[1]["type"] == "aws_lambda_function"


def test_missing_local_file_is_an_error(tmp_path: Path):
    settings = Settings(
        state_file=str(tmp_path / "missing.tfstate"),
        state_bucket=None,
        state_key=None,
        region=None,
        profile=None,
    )
    with pytest.raises(StateLoadError, match="not found"):
        load_state("demo", settings)


def test_s3_key_interpolates_env_and_returns_parsed_state():
    payload = FIXTURE.read_bytes()
    body = MagicMock()
    body.read.return_value = payload
    client = MagicMock()
    client.get_object.return_value = {"Body": body}
    session = MagicMock()
    session.client.return_value = client

    settings = Settings(
        state_file=None,
        state_bucket="state-bucket",
        state_key="envs/{env}/terraform.tfstate",
        region="eu-central-1",
        profile="hackathon",
    )
    with patch("boto3.Session", return_value=session) as session_cls:
        state = load_state("staging", settings)

    session_cls.assert_called_once_with(profile_name="hackathon", region_name="eu-central-1")
    client.get_object.assert_called_once_with(
        Bucket="state-bucket",
        Key="envs/staging/terraform.tfstate",
    )
    assert len(list_resources_from_state(state)) == 7


def test_s3_key_without_placeholder_is_used_as_written():
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
        load_state("demo", settings)
    client.get_object.assert_called_once_with(Bucket="state-bucket", Key="demo/terraform.tfstate")


def test_rejects_env_that_could_change_the_key_path():
    settings = Settings(
        state_file=None,
        state_bucket="state-bucket",
        state_key="envs/{env}/terraform.tfstate",
        region=None,
        profile=None,
    )
    with pytest.raises(ValueError):
        load_state("../prod", settings)


def test_server_registers_the_tool_and_reads_the_fixture(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STATE_FILE", str(FIXTURE))
    monkeypatch.delenv("STATE_BUCKET", raising=False)
    from tfstate_health.server import list_stack_resources, mcp

    tools = asyncio.run(mcp.list_tools())
    assert [tool.name for tool in tools] == [
        "list_stack_resources",
        "last_apply_info",
        "get_stack_health",
    ]
    rows = list_stack_resources("demo")
    assert len(rows) == 7
    assert rows[1]["address"] == "aws_lambda_function.checkout"


def test_settings_come_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STATE_BUCKET", "b")
    monkeypatch.setenv("STATE_KEY", "envs/{env}/terraform.tfstate")
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_PROFILE", "demo")
    monkeypatch.delenv("STATE_FILE", raising=False)
    settings = load_settings()
    assert settings.resolve_state_key("prod") == "envs/prod/terraform.tfstate"
    assert settings.region == "eu-central-1"
    assert settings.profile == "demo"
