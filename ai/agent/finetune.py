"""Runtime fine-tuning scheduler for Chost Hunter.

This module keeps the pretrained model as an immutable master. Runtime
fine-tuning trains a candidate model from recent Prometheus metrics and promotes
it to the active model only after a small validation check passes.
"""

from __future__ import annotations

import math
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ai import config
from ai.agent.controller import get_current_usage, list_managed_containers
from ai.agent.finetune_log import record_finetune_run
from ai.agent.global_state import get_finetune_settings
from ai.agent.policy_store import get_policy_override
from ai.data.loader import (
    CPU_COL,
    FEATURE_COLS,
    MEM_COL,
    load_prometheus,
    load_scaler,
    prometheus_rate_window,
    to_sliding_window,
)
from ai.model.trainer import evaluate_model_path, finetune_to_path


def ensure_active_model() -> str:
    """Create the active model from the pretrained master if it is missing."""
    os.makedirs(config.RUNTIME_MODEL_DIR, exist_ok=True)
    if not os.path.exists(config.ACTIVE_MODEL_PATH):
        shutil.copy2(config.PRETRAINED_MODEL_PATH, config.ACTIVE_MODEL_PATH)
        print(f"[finetune] active model initialized from {config.PRETRAINED_MODEL_PATH}")
    return config.ACTIVE_MODEL_PATH


def active_model_mtime() -> float | None:
    """Return active model modification time, or None if it does not exist."""
    try:
        return os.path.getmtime(config.ACTIVE_MODEL_PATH)
    except OSError:
        return None


def collect_recent_dataset(settings: dict | None = None) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Build a small fine-tuning dataset from recent Prometheus container data."""
    settings = settings or get_finetune_settings()
    targets = _discover_finetune_targets(settings)
    max_containers = int(settings.get("max_containers", config.FINETUNE_MAX_CONTAINERS) or 0)
    if max_containers > 0:
        targets = targets[:max_containers]

    X_chunks: list[np.ndarray] = []
    y_chunks: list[np.ndarray] = []
    used_containers: list[str] = []
    scaler = load_scaler()

    end = time.time()
    history_sec = int(settings.get("history_sec", config.FINETUNE_HISTORY_SEC))
    start = end - history_sec
    step = f"{config.INFERENCE_STEP_SEC}s"
    rate_window = prometheus_rate_window(config.INFERENCE_STEP_SEC)

    for name in targets:
        cpu_query = (
            f'rate(container_cpu_usage_seconds_total'
            f'{{name="{name}"}}[{rate_window}]) * 100'
        )
        mem_query = f'container_memory_usage_bytes{{name="{name}"}} / 1024'

        cpu_df = load_prometheus(cpu_query, start, end, step, config.PROMETHEUS_URL)
        mem_df = load_prometheus(mem_query, start, end, step, config.PROMETHEUS_URL)
        if cpu_df.empty or mem_df.empty:
            continue

        df = pd.DataFrame({
            CPU_COL: cpu_df.iloc[:, 0],
            MEM_COL: mem_df.iloc[:, 0],
        }).ffill().bfill().dropna()
        if len(df) < config.WINDOW_SIZE + config.PREDICT_HORIZON:
            continue

        scaled = df.copy()
        scaled[FEATURE_COLS] = scaler.transform(df[FEATURE_COLS])
        X, y = to_sliding_window(scaled)
        if len(X) == 0:
            continue
        X_chunks.append(X)
        y_chunks.append(y)
        used_containers.append(name)

    if not X_chunks:
        return _empty_dataset(), _empty_targets(), used_containers

    X_all = np.concatenate(X_chunks, axis=0)
    y_all = np.concatenate(y_chunks, axis=0)
    if config.FINETUNE_MAX_SAMPLES > 0 and len(X_all) > config.FINETUNE_MAX_SAMPLES:
        idx = np.linspace(0, len(X_all) - 1, config.FINETUNE_MAX_SAMPLES).astype(int)
        X_all = X_all[idx]
        y_all = y_all[idx]
    return X_all.astype(np.float32), y_all.astype(np.float32), used_containers


def _discover_finetune_targets(settings: dict | None = None) -> list[str]:
    """
    Return container names that can contribute runtime training samples.

    Running Docker containers are preferred, but fine-tuning can also use recent
    Prometheus data from a labeled container that already exited. This matters
    for short benchmark jobs such as stress containers.
    """
    settings = settings or get_finetune_settings()
    selected = {
        str(name)
        for name in settings.get("target_containers", [])
        if str(name).strip()
    }
    running_names = {
        target["name"]
        for target in list_managed_containers(include_skipped=False)
        if target.get("policy") != "skip"
    }
    discovered_names = set(running_names)
    discovered_names.update(_discover_labeled_prometheus_names(settings))
    if selected:
        discovered_names &= selected

    blocked = set(config.INFRA_CONTAINER_NAMES)
    result = []
    for name in sorted(discovered_names):
        if not name or name in blocked:
            continue
        if get_policy_override(name) == "skip":
            continue
        result.append(name)
    return result


def _discover_labeled_prometheus_names(settings: dict | None = None) -> set[str]:
    """Discover recently seen advisory/auto containers from cAdvisor labels."""
    settings = settings or get_finetune_settings()
    end = time.time()
    history_sec = int(settings.get("history_sec", config.FINETUNE_HISTORY_SEC))
    start = end - history_sec
    query = (
        'container_cpu_usage_seconds_total'
        '{container_label_chost_hunter_policy=~"auto|advisory",name!=""}'
    )
    df = load_prometheus(
        query,
        start,
        end,
        f"{config.INFERENCE_STEP_SEC}s",
        config.PROMETHEUS_URL,
    )
    if df.empty:
        return set()
    return {str(name) for name in df.columns if str(name)}


def run_finetune_once() -> dict:
    """Run one safe fine-tuning attempt and return the recorded event."""
    started = time.monotonic()
    active_path = ensure_active_model()
    candidate_path = _candidate_path()
    settings = get_finetune_settings()

    try:
        load_skip_reason = _runtime_load_skip_reason(settings)
        if load_skip_reason:
            return record_finetune_run({
                "status": "skipped",
                "reason": load_skip_reason,
                "settings": settings,
            })

        X, y, containers = collect_recent_dataset(settings)
        if len(X) < config.FINETUNE_MIN_SAMPLES:
            return record_finetune_run({
                "status": "skipped",
                "reason": "insufficient samples",
                "containers": containers,
                "samples": int(len(X)),
                "settings": settings,
            })

        X_train, y_train, X_val, y_val = _split_train_val(X, y)
        baseline_val_loss = evaluate_model_path(active_path, X_val, y_val)
        history = finetune_to_path(
            active_path,
            candidate_path,
            X_train,
            y_train,
            X_val,
            y_val,
            epochs=config.FINETUNE_EPOCHS,
        )
        candidate_val_loss = history["val_loss"][-1]
        duration_sec = time.monotonic() - started

        decision = _promotion_decision(
            baseline_val_loss=baseline_val_loss,
            candidate_val_loss=candidate_val_loss,
            duration_sec=duration_sec,
        )
        auto_promote = bool(settings.get("auto_promote", config.FINETUNE_AUTO_PROMOTE))
        if decision["promote"] and auto_promote:
            _promote_candidate(candidate_path)
            status = "promoted"
        elif decision["promote"]:
            status = "validated"
            decision["reason"] = "candidate validation passed; auto-promote disabled"
        else:
            status = "rejected"

        return record_finetune_run({
            "status": status,
            "reason": decision["reason"],
            "containers": containers,
            "samples": int(len(X)),
            "train_samples": int(len(X_train)),
            "val_samples": int(len(X_val)),
            "baseline_val_loss": baseline_val_loss,
            "candidate_val_loss": candidate_val_loss,
            "duration_sec": duration_sec,
            "candidate_model_path": candidate_path,
            "active_model_path": config.ACTIVE_MODEL_PATH,
            "train_loss": history["train_loss"],
            "val_loss": history["val_loss"],
            "settings": settings,
        })
    except Exception as exc:
        return record_finetune_run({
            "status": "failed",
            "reason": str(exc),
            "candidate_model_path": candidate_path,
            "settings": settings,
        })


def _runtime_load_skip_reason(settings: dict) -> str | None:
    """Skip training when managed containers are already under high load."""
    selected = {
        str(name)
        for name in settings.get("target_containers", [])
        if str(name).strip()
    }
    cpu_threshold = float(settings.get("skip_cpu_threshold", config.FINETUNE_SKIP_CPU_THRESHOLD))
    memory_threshold = float(
        settings.get("skip_memory_threshold", config.FINETUNE_SKIP_MEMORY_THRESHOLD)
    )
    if cpu_threshold <= 0 and memory_threshold <= 0:
        return None

    for target in list_managed_containers(include_skipped=False):
        name = target.get("name")
        if selected and name not in selected:
            continue
        try:
            usage = get_current_usage(name)
        except Exception:
            continue
        cpu_pct = float(usage.get("cpu_pct", 0.0) or 0.0)
        mem_pct = float(usage.get("mem_pct", 0.0) or 0.0)
        if cpu_threshold > 0 and cpu_pct >= cpu_threshold:
            return f"runtime load too high: {name} cpu={cpu_pct:.2f}"
        if memory_threshold > 0 and mem_pct >= memory_threshold:
            return f"runtime load too high: {name} memory={mem_pct:.2f}"
    return None


class FineTuneScheduler:
    """Background scheduler that periodically runs safe fine-tuning."""

    def __init__(
        self,
        interval_sec: int | None = None,
        initial_delay_sec: int | None = None,
    ):
        settings = get_finetune_settings()
        if interval_sec is None:
            interval_sec = int(settings.get("interval_sec", config.FINETUNE_INTERVAL_SEC))
        if initial_delay_sec is None:
            initial_delay_sec = int(
                settings.get("initial_delay_sec", config.FINETUNE_INITIAL_DELAY_SEC)
            )
        self.interval_sec = interval_sec
        self.initial_delay_sec = initial_delay_sec
        self.runtime_key = (self.interval_sec, self.initial_delay_sec)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(
            f"[finetune] scheduler starts "
            f"(initial_delay={self.initial_delay_sec}s, interval={self.interval_sec}s)"
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        if self._stop_event.wait(self.initial_delay_sec):
            return
        while not self._stop_event.is_set():
            run = run_finetune_once()
            print(f"[finetune] {run.get('status')}: {run.get('reason')}")
            if self._stop_event.wait(self.interval_sec):
                return


def start_finetune_scheduler() -> FineTuneScheduler:
    """Create and start the runtime fine-tune scheduler."""
    scheduler = FineTuneScheduler()
    scheduler.start()
    return scheduler


def _split_train_val(
    X: np.ndarray,
    y: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    val_count = max(1, int(len(X) * config.FINETUNE_VALIDATION_SPLIT))
    train_count = len(X) - val_count
    if train_count <= 0:
        raise ValueError("not enough samples for train/validation split")
    return X[:train_count], y[:train_count], X[train_count:], y[train_count:]


def _promotion_decision(
    *,
    baseline_val_loss: float,
    candidate_val_loss: float | None,
    duration_sec: float,
) -> dict:
    if candidate_val_loss is None or not math.isfinite(candidate_val_loss):
        return {"promote": False, "reason": "candidate validation loss is invalid"}
    if not math.isfinite(baseline_val_loss):
        return {"promote": False, "reason": "baseline validation loss is invalid"}
    if duration_sec > config.FINETUNE_MAX_DURATION_SEC:
        return {"promote": False, "reason": "fine-tune exceeded duration budget"}

    required = baseline_val_loss * (1.0 - config.FINETUNE_MIN_IMPROVEMENT)
    if candidate_val_loss <= required:
        return {"promote": True, "reason": "candidate validation passed"}
    return {"promote": False, "reason": "candidate did not improve validation loss"}


def _promote_candidate(candidate_path: str) -> None:
    tmp_path = f"{config.ACTIVE_MODEL_PATH}.tmp"
    shutil.copy2(candidate_path, tmp_path)
    os.replace(tmp_path, config.ACTIVE_MODEL_PATH)


def _candidate_path() -> str:
    os.makedirs(config.CANDIDATE_MODEL_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return str(Path(config.CANDIDATE_MODEL_DIR) / f"candidate-{stamp}.pt")


def _empty_dataset() -> np.ndarray:
    return np.empty((0, config.WINDOW_SIZE, config.N_FEATURES), dtype=np.float32)


def _empty_targets() -> np.ndarray:
    return np.empty((0, config.PREDICT_HORIZON, config.N_FEATURES), dtype=np.float32)
