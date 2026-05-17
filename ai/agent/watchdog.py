"""Watchdog rollback loop for unsafe resource-limit updates."""

from __future__ import annotations

import threading
import time

from ai import config
from ai.agent.action_log import record_action
from ai.agent.controller import get_current_usage, rollback_limits


class Watchdog:
    """Monitor recently updated containers and restore previous limits on spikes."""

    def __init__(self):
        self._previous_limits: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def register(self, container_name: str, prev_limits: dict) -> None:
        """Track a container's previous limits for a possible rollback."""
        with self._lock:
            self._previous_limits[container_name] = prev_limits

    def unregister(self, container_name: str) -> None:
        """Remove a container from rollback tracking."""
        with self._lock:
            self._previous_limits.pop(container_name, None)

    def start(self) -> None:
        """Start the watchdog thread if it is not already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Request watchdog shutdown and wait briefly for the thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _watch_loop(self) -> None:
        """Periodically check tracked containers and roll back unsafe limits."""
        while not self._stop_event.is_set():
            with self._lock:
                snapshot = dict(self._previous_limits)

            for name, prev in snapshot.items():
                if self._check_and_rollback(name, prev):
                    self.unregister(name)

            time.sleep(config.WATCHDOG_INTERVAL_SEC)

    def _check_and_rollback(self, name: str, prev: dict) -> bool:
        """Return True when the container should be removed from tracking."""
        try:
            usage = get_current_usage(name)
        except Exception as e:
            print(f"[watchdog] usage error for {name}: {e}")
            return False

        if not _exceeds_threshold(usage):
            return False

        reason = (
            "watchdog threshold exceeded: "
            f"cpu={usage['cpu_pct']:.2f}, memory={usage['mem_pct']:.2f}"
        )
        print(f"[watchdog] ROLLBACK {name}: cpu={usage['cpu_pct']:.2f} "
              f"mem={usage['mem_pct']:.2f}")
        try:
            rollback_limits(name, prev)
        except Exception as e:
            print(f"[watchdog] rollback error for {name}: {e}")
            record_action(
                container_name=name,
                policy="watchdog",
                status="rollback_failed",
                previous_limits=prev,
                reason=reason,
                error=str(e),
            )
            return True

        record_action(
            container_name=name,
            policy="watchdog",
            status="rolled_back",
            applied_limits=prev,
            previous_limits=prev,
            reason=reason,
        )
        return True


def _exceeds_threshold(usage: dict) -> bool:
    return (
        usage["cpu_pct"] > config.WATCHDOG_THRESHOLD
        or usage["mem_pct"] > config.WATCHDOG_THRESHOLD
    )
