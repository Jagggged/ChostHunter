"""Run a local Docker scenario that proves watchdog rollback works.

The script starts a temporary Python container, lowers its resource limits,
registers the previous limits with the watchdog, then allocates memory inside
the container. When usage crosses the threshold, the watchdog should restore the
previous limits and append a `rolled_back` action to logs/actions.jsonl.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ai import config
from ai.agent.action_log import read_actions
from ai.agent.controller import get_client, get_container_limits, update_limits
from ai.agent.watchdog import Watchdog


def main() -> int:
    args = _parse_args()
    config.WATCHDOG_INTERVAL_SEC = args.watchdog_interval
    config.WATCHDOG_THRESHOLD = args.watchdog_threshold

    client = get_client()
    _remove_existing(client, args.name)

    container = _start_demo_container(client, args)
    watchdog = Watchdog()
    try:
        _wait_for_running(container)
        before = get_container_limits(args.name)
        previous = update_limits(
            args.name,
            cpu_quota=args.low_cpu,
            memory_bytes=_parse_memory(args.low_memory),
        )
        watchdog.register(args.name, previous)
        watchdog.start()

        print(f"[demo] container={args.name}")
        print(f"[demo] before={before}")
        print(f"[demo] lowered={{'cpu_quota': {args.low_cpu}, 'memory_bytes': {_parse_memory(args.low_memory)}}}")
        print(
            f"[demo] waiting for rollback "
            f"(threshold={config.WATCHDOG_THRESHOLD}, timeout={args.timeout}s)"
        )

        action = _wait_for_rollback(args.name, args.timeout)
        if action is None:
            print("[demo] rollback was not observed before timeout")
            return 1

        after = get_container_limits(args.name)
        print(f"[demo] rollback action={action['id']}")
        print(f"[demo] status={action['status']} reason={action['reason']}")
        print(f"[demo] after={after}")
        return 0
    finally:
        watchdog.stop()
        if not args.keep_container:
            _remove_existing(client, args.name)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="chost-watchdog-demo")
    parser.add_argument("--image", default="python:3.11-slim")
    parser.add_argument("--initial-memory", default="256m")
    parser.add_argument("--initial-cpu", type=float, default=1.0)
    parser.add_argument("--low-memory", default="128m")
    parser.add_argument("--low-cpu", type=float, default=0.1)
    parser.add_argument("--allocate-mb", type=int, default=90)
    parser.add_argument("--allocate-delay-sec", type=float, default=3.0)
    parser.add_argument("--watchdog-threshold", type=float, default=0.70)
    parser.add_argument("--watchdog-interval", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--keep-container", action="store_true")
    return parser.parse_args()


def _start_demo_container(client, args):
    script = (
        "import time\n"
        f"time.sleep({args.allocate_delay_sec})\n"
        "chunks=[]\n"
        f"for _ in range({args.allocate_mb}):\n"
        "    chunks.append(bytearray(1024 * 1024))\n"
        "    time.sleep(0.02)\n"
        "time.sleep(120)\n"
    )
    return client.containers.run(
        args.image,
        ["python", "-c", script],
        name=args.name,
        detach=True,
        labels={f"{config.LABEL_PREFIX}.skip": "true"},
        mem_limit=args.initial_memory,
        memswap_limit=args.initial_memory,
        nano_cpus=int(args.initial_cpu * 1_000_000_000),
    )


def _wait_for_running(container) -> None:
    for _ in range(20):
        container.reload()
        if container.status == "running":
            return
        time.sleep(0.2)
    raise RuntimeError("demo container did not start")


def _wait_for_rollback(container_name: str, timeout: float) -> dict | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for action in read_actions(limit=20):
            if (
                action.get("container") == container_name
                and action.get("status") in ("rolled_back", "rollback_failed")
            ):
                return action
        time.sleep(0.5)
    return None


def _remove_existing(client, name: str) -> None:
    try:
        container = client.containers.get(name)
    except Exception:
        return
    try:
        container.remove(force=True)
    except Exception:
        pass


def _parse_memory(value: str) -> int:
    raw = value.strip().lower()
    units = {
        "k": 1024,
        "kb": 1024,
        "m": 1024**2,
        "mb": 1024**2,
        "g": 1024**3,
        "gb": 1024**3,
    }
    for suffix, multiplier in sorted(units.items(), key=lambda item: len(item[0]), reverse=True):
        if raw.endswith(suffix):
            return int(float(raw[: -len(suffix)]) * multiplier)
    return int(raw)


if __name__ == "__main__":
    sys.exit(main())
