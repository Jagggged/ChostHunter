"""Dashboard-managed runtime settings."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from ai import config


def read_settings(path: str = config.SETTINGS_PATH) -> dict:
    """Read dashboard settings, returning an empty dict when unset."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def write_settings(settings: dict, path: str = config.SETTINGS_PATH) -> dict:
    """Persist dashboard settings."""
    settings = dict(settings)
    settings["updated_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return settings


def _mask_webhook_url(url: str) -> str:
    if not url:
        return ""
    if len(url) <= 12:
        return "********"
    return f"{url[:32]}...{url[-6:]}"


def get_slack_settings() -> dict:
    """Return effective Slack notification settings without exposing secrets."""
    settings = read_settings()
    dashboard_url = str(settings.get("slack_webhook_url") or "").strip()
    env_url = str(config.SLACK_WEBHOOK_URL or "").strip()
    webhook_url = dashboard_url or env_url

    enabled = settings.get("slack_notify_enabled")
    if not isinstance(enabled, bool):
        enabled = bool(config.SLACK_NOTIFY_ENABLED)

    if dashboard_url:
        source = "dashboard"
    elif env_url:
        source = "environment"
    else:
        source = "none"

    return {
        "enabled": enabled,
        "configured": bool(webhook_url),
        "source": source,
        "webhook_url": webhook_url,
        "webhook_url_masked": _mask_webhook_url(webhook_url),
    }


def public_slack_settings() -> dict:
    """Return Slack settings safe for API responses."""
    settings = get_slack_settings()
    settings.pop("webhook_url", None)
    return settings


def update_slack_settings(
    *,
    enabled: bool | None = None,
    webhook_url: str | None = None,
    clear_webhook_url: bool = False,
) -> dict:
    """Update dashboard-managed Slack notification settings."""
    settings = read_settings()
    if enabled is not None:
        settings["slack_notify_enabled"] = bool(enabled)
    if clear_webhook_url:
        settings["slack_webhook_url"] = ""
    elif webhook_url is not None:
        settings["slack_webhook_url"] = webhook_url.strip()
    write_settings(settings)
    return public_slack_settings()
