import math

import numpy as np
import pytest

pytest.importorskip("torch")

from ai import config
from ai.agent import finetune


def test_split_train_val_uses_recent_tail_for_validation(monkeypatch):
    monkeypatch.setattr(config, "FINETUNE_VALIDATION_SPLIT", 0.25)

    X = np.arange(8 * config.WINDOW_SIZE * config.N_FEATURES).reshape(
        8,
        config.WINDOW_SIZE,
        config.N_FEATURES,
    )
    y = np.arange(8 * config.PREDICT_HORIZON * config.N_FEATURES).reshape(
        8,
        config.PREDICT_HORIZON,
        config.N_FEATURES,
    )

    X_train, y_train, X_val, y_val = finetune._split_train_val(X, y)

    assert len(X_train) == 6
    assert len(y_train) == 6
    assert len(X_val) == 2
    assert len(y_val) == 2
    np.testing.assert_array_equal(X_val, X[-2:])
    np.testing.assert_array_equal(y_val, y[-2:])


def test_promotion_decision_rejects_invalid_candidate():
    decision = finetune._promotion_decision(
        baseline_val_loss=0.1,
        candidate_val_loss=math.nan,
        duration_sec=1.0,
    )

    assert decision["promote"] is False
    assert "invalid" in decision["reason"]


def test_promotion_decision_promotes_non_worse_candidate(monkeypatch):
    monkeypatch.setattr(config, "FINETUNE_MIN_IMPROVEMENT", 0.0)
    monkeypatch.setattr(config, "FINETUNE_MAX_DURATION_SEC", 120)

    decision = finetune._promotion_decision(
        baseline_val_loss=0.1,
        candidate_val_loss=0.09,
        duration_sec=3.0,
    )

    assert decision == {
        "promote": True,
        "reason": "candidate validation passed",
    }


def test_promotion_decision_rejects_slow_candidate(monkeypatch):
    monkeypatch.setattr(config, "FINETUNE_MAX_DURATION_SEC", 10)

    decision = finetune._promotion_decision(
        baseline_val_loss=0.1,
        candidate_val_loss=0.09,
        duration_sec=11.0,
    )

    assert decision["promote"] is False
    assert "duration" in decision["reason"]


def test_discover_finetune_targets_respects_target_selection(monkeypatch):
    monkeypatch.setattr(
        finetune,
        "list_managed_containers",
        lambda include_skipped=False: [
            {"name": "api", "policy": "auto"},
            {"name": "worker", "policy": "advisory"},
            {"name": "ignored", "policy": "skip"},
        ],
    )
    monkeypatch.setattr(finetune, "_discover_labeled_prometheus_names", lambda settings: {"batch"})
    monkeypatch.setattr(finetune, "get_policy_override", lambda name: None)

    targets = finetune._discover_finetune_targets({
        "target_containers": ["worker", "batch"],
        "history_sec": 60,
    })

    assert targets == ["batch", "worker"]


def test_runtime_load_skip_reason_uses_thresholds(monkeypatch):
    monkeypatch.setattr(
        finetune,
        "list_managed_containers",
        lambda include_skipped=False: [{"name": "api", "policy": "auto"}],
    )
    monkeypatch.setattr(
        finetune,
        "get_current_usage",
        lambda name: {"cpu_pct": 0.91, "mem_pct": 0.2},
    )

    reason = finetune._runtime_load_skip_reason({
        "target_containers": ["api"],
        "skip_cpu_threshold": 0.9,
        "skip_memory_threshold": 0.9,
    })

    assert reason == "runtime load too high: api cpu=0.91"


def test_run_finetune_validates_without_promoting_when_auto_promote_off(monkeypatch):
    X = np.ones(
        (8, config.WINDOW_SIZE, config.N_FEATURES),
        dtype=np.float32,
    )
    y = np.ones(
        (8, config.PREDICT_HORIZON, config.N_FEATURES),
        dtype=np.float32,
    )
    promoted = {"called": False}

    monkeypatch.setattr(config, "FINETUNE_MIN_SAMPLES", 4)
    monkeypatch.setattr(config, "FINETUNE_VALIDATION_SPLIT", 0.25)
    monkeypatch.setattr(finetune, "ensure_active_model", lambda: "active.pt")
    monkeypatch.setattr(finetune, "_candidate_path", lambda: "candidate.pt")
    monkeypatch.setattr(
        finetune,
        "get_finetune_settings",
        lambda: {
            "auto_promote": False,
            "skip_cpu_threshold": 0,
            "skip_memory_threshold": 0,
        },
    )
    monkeypatch.setattr(finetune, "_runtime_load_skip_reason", lambda settings: None)
    monkeypatch.setattr(finetune, "collect_recent_dataset", lambda settings: (X, y, ["api"]))
    monkeypatch.setattr(finetune, "evaluate_model_path", lambda path, X_val, y_val: 0.2)
    monkeypatch.setattr(
        finetune,
        "finetune_to_path",
        lambda *args, **kwargs: {"train_loss": [0.1], "val_loss": [0.05]},
    )
    monkeypatch.setattr(
        finetune,
        "_promote_candidate",
        lambda candidate_path: promoted.update(called=True),
    )
    monkeypatch.setattr(finetune, "record_finetune_run", lambda event: event)

    event = finetune.run_finetune_once()

    assert event["status"] == "validated"
    assert promoted["called"] is False
    assert event["reason"] == "candidate validation passed; auto-promote disabled"
