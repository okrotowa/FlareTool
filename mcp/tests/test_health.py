"""Stack health: one checker per type, alarms, and a failure that stays local."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tfstate_health.health import build_health, judge_database, matching_alarm_names
from tfstate_health.state import list_resources_from_state

FIXTURE = Path(__file__).parent / "fixtures" / "sample.tfstate.json"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


class _Paginator:
    def __init__(self, pages: list[dict]):
        self._pages = pages

    def paginate(self, StateValue: str):
        assert StateValue == "ALARM"
        return self._pages


class _CloudWatch:
    def __init__(self, alarms: list[dict] | None = None, fail_alarms: bool = False):
        self._alarms = alarms or []
        self._fail_alarms = fail_alarms

    def get_paginator(self, name: str):
        assert name == "describe_alarms"
        if self._fail_alarms:
            raise RuntimeError("access denied")
        return _Paginator([{"MetricAlarms": self._alarms, "CompositeAlarms": []}])

    def get_metric_data(self, MetricDataQueries, StartTime, EndTime):
        results = []
        for query in MetricDataQueries:
            metric = query["MetricStat"]["Metric"]
            name = metric["MetricName"]
            dimension = metric["Dimensions"][0]["Value"]
            if name == "Errors" and dimension == "demo-checkout":
                values = [2, 1]
            elif name == "Throttles" and dimension == "demo-checkout":
                values = [4]
            elif name == "CPUUtilization" and dimension == "demo-db":
                values = [85.5]
            else:
                values = [0]
            results.append({"Id": query["Id"], "Values": values})
        return {"MetricDataResults": results}


class _Ec2:
    def describe_instance_status(self, InstanceIds, IncludeAllInstances):
        instance_id = InstanceIds[0]
        if instance_id == "i-bbb":
            raise RuntimeError("throttled")
        return {
            "InstanceStatuses": [
                {
                    "InstanceState": {"Name": "running"},
                    "InstanceStatus": {"Status": "ok"},
                    "SystemStatus": {"Status": "ok"},
                }
            ]
        }


class _Rds:
    def describe_db_instances(self, DBInstanceIdentifier):
        return {"DBInstances": [{"DBInstanceStatus": "available"}]}


class _S3:
    def head_bucket(self, Bucket):
        return {}

    def get_public_access_block(self, Bucket):
        return {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            }
        }


class _Clients:
    def __init__(self, cloudwatch: _CloudWatch):
        self.cloudwatch = cloudwatch
        self.ec2 = _Ec2()
        self.rds = _Rds()
        self.s3 = _S3()


def _resources() -> list[dict]:
    rows = list_resources_from_state(json.loads(FIXTURE.read_text(encoding="utf-8")))
    rows.append(
        {
            "address": "aws_db_instance.api",
            "type": "aws_db_instance",
            "module": None,
            "id": "demo-db",
            "arn": "arn:aws:rds:eu-central-1:123456789012:db:demo-db",
        }
    )
    return rows


def _by_address(report: dict) -> dict[str, dict]:
    found = {}
    for module in report["modules"]:
        for resource in module["resources"]:
            found[resource["address"]] = resource
    return found


def test_checkers_alarms_and_a_single_aws_error():
    alarms = [
        {
            "AlarmName": "checkout-errors",
            "Dimensions": [{"Name": "FunctionName", "Value": "demo-checkout"}],
        }
    ]
    report = build_health(_resources(), 60, _Clients(_CloudWatch(alarms)), now=NOW)
    rows = _by_address(report)
    checkout = rows["aws_lambda_function.checkout"]
    assert checkout["status"] == "error"
    assert checkout["reason"] == (
        "3 errors, 4 throttles in the last 60 minutes; CloudWatch alarm checkout-errors is ALARM"
    )
    assert rows["module.compute.aws_instance.web[0]"]["status"] == "ok"
    assert rows["module.compute.aws_instance.web[1]"]["status"] == "unknown"
    assert "throttled" in rows["module.compute.aws_instance.web[1]"]["reason"]
    assert rows["module.edge.aws_s3_bucket.logs"]["status"] == "ok"
    assert rows["aws_db_instance.api"]["status"] == "warn"
    assert "85.5%" in rows["aws_db_instance.api"]["reason"]
    assert rows["aws_iam_role_policy_attachment.lambda_logs"]["status"] == "unknown"
    assert report["alarm_check"] == "ok"
    assert report["summary"]["error"] == 1
    assert report["modules"][0]["module"] is None


def test_alarm_fetch_failure_does_not_hide_lambda_errors():
    lambdas = [item for item in _resources() if item["type"] == "aws_lambda_function"]
    report = build_health(lambdas, 60, _Clients(_CloudWatch(fail_alarms=True)), now=NOW)
    rows = _by_address(report)
    assert report["alarm_check"].startswith("unknown:")
    assert rows["aws_lambda_function.checkout"]["status"] == "error"
    assert "checkout-errors" not in rows["aws_lambda_function.checkout"]["reason"]


def test_alarm_matches_function_name_inside_the_arn():
    resource = {
        "address": "aws_lambda_function.checkout",
        "type": "aws_lambda_function",
        "id": None,
        "arn": "arn:aws:lambda:eu-central-1:123:function:demo-checkout",
    }
    names = matching_alarm_names(
        [{"AlarmName": "checkout-errors", "Dimensions": [{"Name": "FunctionName", "Value": "demo-checkout"}]}],
        resource,
    )
    assert names == ["checkout-errors"]


def test_database_cpu_thresholds():
    assert judge_database("available", 79)[0] == "ok"
    assert judge_database("available", 80)[0] == "warn"
    assert judge_database("available", 90)[0] == "error"
    assert judge_database("stopped", None)[0] == "warn"
    assert judge_database("failed", None)[0] == "error"


def test_stopped_instance_is_a_warning():
    class _StoppedEc2:
        def describe_instance_status(self, InstanceIds, IncludeAllInstances):
            return {
                "InstanceStatuses": [
                    {
                        "InstanceState": {"Name": "stopped"},
                        "InstanceStatus": {"Status": "not-applicable"},
                        "SystemStatus": {"Status": "not-applicable"},
                    }
                ]
            }

    clients = _Clients(_CloudWatch())
    clients.ec2 = _StoppedEc2()
    resources = [
        {
            "address": "aws_instance.web",
            "type": "aws_instance",
            "module": None,
            "id": "i-aaa",
            "arn": "arn:aws:ec2:eu-central-1:123:instance/i-aaa",
        }
    ]
    report = build_health(resources, 60, clients, now=NOW)
    row = report["modules"][0]["resources"][0]
    assert row["status"] == "warn"
    assert row["reason"] == "instance is stopped"
