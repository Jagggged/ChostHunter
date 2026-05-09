"""Runtime policy overrides controlled by the dashboard/API."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from ai import config


VALID_POLICIES = {"auto", "advisory", "skip"}


def read_policy_overrides(path: str = config.POLICY_OVERRIDE_PATH) -> dict:
    """Return all runtime policy overrides keyed by container name."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def get_policy_override(container_name: str) -> str | None:
    """Return the override policy for one container, if present and valid."""
    entry = read_policy_overrides().get(container_name)
    if isinstance(entry, dict):
        policy = entry.get("policy")
    else:
        policy = entry
    return policy if policy in VALID_POLICIES else None


def set_policy_override(
    container_name: str,
    policy: str,
    path: str = config.POLICY_OVERRIDE_PATH,
) -> dict:
    """Persist a runtime policy override for one container."""
    if policy not in VALID_POLICIES:
        raise ValueError(f"invalid policy '{policy}'")

    overrides = read_policy_overrides(path)
    entry = {
        "policy": policy,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    overrides[container_name] = entry
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2)
    return entry


def clear_policy_override(
    container_name: str,
    path: str = config.POLICY_OVERRIDE_PATH,
) -> bool:
    """Remove one override. Returns True if an override existed."""
    overrides = read_policy_overrides(path)
    existed = container_name in overrides
    if existed:
        overrides.pop(container_name, None)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(overrides, f, ensure_ascii=False, indent=2)
    return existed
