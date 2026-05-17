"""
Small HTTP control API for inspecting Chost Hunter decisions.

The server intentionally uses Python's standard library so the dashboard can
start consuming runtime state without adding another web framework dependency.
"""

from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ai import config
from ai.agent.action_log import (
    get_action,
    latest_action,
    latest_recommendations,
    read_actions,
    record_action,
)
from ai.agent.controller import list_managed_containers, update_limits
from ai.agent.controller import container_exists
from ai.agent.finetune_log import read_finetune_runs
from ai.agent.global_state import (
    get_finetune_settings,
    read_global_state,
    set_autopilot_enabled,
    set_finetune_enabled,
    update_finetune_settings,
)
from ai.agent.notifier import send_test_notification
from ai.agent.policy_store import set_policy_override
from ai.agent.settings_store import public_slack_settings, update_slack_settings


def _parse_limit(raw_value: str | None, default: int = 50, maximum: int = 500) -> int:
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return max(0, min(value, maximum))


class ControlAPIHandler(BaseHTTPRequestHandler):
    """HTTP handler for action-log and manual-apply endpoints."""

    server_version = "ChostHunterControlAPI/0.1"

    def do_OPTIONS(self) -> None:
        self._send_response({}, HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        try:
            if path == "/api/health":
                self._send_json({"status": "ok"})
            elif path == "/api/actions":
                self._handle_get_actions(query)
            elif path == "/api/actions/latest":
                self._send_json({"action": latest_action()})
            elif path == "/api/recommendations/latest":
                self._handle_get_latest_recommendations()
            elif path == "/api/containers":
                self._send_json({
                    "containers": list_managed_containers(include_skipped=True)
                })
            elif path == "/api/state":
                self._send_json({"state": read_global_state()})
            elif path == "/api/finetune/runs":
                limit = _parse_limit(query.get("limit", [None])[0], default=20)
                self._send_json({"runs": read_finetune_runs(limit=limit)})
            elif path == "/api/finetune/latest":
                runs = read_finetune_runs(limit=1)
                self._send_json({"run": runs[0] if runs else None})
            elif path == "/api/settings/notifications":
                self._send_json({"slack": public_slack_settings()})
            elif path == "/api/settings/finetune":
                self._send_json({"settings": get_finetune_settings()})
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "unknown endpoint")
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        try:
            if path.startswith("/api/actions/") and path.endswith("/apply"):
                action_id = path.removeprefix("/api/actions/").removesuffix("/apply")
                self._handle_apply_action(action_id.strip("/"))
            elif path.startswith("/api/containers/") and path.endswith("/policy"):
                container_name = path.removeprefix("/api/containers/").removesuffix("/policy")
                self._handle_set_policy(container_name.strip("/"))
            elif path == "/api/state/autopilot":
                self._handle_set_autopilot()
            elif path == "/api/state/finetune":
                self._handle_set_finetune()
            elif path == "/api/settings/finetune":
                self._handle_set_finetune_settings()
            elif path == "/api/settings/notifications/slack":
                self._handle_set_slack_notifications()
            elif path == "/api/settings/notifications/slack/test":
                self._handle_test_slack_notifications()
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "unknown endpoint")
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def log_message(self, format: str, *args) -> None:
        print(f"[api] {self.address_string()} - {format % args}")

    def _handle_get_actions(self, query: dict[str, list[str]]) -> None:
        limit = _parse_limit(query.get("limit", [None])[0])
        status = query.get("status", [None])[0]
        container = query.get("container", [None])[0]
        actions = read_actions(limit=limit, status=status, container_name=container)
        self._send_json({"actions": actions})

    def _handle_get_latest_recommendations(self) -> None:
        managed = list_managed_containers(include_skipped=True)
        existing_names = {container["name"] for container in managed}
        recommendations = [
            recommendation
            for recommendation in latest_recommendations()
            if recommendation.get("container") in existing_names
        ]
        self._send_json({"recommendations": recommendations})

    def _handle_apply_action(self, action_id: str) -> None:
        action = get_action(action_id)
        if action is None:
            self._send_error(HTTPStatus.NOT_FOUND, "action not found")
            return

        recommended = action.get("recommended_limits")
        if not recommended:
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "action has no recommended_limits to apply",
            )
            return

        container_name = action.get("container")
        if not container_exists(container_name):
            reason = "container does not exist"
            failed = record_action(
                container_name=container_name,
                policy="manual",
                status="failed",
                current_limits=action.get("current_limits"),
                recommended_limits=recommended,
                reason=reason,
                error=f"No such container: {container_name}",
            )
            self._send_json({"action": failed}, HTTPStatus.NOT_FOUND)
            return

        try:
            prev = update_limits(container_name, **recommended)
        except Exception as exc:
            reason = _friendly_error_message(exc)
            failed = record_action(
                container_name=container_name,
                policy="manual",
                status="failed",
                current_limits=action.get("current_limits"),
                recommended_limits=recommended,
                reason=reason,
                error=str(exc),
            )
            self._send_json({"action": failed}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        applied = record_action(
            container_name=container_name,
            policy="manual",
            status="applied",
            current_limits=action.get("current_limits"),
            recommended_limits=recommended,
            applied_limits=recommended,
            previous_limits=prev,
            reason=f"manual apply from action {action_id}",
        )
        self._send_json({"action": applied})

    def _handle_set_policy(self, container_name: str) -> None:
        payload = self._read_json_body()
        policy = payload.get("policy")
        if policy not in ("auto", "advisory", "skip"):
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "policy must be one of: auto, advisory, skip",
            )
            return

        override = set_policy_override(container_name, policy)
        action = record_action(
            container_name=container_name,
            policy=policy,
            status="policy_updated",
            reason=f"runtime policy override set to {policy}",
        )
        self._send_json({"container": container_name, "override": override, "action": action})

    def _handle_set_autopilot(self) -> None:
        payload = self._read_json_body()
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            self._send_error(HTTPStatus.BAD_REQUEST, "enabled must be a boolean")
            return

        state = set_autopilot_enabled(enabled)
        action = record_action(
            container_name="__global__",
            policy="global",
            status="autopilot_updated",
            reason=f"global autopilot set to {'on' if enabled else 'off'}",
        )
        self._send_json({"state": state, "action": action})

    def _handle_set_finetune(self) -> None:
        payload = self._read_json_body()
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            self._send_error(HTTPStatus.BAD_REQUEST, "enabled must be a boolean")
            return

        state = set_finetune_enabled(enabled)
        action = record_action(
            container_name="__finetune__",
            policy="global",
            status="finetune_updated",
            reason=f"runtime fine-tuning set to {'on' if enabled else 'off'}",
        )
        self._send_json({"state": state, "action": action})

    def _handle_set_finetune_settings(self) -> None:
        payload = self._read_json_body()
        try:
            updates = _coerce_finetune_settings(payload)
        except ValueError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return

        settings = update_finetune_settings(updates)
        action = record_action(
            container_name="__finetune__",
            policy="global",
            status="finetune_settings_updated",
            reason="runtime fine-tuning settings updated",
        )
        self._send_json({"settings": settings, "action": action})

    def _handle_set_slack_notifications(self) -> None:
        payload = self._read_json_body()
        enabled = payload.get("enabled")
        webhook_url = payload.get("webhook_url")
        clear_webhook_url = bool(payload.get("clear_webhook_url", False))

        if enabled is not None and not isinstance(enabled, bool):
            self._send_error(HTTPStatus.BAD_REQUEST, "enabled must be a boolean")
            return
        if webhook_url is not None and not isinstance(webhook_url, str):
            self._send_error(HTTPStatus.BAD_REQUEST, "webhook_url must be a string")
            return

        slack = update_slack_settings(
            enabled=enabled,
            webhook_url=webhook_url,
            clear_webhook_url=clear_webhook_url,
        )
        action = record_action(
            container_name="__notifications__",
            policy="notification",
            status="settings_updated",
            reason="Slack notification settings updated",
        )
        self._send_json({"slack": slack, "action": action})

    def _handle_test_slack_notifications(self) -> None:
        sent, detail = send_test_notification()
        action = record_action(
            container_name="__notifications__",
            policy="notification",
            status="notification_test",
            reason="Slack test notification sent" if sent else detail,
            error=None if sent else detail,
        )
        status = HTTPStatus.OK if sent else HTTPStatus.BAD_REQUEST
        self._send_json({"sent": sent, "detail": detail, "action": action}, status)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send_response(payload, status)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_response({"error": message}, status)

    def _send_response(self, payload: dict, status: HTTPStatus) -> None:
        body = b""
        if status != HTTPStatus.NO_CONTENT:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)


def create_server(
    host: str = config.CONTROL_API_HOST,
    port: int = config.CONTROL_API_PORT,
) -> ThreadingHTTPServer:
    """Create, but do not start, the control API server."""
    return ThreadingHTTPServer((host, port), ControlAPIHandler)


def _friendly_error_message(exc: Exception) -> str:
    message = str(exc)
    if "No such container" in message or "404 Client Error" in message:
        return "container does not exist"
    return message[:200]


def _coerce_finetune_settings(payload: dict) -> dict:
    updates = {}
    integer_fields = {
        "interval_sec": (1, None),
        "initial_delay_sec": (0, None),
        "history_sec": (1, None),
        "max_containers": (0, None),
    }
    float_fields = {
        "skip_cpu_threshold": (0.0, None),
        "skip_memory_threshold": (0.0, None),
    }

    for key, (minimum, maximum) in integer_fields.items():
        if key in payload:
            updates[key] = _coerce_int(payload[key], key, minimum, maximum)

    for key, (minimum, maximum) in float_fields.items():
        if key in payload:
            updates[key] = _coerce_float(payload[key], key, minimum, maximum)

    if "auto_promote" in payload:
        if not isinstance(payload["auto_promote"], bool):
            raise ValueError("auto_promote must be a boolean")
        updates["auto_promote"] = payload["auto_promote"]

    if "target_containers" in payload:
        updates["target_containers"] = _coerce_container_list(payload["target_containers"])

    return updates


def _coerce_int(value, field: str, minimum: int, maximum: int | None) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be an integer") from None
    if coerced < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    if maximum is not None and coerced > maximum:
        raise ValueError(f"{field} must be <= {maximum}")
    return coerced


def _coerce_float(value, field: str, minimum: float, maximum: float | None) -> float:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number") from None
    if coerced < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    if maximum is not None and coerced > maximum:
        raise ValueError(f"{field} must be <= {maximum}")
    return coerced


def _coerce_container_list(value) -> list[str]:
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raise ValueError("target_containers must be a list or comma-separated string")

    names = []
    seen = set()
    for raw in raw_items:
        name = str(raw).strip()
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)
    return names


def start_api_server(
    host: str = config.CONTROL_API_HOST,
    port: int = config.CONTROL_API_PORT,
) -> ThreadingHTTPServer:
    """Start the control API in a daemon thread and return the server."""
    server = create_server(host, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[api] control API listening on http://{host}:{port}")
    return server


def main() -> None:
    """Run the control API until interrupted."""
    server = create_server()
    print(f"[api] control API listening on http://{config.CONTROL_API_HOST}:{config.CONTROL_API_PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[api] interrupted")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
