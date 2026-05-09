"""
Append-only action log for Chost Hunter control decisions.

Each line is one JSON object so operators can inspect the latest decisions with
simple shell tools and future API/UI code can stream or paginate the same file.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from ai import config


def _json_default(value: Any) -> Any:
    """Convert NumPy-like scalar values before json.dumps sees them."""
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def record_action(
    *,
    container_name: str,
    policy: str,
    status: str,
    current_limits: dict | None = None,
    recommended_limits: dict | None = None,
    applied_limits: dict | None = None,
    previous_limits: dict | None = None,
    reason: str | None = None,
    error: str | None = None,
    path: str = config.ACTION_LOG_PATH,
) -> dict:
    """Append a control decision to the JSONL action log and return the entry."""
    entry = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "container": container_name,
        "policy": policy,
        "status": status,
        "current_limits": current_limits,
        "recommended_limits": recommended_limits,
        "applied_limits": applied_limits,
        "previous_limits": previous_limits,
        "reason": reason,
        "error": error,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=_json_default) + "\n")
    try:
        from ai.agent.notifier import notify_action
        notify_action(entry)
    except Exception as exc:
        print(f"[notify] error for action {entry['id']}: {exc}")
    return entry


def read_actions(
    *,
    limit: int | None = None,
    status: str | None = None,
    container_name: str | None = None,
    newest_first: bool = True,
    path: str = config.ACTION_LOG_PATH,
) -> list[dict]:
    """Read action log entries, optionally filtering by status/container."""
    if not os.path.exists(path):
        return []

    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if status is not None and entry.get("status") != status:
                continue
            if container_name is not None and entry.get("container") != container_name:
                continue
            entries.append(entry)

    if newest_first:
        entries.reverse()
    if limit is not None:
        entries = entries[: max(limit, 0)]
    return entries


def get_action(action_id: str, path: str = config.ACTION_LOG_PATH) -> dict | None:
    """Return one action log entry by id."""
    for entry in read_actions(newest_first=False, path=path):
        if entry.get("id") == action_id:
            return entry
    return None


def latest_action(path: str = config.ACTION_LOG_PATH) -> dict | None:
    """Return the newest action log entry."""
    entries = read_actions(limit=1, path=path)
    return entries[0] if entries else None


def latest_recommendations(path: str = config.ACTION_LOG_PATH) -> list[dict]:
    """
    Return the latest recommendation-bearing entry for each container.

    Both advisory recommendations and auto-applied decisions carry
    recommended_limits, so the dashboard can show one current row per container.
    """
    latest_by_container = {}
    for entry in read_actions(newest_first=True, path=path):
        container = entry.get("container")
        if not container or entry.get("recommended_limits") is None:
            continue
        if entry.get("status") not in ("recommended", "applied"):
            continue
        latest_by_container.setdefault(container, entry)
    return list(latest_by_container.values())
