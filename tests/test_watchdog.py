from ai import config
from ai.agent import watchdog


def test_exceeds_threshold_checks_cpu_and_memory(monkeypatch):
    monkeypatch.setattr(config, "WATCHDOG_THRESHOLD", 0.9)

    assert watchdog._exceeds_threshold({"cpu_pct": 0.91, "mem_pct": 0.1})
    assert watchdog._exceeds_threshold({"cpu_pct": 0.1, "mem_pct": 0.91})
    assert not watchdog._exceeds_threshold({"cpu_pct": 0.9, "mem_pct": 0.9})


def test_watchdog_rolls_back_and_records_action(monkeypatch):
    events = []
    rolled_back = []
    wd = watchdog.Watchdog()

    monkeypatch.setattr(config, "WATCHDOG_THRESHOLD", 0.9)
    monkeypatch.setattr(
        watchdog,
        "get_current_usage",
        lambda name: {"cpu_pct": 0.95, "mem_pct": 0.2},
    )
    monkeypatch.setattr(
        watchdog,
        "rollback_limits",
        lambda name, prev: rolled_back.append((name, prev)),
    )
    monkeypatch.setattr(
        watchdog,
        "record_action",
        lambda **kwargs: events.append(kwargs),
    )

    prev = {"cpu_quota": 100000, "memory_bytes": 256}

    assert wd._check_and_rollback("api", prev) is True
    assert rolled_back == [("api", prev)]
    assert events == [{
        "container_name": "api",
        "policy": "watchdog",
        "status": "rolled_back",
        "applied_limits": prev,
        "previous_limits": prev,
        "reason": "watchdog threshold exceeded: cpu=0.95, memory=0.20",
    }]


def test_watchdog_records_rollback_failure(monkeypatch):
    events = []
    wd = watchdog.Watchdog()

    monkeypatch.setattr(config, "WATCHDOG_THRESHOLD", 0.9)
    monkeypatch.setattr(
        watchdog,
        "get_current_usage",
        lambda name: {"cpu_pct": 0.1, "mem_pct": 0.95},
    )

    def fail_rollback(name, prev):
        raise RuntimeError("docker update failed")

    monkeypatch.setattr(watchdog, "rollback_limits", fail_rollback)
    monkeypatch.setattr(
        watchdog,
        "record_action",
        lambda **kwargs: events.append(kwargs),
    )

    prev = {"cpu_quota": 100000, "memory_bytes": 256}

    assert wd._check_and_rollback("api", prev) is True
    assert events == [{
        "container_name": "api",
        "policy": "watchdog",
        "status": "rollback_failed",
        "previous_limits": prev,
        "reason": "watchdog threshold exceeded: cpu=0.10, memory=0.95",
        "error": "docker update failed",
    }]


def test_watchdog_keeps_tracking_when_usage_is_safe(monkeypatch):
    wd = watchdog.Watchdog()

    monkeypatch.setattr(config, "WATCHDOG_THRESHOLD", 0.9)
    monkeypatch.setattr(
        watchdog,
        "get_current_usage",
        lambda name: {"cpu_pct": 0.2, "mem_pct": 0.3},
    )

    assert wd._check_and_rollback("api", {"cpu_quota": 100000}) is False
