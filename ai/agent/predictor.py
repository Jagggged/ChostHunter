"""
추론 루프 (PyTorch)
주기적으로 Prometheus에서 최근 데이터를 가져와 모델에 추론을 돌리고
권고값(예상 사용량 + 안전 버퍼)을 산출한다.

성능 최적화 메모:
- 모델이 작고 추론 주기가 5분이라 torch.compile / ONNX 도입은 보류
- 추론이 병목이 되면 그때 model = torch.compile(model) 한 줄 추가
"""

import math

import numpy as np
import torch

from ai import config
from ai.data.loader import load_scaler
from ai.model.lstm import LightweightLSTM, build_model, get_device


def load_pretrained(model_path: str = config.PRETRAINED_MODEL_PATH) -> LightweightLSTM:
    """
    저장된 state_dict를 로드해 추론용 모델을 만든다.
    eval 모드로 전환하여 Dropout 등을 비활성화한다.

    config.USE_TORCH_COMPILE이 True면 torch.compile로 JIT 컴파일한다.
    (첫 호출 시 컴파일 오버헤드가 있으니 환경에서 효과 측정 후 활성화 권장)
    """
    device = get_device()
    model = build_model().to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()
    if config.USE_TORCH_COMPILE:
        model = torch.compile(model)
    return model


def predict(model: LightweightLSTM, recent_window: np.ndarray) -> np.ndarray:
    """
    최근 시계열을 받아 미래 사용량을 예측한다.

    Args:
        model: 로드된 LSTM 모델 (eval 모드)
        recent_window: shape (1, window_size, n_features) - 정규화된 입력

    Returns:
        예측값 (horizon, n_features) - 정규화된 상태
    """
    device = get_device()
    x = torch.from_numpy(recent_window).float().to(device)
    with torch.no_grad():
        pred = model(x)
    return pred.cpu().numpy()[0]   # batch 차원 제거


def recommend_limits(
    prediction_unscaled: np.ndarray,
    current_limits: dict | None = None,
) -> dict:
    """
    예측값(원래 스케일)을 바탕으로 컨테이너 리소스 권고값을 계산한다.
    안전 버퍼와 Minimum Floor를 적용한다.

    Args:
        prediction_unscaled: (horizon, 2) - 역정규화된 예측. 컬럼: [CPU%, Memory KB]

    Returns:
        {"cpu_quota": float (코어 단위), "memory_bytes": int}
    """
    max_pred = prediction_unscaled.max(axis=0)   # horizon 중 최대값을 기준
    cpu_pct = float(max_pred[0])                 # CPU 사용률(%)
    mem_kb = float(max_pred[1])                  # 메모리(KB)

    # CPU: % → 코어 수 환산 후 안전 버퍼
    cpu_cores = (cpu_pct / 100.0) * (1 + config.SAFETY_BUFFER)
    cpu_quota = max(cpu_cores, config.MIN_CPU_QUOTA)

    # Memory: KB → bytes 환산 후 안전 버퍼
    mem_bytes = int(mem_kb * 1024 * (1 + config.SAFETY_BUFFER))
    mem_bytes = max(mem_bytes, config.MIN_MEMORY_BYTES)

    return _apply_recommendation_caps(
        cpu_quota=cpu_quota,
        memory_bytes=mem_bytes,
        current_limits=current_limits,
    )


def _apply_recommendation_caps(
    *,
    cpu_quota: float,
    memory_bytes: int,
    current_limits: dict | None,
) -> dict:
    """Clamp and round recommendations so the agent cannot grow limits wildly."""
    cpu_quota = _round_up(cpu_quota, config.CPU_QUOTA_STEP)
    memory_bytes = int(_round_up(float(memory_bytes), float(config.MEMORY_STEP_BYTES)))
    cpu_quota = min(cpu_quota, config.MAX_CPU_QUOTA)
    memory_bytes = min(memory_bytes, config.MAX_MEMORY_BYTES)

    if current_limits:
        current_cpu = _current_cpu_cores(current_limits)
        current_memory = int(current_limits.get("memory_bytes", 0) or 0)
        max_increase = max(config.MAX_LIMIT_INCREASE_RATIO, 0.0)
        if current_cpu > 0:
            cpu_quota = min(cpu_quota, current_cpu * max_increase)
        if current_memory > 0:
            memory_bytes = min(memory_bytes, int(current_memory * max_increase))

    cpu_quota = max(cpu_quota, config.MIN_CPU_QUOTA)
    memory_bytes = max(memory_bytes, config.MIN_MEMORY_BYTES)
    return {"cpu_quota": cpu_quota, "memory_bytes": memory_bytes}


def _current_cpu_cores(current_limits: dict) -> float:
    nano_cpus = int(current_limits.get("nano_cpus", 0) or 0)
    if nano_cpus > 0:
        return nano_cpus / 1_000_000_000
    cpu_quota = float(current_limits.get("cpu_quota", 0) or 0)
    if cpu_quota > 0:
        return cpu_quota / 100_000
    return 0.0


def _round_up(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.ceil(value / step) * step


def inverse_scale(prediction_scaled: np.ndarray) -> np.ndarray:
    """
    정규화된 예측값을 원래 스케일로 되돌린다.
    (CPU%, Memory KB) 단위로 환원.
    """
    scaler = load_scaler()
    flat = prediction_scaled.reshape(-1, prediction_scaled.shape[-1])
    unscaled = scaler.inverse_transform(flat)
    return unscaled.reshape(prediction_scaled.shape)
