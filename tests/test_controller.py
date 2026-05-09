from types import SimpleNamespace

import pytest

pytest.importorskip("docker")
from ai import config
from ai.agent import controller


class FakeContainer:
    def __init__(self, name="app", labels=None, cpu_quota=100000, memory_bytes=256):
        self.name = name
        self.labels = labels or {}
        self.attrs = {
            "HostConfig": {
                "CpuQuota": cpu_quota,
                "Memory": memory_bytes,
            }
        }
        self.update_calls = []

    def update(self, **kwargs):
        self.update_calls.append(kwargs)


def test_has_unlimited_limit_detects_either_unlimited_dimension():
    assert controller._has_unlimited_limit({"cpu_quota": 0, "memory_bytes": 1024})
    assert controller._has_unlimited_limit({"cpu_quota": 100000, "memory_bytes": 0})
    assert not controller._has_unlimited_limit({"cpu_quota": 100000, "memory_bytes": 1024})


def test_resolve_policy_prioritizes_skip_label(monkeypatch):
    monkeypatch.setattr(controller, "get_policy_override", lambda name: None)

    container = FakeContainer(labels={f"{config.LABEL_PREFIX}.skip": "true"})

    assert controller._resolve_policy(container) == "skip"


def test_resolve_policy_uses_explicit_valid_policy(monkeypatch):
    monkeypatch.setattr(controller, "get_policy_override", lambda name: None)

    container = FakeContainer(labels={f"{config.LABEL_PREFIX}.policy": "advisory"})

    assert controller._resolve_policy(container) == "advisory"


def test_resolve_policy_downgrades_unknown_policy_to_advisory(monkeypatch):
    monkeypatch.setattr(controller, "get_policy_override", lambda name: None)

    container = FakeContainer(labels={f"{config.LABEL_PREFIX}.policy": "danger"})

    assert controller._resolve_policy(container) == "advisory"


def test_resolve_policy_treats_unlabeled_unlimited_container_as_advisory(monkeypatch):
    monkeypatch.setattr(controller, "get_policy_override", lambda name: None)
    monkeypatch.setattr(config, "ADVISORY_FOR_UNLABELED_UNLIMITED", True)
    monkeypatch.setattr(config, "DEFAULT_POLICY", "auto")

    container = FakeContainer(labels={}, cpu_quota=0, memory_bytes=512)

    assert controller._resolve_policy(container) == "advisory"


def test_update_limits_converts_cpu_cores_to_docker_quota(monkeypatch):
    container = FakeContainer(cpu_quota=100000, memory_bytes=128 * 1024 * 1024)
    fake_client = SimpleNamespace(
        containers=SimpleNamespace(get=lambda name: container)
    )
    monkeypatch.setattr(controller, "get_client", lambda: fake_client)

    previous = controller.update_limits(
        "app",
        cpu_quota=0.5,
        memory_bytes=256 * 1024 * 1024,
    )

    assert previous == {"cpu_quota": 100000, "memory_bytes": 128 * 1024 * 1024}
    assert container.update_calls == [{
        "cpu_quota": 50000,
        "mem_limit": 256 * 1024 * 1024,
        "memswap_limit": 256 * 1024 * 1024,
    }]


def test_rollback_limits_uses_negative_one_to_restore_unlimited(monkeypatch):
    container = FakeContainer()
    fake_client = SimpleNamespace(
        containers=SimpleNamespace(get=lambda name: container)
    )
    monkeypatch.setattr(controller, "get_client", lambda: fake_client)

    controller.rollback_limits("app", {"cpu_quota": 0, "memory_bytes": 0})

    assert container.update_calls == [{
        "cpu_quota": -1,
        "mem_limit": -1,
        "memswap_limit": -1,
    }]
