import numpy as np
import pytest

pytest.importorskip("torch")
from ai import config
from ai.agent.predictor import recommend_limits


def test_recommend_limits_uses_peak_prediction_with_safety_buffer(monkeypatch):
    monkeypatch.setattr(config, "SAFETY_BUFFER", 0.30)
    monkeypatch.setattr(config, "MIN_CPU_QUOTA", 0.1)
    monkeypatch.setattr(config, "MIN_MEMORY_BYTES", 64 * 1024 * 1024)

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

    prediction = np.array([
        [0.0, 0.0],
        [1.0, 128.0],
    ])

    limits = recommend_limits(prediction)

    assert limits["cpu_quota"] == 0.1
    assert limits["memory_bytes"] == 64 * 1024 * 1024
