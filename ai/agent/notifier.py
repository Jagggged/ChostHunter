"""Slack notification hook for action-log events."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import requests

from ai import config
from ai.agent.settings_store import get_slack_settings


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _format_limits(limits: dict | None) -> str:
    if not limits:
        return "-"
    cpu = limits.get("cpu_quota")
    mem = limits.get("memory_bytes")
    return f"cpu={cpu}, mem={mem}"


def _build_slack_payload(action: dict) -> dict:
    status = action.get("status", "unknown")
    container = action.get("container", "unknown")
    policy = action.get("policy", "unknown")
    reason = action.get("error") or action.get("reason") or ""

    text = f"Chost Hunter: {status} - {container}"
    fields = [
        {"type": "mrkdwn", "text": f"*Container*\n{container}"},
        {"type": "mrkdwn", "text": f"*Status*\n{status}"},
        {"type": "mrkdwn", "text": f"*Policy*\n{policy}"},
        {
            "type": "mrkdwn",
            "text": f"*Recommended*\n{_format_limits(action.get('recommended_limits'))}",
        },
    ]
    if action.get("applied_limits"):
        fields.append({
            "type": "mrkdwn",
            "text": f"*Applied*\n{_format_limits(action.get('applied_limits'))}",
        })
    if reason:
        fields.append({"type": "mrkdwn", "text": f"*Reason*\n{reason[:500]}"})

    return {
        "text": text,
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": text[:150]},
            },
            {"type": "section", "fields": fields},
        ],
    }


def _send_slack_payload(webhook_url: str, payload: dict) -> tuple[bool, str | None]:
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=config.SLACK_TIMEOUT_SEC,
        )
        response.raise_for_status()
    except Exception as exc:
        return False, str(exc)
    return True, None


def _record_notification(action: dict, status: str, detail: str | None = None) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_id": action.get("id"),
        "container": action.get("container"),
        "action_status": action.get("status"),
        "notification_status": status,
        "detail": detail,
    }
    os.makedirs(os.path.dirname(config.NOTIFICATION_LOG_PATH), exist_ok=True)
    with open(config.NOTIFICATION_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=_json_default) + "\n")


def notify_action(action: dict) -> None:
    """Send a Slack notification for notable action events."""
    slack = get_slack_settings()
    if not slack["enabled"]:
        _record_notification(action, "disabled", "Slack notifications are disabled")
        return

    status = action.get("status")
    if status not in config.SLACK_NOTIFY_STATUSES:
        return

    webhook_url = slack["webhook_url"]
    if not webhook_url:
        _record_notification(action, "disabled", "SLACK_WEBHOOK_URL is not set")
        return

    payload = _build_slack_payload(action)
    sent, detail = _send_slack_payload(webhook_url, payload)
    if not sent:
        _record_notification(action, "failed", detail)
        return

    _record_notification(action, "sent", None)


def send_test_notification() -> tuple[bool, str | None]:
    """Send a Slack test message using the effective dashboard/env settings."""
    slack = get_slack_settings()
    if not slack["enabled"]:
        return False, "Slack notifications are disabled"
    webhook_url = slack["webhook_url"]
    if not webhook_url:
        return False, "Slack webhook URL is not configured"

    payload = {
        "text": "Chost Hunter Slack test",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Chost Hunter Slack test"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Slack notifications are connected.",
                },
            },
        ],
    }
    return _send_slack_payload(webhook_url, payload)
