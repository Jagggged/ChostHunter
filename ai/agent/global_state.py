"""Global runtime switches for Chost Hunter."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from ai import config


DEFAULT_STATE = {
    "autopilot_enabled": True,
    "finetune_enabled": config.ENABLE_ONLINE_FINETUNE,
}

DEFAULT_FINETUNE_SETTINGS = {
    "interval_sec": config.FINETUNE_INTERVAL_SEC,
    "initial_delay_sec": config.FINETUNE_INITIAL_DELAY_SEC,
    "history_sec": config.FINETUNE_HISTORY_SEC,
    "max_containers": config.FINETUNE_MAX_CONTAINERS,
    "target_containers": [],
    "auto_promote": config.FINETUNE_AUTO_PROMOTE,
    "skip_cpu_threshold": config.FINETUNE_SKIP_CPU_THRESHOLD,
    "skip_memory_threshold": config.FINETUNE_SKIP_MEMORY_THRESHOLD,
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
    state["finetune_settings"] = {
        **DEFAULT_FINETUNE_SETTINGS,
        **state.get("finetune_settings", {}),
    }
    return state


def is_autopilot_enabled() -> bool:
    """Return whether auto policy is allowed to execute docker update."""
    return bool(read_global_state().get("autopilot_enabled", True))


def is_finetune_enabled() -> bool:
    """Return whether runtime fine-tuning is enabled."""
    return bool(read_global_state().get("finetune_enabled", config.ENABLE_ONLINE_FINETUNE))


def get_finetune_settings(path: str = config.GLOBAL_STATE_PATH) -> dict:
    """Return runtime fine-tuning settings with defaults filled in."""
    return dict(read_global_state(path).get("finetune_settings", DEFAULT_FINETUNE_SETTINGS))


def update_finetune_settings(
    updates: dict,
    path: str = config.GLOBAL_STATE_PATH,
) -> dict:
    """Persist runtime fine-tuning settings."""
    state = read_global_state(path)
    settings = {
        **DEFAULT_FINETUNE_SETTINGS,
        **state.get("finetune_settings", {}),
    }
    allowed = set(DEFAULT_FINETUNE_SETTINGS)
    settings.update({key: value for key, value in updates.items() if key in allowed})
    state["finetune_settings"] = settings
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return settings


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


def set_finetune_enabled(
    enabled: bool,
    path: str = config.GLOBAL_STATE_PATH,
) -> dict:
    """Persist the runtime fine-tuning switch."""
    state = read_global_state(path)
    state["finetune_enabled"] = bool(enabled)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return state
