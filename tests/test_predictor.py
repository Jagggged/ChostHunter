import numpy as np
import pytest

pytest.importorskip("torch")
from ai import config
from ai.agent.predictor import recommend_limits


def test_recommend_limits_uses_peak_prediction_with_safety_buffer(monkeypatch):
    monkeypatch.setattr(config, "SAFETY_BUFFER", 0.30)
    monkeypatch.setattr(config, "MIN_CPU_QUOTA", 0.1)
    monkeypatch.setattr(config, "MIN_MEMORY_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(config, "MAX_CPU_QUOTA", 4.0)
    monkeypatch.setattr(config, "MAX_MEMORY_BYTES", 8 * 1024 * 1024 * 1024)
    monkeypatch.setattr(config, "MAX_LIMIT_INCREASE_RATIO", 1.0)
    monkeypatch.setattr(config, "CPU_QUOTA_STEP", 0.0)
    monkeypatch.setattr(config, "MEMORY_STEP_BYTES", 1)

    prediction = np.array([
        [10.0, 100_000.0],
        [50.0, 200_000.0],
        [20.0, 150_000.0],
    ])

    limits = recommend_limits(prediction)

    assert limits["cpu_quota"] == 0.65
    assert limits["memory_bytes"] == 266_240_000


def test_recommend_limits_applies_minimum_floors(monkeypatch):
    monkeypatch.setattr(config, "SAFETY_BUFFER", 0.30)
    monkeypatch.setattr(config, "MIN_CPU_QUOTA", 0.1)
    monkeypatch.setattr(config, "MIN_MEMORY_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(config, "MAX_CPU_QUOTA", 4.0)
    monkeypatch.setattr(config, "MAX_MEMORY_BYTES", 8 * 1024 * 1024 * 1024)
    monkeypatch.setattr(config, "MAX_LIMIT_INCREASE_RATIO", 1.0)
    monkeypatch.setattr(config, "CPU_QUOTA_STEP", 0.0)
    monkeypatch.setattr(config, "MEMORY_STEP_BYTES", 1)

    prediction = np.array([
        [0.0, 0.0],
        [1.0, 128.0],
    ])

    limits = recommend_limits(prediction)

    assert limits["cpu_quota"] == 0.1
    assert limits["memory_bytes"] == 64 * 1024 * 1024


def test_recommend_limits_does_not_grow_finite_current_limits(monkeypatch):
    monkeypatch.setattr(config, "SAFETY_BUFFER", 0.30)
    monkeypatch.setattr(config, "MIN_CPU_QUOTA", 0.1)
    monkeypatch.setattr(config, "MIN_MEMORY_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(config, "MAX_CPU_QUOTA", 4.0)
    monkeypatch.setattr(config, "MAX_MEMORY_BYTES", 2 * 1024 * 1024 * 1024)
    monkeypatch.setattr(config, "MAX_LIMIT_INCREASE_RATIO", 1.0)
    monkeypatch.setattr(config, "CPU_QUOTA_STEP", 0.01)
    monkeypatch.setattr(config, "MEMORY_STEP_BYTES", 16 * 1024 * 1024)

    prediction = np.array([
        [50.0, 45_000_000.0],
    ])

    limits = recommend_limits(
        prediction,
        current_limits={
            "cpu_quota": 100000,
            "memory_bytes": 128 * 1024 * 1024,
            "nano_cpus": 1_000_000_000,
        },
    )

    assert limits == {
        "cpu_quota": 0.65,
        "memory_bytes": 128 * 1024 * 1024,
    }


def test_recommend_limits_applies_hard_caps_without_current_limits(monkeypatch):
    monkeypatch.setattr(config, "SAFETY_BUFFER", 0.30)
    monkeypatch.setattr(config, "MIN_CPU_QUOTA", 0.1)
    monkeypatch.setattr(config, "MIN_MEMORY_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(config, "MAX_CPU_QUOTA", 0.5)
    monkeypatch.setattr(config, "MAX_MEMORY_BYTES", 256 * 1024 * 1024)
    monkeypatch.setattr(config, "MAX_LIMIT_INCREASE_RATIO", 1.0)
    monkeypatch.setattr(config, "CPU_QUOTA_STEP", 0.01)
    monkeypatch.setattr(config, "MEMORY_STEP_BYTES", 16 * 1024 * 1024)

    prediction = np.array([
        [200.0, 45_000_000.0],
    ])

    limits = recommend_limits(prediction)

    assert limits == {
        "cpu_quota": 0.5,
        "memory_bytes": 256 * 1024 * 1024,
    }
