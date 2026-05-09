"""Global runtime switches for Chost Hunter."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from ai import config


DEFAULT_STATE = {
    "autopilot_enabled": True,
}


def read_global_state(path: str = config.GLOBAL_STATE_PATH) -> dict:
    """Read global runtime state, returning defaults when no file exists."""
    state = dict(DEFAULT_STATE)
    if not os.path.exists(path):
        return state
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return state
    if isinstance(data, dict):
        state.update(data)
    return state


def is_autopilot_enabled() -> bool:
    """Return whether auto policy is allowed to execute docker update."""
    return bool(read_global_state().get("autopilot_enabled", True))


def set_autopilot_enabled(
    enabled: bool,
    path: str = config.GLOBAL_STATE_PATH,
) -> dict:
    """Persist the global autopilot switch."""
    state = read_global_state(path)
    state["autopilot_enabled"] = bool(enabled)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return state
