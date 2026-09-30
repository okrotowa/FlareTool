"""Parse a Terraform state file into a compact resource list.

The state file is the source of truth for what the stack owns. This module
only keeps identity fields (address, type, module, id, arn). Attribute
dumps stay in the state file.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping

_ENV_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class StateParseError(Exception):
    """Raised when a file is not a usable Terraform state document."""


@dataclass(frozen=True)
class StackResource:
    address: str
    type: str
    module: str | None
    id: str | None
    arn: str | None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def list_resources_from_state(state: Mapping[str, Any]) -> list[dict[str, str | None]]:
    """Return managed resource instances, data sources omitted, sorted by address."""
    resources = state.get("resources")
    if not isinstance(resources, list):
        raise StateParseError("Terraform state has no 'resources' array.")

    found: list[StackResource] = []
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        if resource.get("mode") != "managed":
            continue
        resource_type = resource.get("type")
        name = resource.get("name")
        if not isinstance(resource_type, str) or not isinstance(name, str):
            continue
        module = resource.get("module")
        module_name = module if isinstance(module, str) and module else None
        base_address = f"{module_name}.{resource_type}.{name}" if module_name else f"{resource_type}.{name}"
        instances = resource.get("instances")
        if not isinstance(instances, list):
            continue
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            attributes = instance.get("attributes")
            if not isinstance(attributes, dict):
                attributes = {}
            found.append(
                StackResource(
                    address=_instance_address(base_address, instance.get("index_key")),
                    type=resource_type,
                    module=module_name,
                    id=_string_or_none(attributes.get("id")),
                    arn=_string_or_none(attributes.get("arn")),
                )
            )
    found.sort(key=lambda item: item.address)
    return [item.to_dict() for item in found]


def check_env_name(env: str) -> str:
    """Reject env values that are not a single path segment."""
    if not _ENV_PATTERN.fullmatch(env):
        raise ValueError(
            "env must be letters, digits, '.', '_' or '-'. "
            f"Got {env!r}."
        )
    return env


def _instance_address(base_address: str, index_key: Any) -> str:
    if index_key is None:
        return base_address
    if isinstance(index_key, bool):
        return base_address
    if isinstance(index_key, int):
        return f"{base_address}[{index_key}]"
    return f"{base_address}[{json.dumps(index_key, ensure_ascii=False)}]"


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
