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
    return f"CPU {_format_cpu(cpu)}, Memory {_format_bytes(mem)}"


def _status_label(status: str) -> str:
    labels = {
        "applied": "적용됨",
        "recommended": "권고",
        "skipped": "건너뜀",
        "failed": "실패",
        "rolled_back": "롤백됨",
        "rollback_failed": "롤백 실패",
        "promoted": "승격됨",
        "rejected": "거절됨",
        "validated": "검증됨",
        "notification_test": "알림 테스트",
        "finetune_updated": "파인튜닝 전환",
        "finetune_settings_updated": "파인튜닝 설정 변경",
    }
    return labels.get(status, status)


def _policy_label(policy: str) -> str:
    labels = {
        "auto": "자동 적용",
        "advisory": "권고만",
        "skip": "제외",
        "global": "전체 설정",
        "notification": "알림",
        "manual": "수동 적용",
    }
    return labels.get(policy, policy)


def _format_cpu(cpu_quota: float | int | None) -> str:
    if cpu_quota is None:
        return "-"
    if cpu_quota == 0:
        return "unlimited"
    if cpu_quota > 1000:
        return f"{cpu_quota / 100000:.2f} cores"
    return f"{float(cpu_quota):.2f} cores"


def _format_bytes(memory_bytes: int | None) -> str:
    if memory_bytes is None:
        return "-"
    if memory_bytes == 0:
        return "unlimited"
    units = ["B", "KB", "MB", "GB"]
    value = float(memory_bytes)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    precision = 0 if value >= 10 else 1
    return f"{value:.{precision}f} {units[unit_index]}"


def _build_slack_payload(action: dict) -> dict:
    status = action.get("status", "unknown")
    container = action.get("container", "unknown")
    policy = action.get("policy", "unknown")
    reason = action.get("reason") or action.get("error") or ""

    status_text = _status_label(status)
    policy_text = _policy_label(policy)
    text = f"Chost Hunter: {status_text} - {container}"
    fields = [
        {"type": "mrkdwn", "text": f"*컨테이너*\n{container}"},
        {"type": "mrkdwn", "text": f"*상태*\n{status_text}"},
        {"type": "mrkdwn", "text": f"*정책*\n{policy_text}"},
        {
            "type": "mrkdwn",
            "text": f"*권고 limit*\n{_format_limits(action.get('recommended_limits'))}",
        },
    ]
    if action.get("applied_limits"):
        fields.append({
            "type": "mrkdwn",
            "text": f"*적용 limit*\n{_format_limits(action.get('applied_limits'))}",
        })
    if reason:
        fields.append({"type": "mrkdwn", "text": f"*사유*\n{reason[:500]}"})

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


def _is_routine_noop_recommendation(action: dict) -> bool:
    """Suppress per-loop recommendations that did not change any limit."""
    reason = action.get("reason") or ""
    return (
        action.get("status") == "recommended"
        and "already applied" in reason
        and action.get("applied_limits") is None
    )


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
    if _is_routine_noop_recommendation(action):
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
        "text": "Chost Hunter Slack 테스트",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Chost Hunter Slack 테스트"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Slack 알림 연결이 정상입니다.",
                },
            },
        ],
    }
    return _send_slack_payload(webhook_url, payload)
