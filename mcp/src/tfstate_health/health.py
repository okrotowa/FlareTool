"""Health checks for resources listed in Terraform state.

Each resource type has a small checker. Types without one stay "unknown".
An AWS error on one resource becomes "unknown" for that resource and does
not fail the rest of the stack.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from tfstate_health.config import Settings, load_settings
from tfstate_health.loader import load_state
from tfstate_health.state import list_resources_from_state

Status = str  # ok | warn | error | unknown
_RANK = {"ok": 0, "unknown": 1, "warn": 2, "error": 3}
_MAX_MINUTES = 7 * 24 * 60
_DB_WARN_CPU = 80
_DB_ERROR_CPU = 90
_DB_WARN_STATUSES = {
    "backing-up",
    "configuring-enhanced-monitoring",
    "creating",
    "modifying",
    "rebooting",
    "renaming",
    "resetting-master-credentials",
    "starting",
    "stopping",
    "stopped",
    "storage-optimization",
    "upgrading",
}


class AwsClients:
    """Read-only AWS clients used by the checkers."""

    def __init__(self, region: str | None, profile: str | None):
        import boto3

        kwargs: dict[str, str] = {}
        if profile:
            kwargs["profile_name"] = profile
        if region:
            kwargs["region_name"] = region
        session = boto3.Session(**kwargs)
        self.cloudwatch = session.client("cloudwatch")
        self.ec2 = session.client("ec2")
        self.rds = session.client("rds")
        self.s3 = session.client("s3")


def get_stack_health(
    env: str,
    since_minutes: int = 60,
    settings: Settings | None = None,
    clients: AwsClients | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Health of every managed resource, grouped by Terraform module."""
    window = _check_window(since_minutes)
    active = settings or load_settings()
    resources = list_resources_from_state(load_state(env, active))
    if clients is None:
        clients = AwsClients(active.region, active.profile)
    return build_health(resources, window, clients, now)


def build_health(
    resources: list[dict[str, Any]],
    since_minutes: int,
    clients: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    start = current - timedelta(minutes=since_minutes)

    lambdas = [item for item in resources if item.get("type") == "aws_lambda_function"]
    instances = [item for item in resources if item.get("type") == "aws_instance"]
    databases = [item for item in resources if item.get("type") == "aws_db_instance"]
    buckets = [item for item in resources if item.get("type") == "aws_s3_bucket"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        alarm_future = pool.submit(_capture, fetch_alarms, clients.cloudwatch)
        lambda_future = pool.submit(
            _capture, fetch_lambda_metrics, clients.cloudwatch, lambdas, start, current
        )
        instance_futures = {
            item["address"]: pool.submit(_capture, fetch_instance, clients.ec2, item) for item in instances
        }
        database_futures = {
            item["address"]: pool.submit(_capture, fetch_database, clients, item, start, current)
            for item in databases
        }
        bucket_futures = {
            item["address"]: pool.submit(_capture, fetch_bucket, clients.s3, item) for item in buckets
        }
        alarms = alarm_future.result()
        lambda_metrics = lambda_future.result()
        instance_facts = {address: future.result() for address, future in instance_futures.items()}
        database_facts = {address: future.result() for address, future in database_futures.items()}
        bucket_facts = {address: future.result() for address, future in bucket_futures.items()}

    alarm_check, alarm_list = _alarm_outcome(alarms)
    rows = []
    for resource in resources:
        status, reason = _judge_resource(
            resource,
            since_minutes,
            lambda_metrics,
            instance_facts,
            database_facts,
            bucket_facts,
            alarm_list,
        )
        rows.append(
            {
                "address": resource["address"],
                "type": resource["type"],
                "module": resource.get("module"),
                "status": status,
                "reason": reason,
            }
        )
    return {
        "since_minutes": since_minutes,
        "alarm_check": alarm_check,
        "summary": _summary(rows),
        "modules": _group_by_module(rows),
    }


def fetch_alarms(cloudwatch: Any) -> list[dict[str, Any]]:
    paginator = cloudwatch.get_paginator("describe_alarms")
    alarms: list[dict[str, Any]] = []
    for page in paginator.paginate(StateValue="ALARM"):
        alarms.extend(page.get("MetricAlarms") or [])
    return alarms


def fetch_lambda_metrics(
    cloudwatch: Any,
    resources: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> dict[str, tuple[float, float]]:
    named = [item for item in resources if item.get("id")]
    if not named:
        return {}
    queries = []
    index: dict[str, tuple[str, str]] = {}
    for position, resource in enumerate(named):
        for prefix, metric in (("e", "Errors"), ("t", "Throttles")):
            query_id = f"{prefix}{position}"
            index[query_id] = (resource["address"], prefix)
            queries.append(
                {
                    "Id": query_id,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/Lambda",
                            "MetricName": metric,
                            "Dimensions": [{"Name": "FunctionName", "Value": resource["id"]}],
                        },
                        "Period": 60,
                        "Stat": "Sum",
                    },
                    "ReturnData": True,
                }
            )
    response = cloudwatch.get_metric_data(MetricDataQueries=queries, StartTime=start, EndTime=end)
    totals = {item["address"]: [0.0, 0.0] for item in named}
    for result in response.get("MetricDataResults") or []:
        address, kind = index[result["Id"]]
        value = float(sum(result.get("Values") or []))
        slot = 0 if kind == "e" else 1
        totals[address][slot] = value
    return {address: (pair[0], pair[1]) for address, pair in totals.items()}


def fetch_instance(ec2: Any, resource: dict[str, Any]) -> dict[str, str]:
    if not resource.get("id"):
        raise ValueError("instance has no id")
    response = ec2.describe_instance_status(InstanceIds=[resource["id"]], IncludeAllInstances=True)
    statuses = response.get("InstanceStatuses") or []
    if not statuses:
        raise LookupError("instance not found")
    item = statuses[0]
    return {
        "state": (item.get("InstanceState") or {}).get("Name") or "unknown",
        "instance_status": (item.get("InstanceStatus") or {}).get("Status") or "not-applicable",
        "system_status": (item.get("SystemStatus") or {}).get("Status") or "not-applicable",
    }


def fetch_database(clients: Any, resource: dict[str, Any], start: datetime, end: datetime) -> dict[str, Any]:
    if not resource.get("id"):
        raise ValueError("db instance has no id")
    response = clients.rds.describe_db_instances(DBInstanceIdentifier=resource["id"])
    instances = response.get("DBInstances") or []
    if not instances:
        raise LookupError("db instance not found")
    status = instances[0].get("DBInstanceStatus") or "unknown"
    cpu = None
    if status == "available":
        cpu = _rds_cpu(clients.cloudwatch, resource["id"], start, end)
    return {"status": status, "cpu": cpu}


def fetch_bucket(s3: Any, resource: dict[str, Any]) -> dict[str, Any]:
    if not resource.get("id"):
        raise ValueError("bucket has no name")
    _call_bucket(s3.head_bucket, resource["id"])
    try:
        block = s3.get_public_access_block(Bucket=resource["id"])
    except Exception as exc:
        if _error_code(exc) == "NoSuchPublicAccessBlockConfiguration":
            return {"block": None}
        raise
    config = (block or {}).get("PublicAccessBlockConfiguration") or {}
    return {"block": config}


def judge_lambda(errors: float, throttles: float, since_minutes: int) -> tuple[Status, str]:
    window = f"in the last {since_minutes} minutes"
    if errors > 0:
        return "error", f"{_count(errors)} errors, {_count(throttles)} throttles {window}"
    if throttles > 0:
        return "warn", f"0 errors, {_count(throttles)} throttles {window}"
    return "ok", f"no errors or throttles {window}"


def judge_instance(state: str, instance_status: str, system_status: str) -> tuple[Status, str]:
    if state != "running":
        status: Status = "warn" if state in {"stopped", "stopping", "pending"} else "error"
        return status, f"instance is {state}"
    failed = [
        label
        for label, value in (("instance", instance_status), ("system", system_status))
        if value not in {"ok", "not-applicable"}
    ]
    if failed:
        detail = ", ".join(f"{label} status {value}" for label, value in (
            ("instance", instance_status),
            ("system", system_status),
        ) if label in failed)
        level: Status = "warn" if instance_status == "initializing" or system_status == "initializing" else "error"
        if "impaired" in {instance_status, system_status}:
            level = "error"
        return level, f"instance is running; {detail}"
    return "ok", "instance is running and status checks passed"


def judge_database(status: str, cpu: float | None) -> tuple[Status, str]:
    if status != "available":
        level: Status = "warn" if status in _DB_WARN_STATUSES else "error"
        return level, f"db instance is {status}"
    if cpu is None:
        return "ok", "db instance is available; no CPUUtilization datapoints"
    if cpu >= _DB_ERROR_CPU:
        return "error", f"db instance is available; CPUUtilization {_count(cpu)}%"
    if cpu >= _DB_WARN_CPU:
        return "warn", f"db instance is available; CPUUtilization {_count(cpu)}%"
    return "ok", f"db instance is available; CPUUtilization {_count(cpu)}%"


def judge_bucket(block: dict[str, Any] | None) -> tuple[Status, str]:
    if block is None:
        return "error", "bucket exists; public access block is not enabled"
    flags = ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")
    if all(block.get(flag) is True for flag in flags):
        return "ok", "bucket exists and public access block is enabled"
    return "error", "bucket exists; public access block is not fully enabled"


def matching_alarm_names(alarms: list[dict[str, Any]], resource: dict[str, Any]) -> list[str]:
    identifiers = _identifiers(resource)
    if not identifiers:
        return []
    names: list[str] = []
    for alarm in alarms:
        for dimension in alarm.get("Dimensions") or []:
            if dimension.get("Value") in identifiers:
                names.append(str(alarm.get("AlarmName") or "unnamed"))
                break
    return names


def _judge_resource(
    resource: dict[str, Any],
    since_minutes: int,
    lambda_metrics: Any,
    instance_facts: dict[str, Any],
    database_facts: dict[str, Any],
    bucket_facts: dict[str, Any],
    alarms: list[dict[str, Any]] | None,
) -> tuple[Status, str]:
    resource_type = resource.get("type")
    address = resource["address"]
    if resource_type == "aws_lambda_function" and not resource.get("id"):
        status, reason = "unknown", "lambda has no function name"
    elif resource_type == "aws_lambda_function":
        status, reason = _from_fetch(
            lambda_metrics, address, lambda value: judge_lambda(value[0], value[1], since_minutes)
        )
    elif resource_type == "aws_instance":
        status, reason = _from_fetch(
            instance_facts,
            address,
            lambda value: judge_instance(value["state"], value["instance_status"], value["system_status"]),
        )
    elif resource_type == "aws_db_instance":
        status, reason = _from_fetch(
            database_facts, address, lambda value: judge_database(value["status"], value["cpu"])
        )
    elif resource_type == "aws_s3_bucket":
        status, reason = _from_fetch(bucket_facts, address, lambda value: judge_bucket(value["block"]))
    else:
        status, reason = "unknown", f"no health check for {resource_type}"

    if not alarms:
        return status, reason
    names = matching_alarm_names(alarms, resource)
    if not names:
        return status, reason
    if len(names) == 1:
        alarm_reason = f"CloudWatch alarm {names[0]} is ALARM"
    else:
        alarm_reason = f"CloudWatch alarms {', '.join(names)} are ALARM"
    if status == "ok":
        return "error", alarm_reason
    return _worse(status, "error"), f"{reason}; {alarm_reason}"


def _from_fetch(facts: Any, address: str, judge: Callable[[Any], tuple[Status, str]]) -> tuple[Status, str]:
    if isinstance(facts, Exception):
        return "unknown", _one_line(facts)
    value = facts.get(address)
    if isinstance(value, LookupError):
        return "error", _one_line(value)
    if isinstance(value, Exception):
        return "unknown", _one_line(value)
    if value is None:
        return "unknown", "no data returned for this resource"
    try:
        return judge(value)
    except Exception as exc:
        return "unknown", _one_line(exc)


def _alarm_outcome(alarms: Any) -> tuple[str, list[dict[str, Any]] | None]:
    if isinstance(alarms, Exception):
        return f"unknown: {_one_line(alarms)}", None
    return "ok", alarms


def _rds_cpu(cloudwatch: Any, db_id: str, start: datetime, end: datetime) -> float | None:
    response = cloudwatch.get_metric_data(
        MetricDataQueries=[
            {
                "Id": "cpu",
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/RDS",
                        "MetricName": "CPUUtilization",
                        "Dimensions": [{"Name": "DBInstanceIdentifier", "Value": db_id}],
                    },
                    "Period": 60,
                    "Stat": "Average",
                },
                "ReturnData": True,
            }
        ],
        StartTime=start,
        EndTime=end,
    )
    results = response.get("MetricDataResults") or []
    values = results[0].get("Values") if results else None
    if not values:
        return None
    return float(max(values))


def _call_bucket(operation: Callable[..., Any], bucket: str) -> None:
    try:
        operation(Bucket=bucket)
    except Exception as exc:
        code = _error_code(exc)
        if code in {"404", "NoSuchBucket", "NotFound"}:
            raise LookupError("bucket does not exist") from exc
        if code in {"301", "PermanentRedirect"}:
            raise LookupError("bucket is not in this region") from exc
        raise


def _identifiers(resource: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    if resource.get("id"):
        found.add(str(resource["id"]))
    arn = resource.get("arn") or ""
    if not isinstance(arn, str) or not arn:
        return found
    found.add(arn)
    if ":function:" in arn:
        found.add(arn.rsplit(":function:", 1)[1])
    if arn.startswith("arn:aws:s3:::"):
        found.add(arn.removeprefix("arn:aws:s3:::"))
    if "/instance/" in arn:
        found.add(arn.rsplit("/", 1)[1])
    if ":db:" in arn:
        found.add(arn.rsplit(":", 1)[1])
    return {item for item in found if item}


def _group_by_module(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str | None, list[dict[str, Any]]] = {}
    for row in rows:
        module = row.get("module")
        grouped.setdefault(module, []).append(
            {
                "address": row["address"],
                "type": row["type"],
                "status": row["status"],
                "reason": row["reason"],
            }
        )
    modules = sorted(grouped, key=lambda name: (name is not None, name or ""))
    return [{"module": name, "resources": grouped[name]} for name in modules]


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"ok": 0, "warn": 0, "error": 0, "unknown": 0}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return counts


def _worse(left: Status, right: Status) -> Status:
    return left if _RANK[left] >= _RANK[right] else right


def _capture(function: Callable[..., Any], *args: Any) -> Any:
    try:
        return function(*args)
    except Exception as exc:
        return exc


def _check_window(since_minutes: int) -> int:
    if isinstance(since_minutes, bool) or not isinstance(since_minutes, int):
        raise ValueError("since_minutes must be an integer")
    if since_minutes < 1 or since_minutes > _MAX_MINUTES:
        raise ValueError(f"since_minutes must be between 1 and {_MAX_MINUTES}")
    return since_minutes


def _count(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}"


def _one_line(exc: Exception) -> str:
    code = _error_code(exc)
    text = str(exc).replace("\n", " ").strip()
    if code and code not in text:
        text = f"{code}: {text}"
    return text[:240] or exc.__class__.__name__


def _error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error") or {}
        code = error.get("Code")
        if isinstance(code, str):
            return code
    return None
