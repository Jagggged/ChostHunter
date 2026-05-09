"""
LSTM 학습 / Fine-tuning 로직 (PyTorch)
- 사전 학습(Pre-training): 공개 데이터셋으로 처음부터 학습
- Fine-tuning(Online Learning): 운영 중 Prometheus 데이터로 모델 업데이트

학습 안전 장치:
- Best Model Saving: val_loss가 가장 낮은 시점의 weights를 저장 (마지막 epoch ≠ 최선)
- Early Stopping: val_loss가 PATIENCE 동안 개선되지 않으면 학습 중단 (과적합 방지)
- 학습 이력 기록: epoch별 train/val loss + RMSE를 JSON으로 저장 (발표/시각화용)
"""

import copy
import json
import math
import os

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from ai import config
from ai.model.lstm import LightweightLSTM, build_model, get_device


class WeightedMSELoss(nn.Module):
    """
    정답값에 비례한 가중치를 둔 MSE Loss.

    weight = 1 + alpha * normalized_target
    - 유휴 샘플(target ≈ 0): weight ≈ 1 (기존 MSE와 동일)
    - 스파이크 샘플(target ≈ 1): weight ≈ 1 + alpha (오차에 큰 페널티)

    Bitbrain의 99% 유휴 분포에서 model collapse(평균값만 출력)를 방지한다.
    오버샘플링과 함께 쓰면 더 효과적이다.
    """

    def __init__(self, alpha: float = config.WEIGHTED_LOSS_ALPHA):
        super().__init__()
        self.alpha = alpha

    def forward(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        weight = 1.0 + self.alpha * target
        return (weight * (pred - target) ** 2).mean()


def _make_dataloader(
    X: np.ndarray, y: np.ndarray, batch_size: int, shuffle: bool
) -> DataLoader:
    """NumPy 배열을 PyTorch DataLoader로 감싼다."""
    X_t = torch.from_numpy(X).float()
    y_t = torch.from_numpy(y).float()
    dataset = TensorDataset(X_t, y_t)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)


def _train_one_epoch(
    model: LightweightLSTM,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> float:
    """1 epoch 학습 후 평균 train loss 반환"""
    model.train()
    total_loss, n_batches = 0.0, 0
    for xb, yb in loader:
        xb, yb = xb.to(device), yb.to(device)
        optimizer.zero_grad()
        pred = model(xb)
        loss = criterion(pred, yb)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        n_batches += 1
    return total_loss / max(n_batches, 1)


def _evaluate(
    model: LightweightLSTM,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> float:
    """검증셋 loss 계산 (MSE)"""
    model.eval()
    total_loss, n_batches = 0.0, 0
    with torch.no_grad():
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            loss = criterion(model(xb), yb)
            total_loss += loss.item()
            n_batches += 1
    return total_loss / max(n_batches, 1)


def _save_history(history: dict, path: str = config.TRAINING_HISTORY_PATH) -> None:
    """학습 이력을 JSON으로 저장 (시각화/발표용)"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def pretrain(
    X: np.ndarray,
    y: np.ndarray,
    X_val: np.ndarray | None = None,
    y_val: np.ndarray | None = None,
) -> LightweightLSTM:
    """
    공개 데이터셋으로 LSTM을 처음부터 학습한다.

    안전 장치:
    1. Best Model Saving: val_loss가 가장 낮은 시점의 weights를 보관/저장
    2. Early Stopping: val_loss가 EARLY_STOPPING_PATIENCE 동안 개선 X면 중단
    3. 학습 이력 저장: epoch별 loss/RMSE를 JSON으로 기록

    Args:
        X, y: 학습 데이터 (samples, window/horizon, n_features)
        X_val, y_val: 검증 데이터 (선택). 없으면 best/early stopping 기능 비활성

    Returns:
        가장 좋은 시점의 weights를 가진 PyTorch 모델
    """
    device = get_device()
    model = build_model().to(device)

    # 학습용 Loss: 가중 MSE (스파이크 강조) 또는 일반 MSE
    train_criterion = (
        WeightedMSELoss(config.WEIGHTED_LOSS_ALPHA)
        if config.USE_WEIGHTED_LOSS else nn.MSELoss()
    )
    # 평가용 Loss: 항상 일반 MSE (RMSE 비교 일관성을 위해)
    eval_criterion = nn.MSELoss()

    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.LEARNING_RATE,
        weight_decay=config.WEIGHT_DECAY,
    )

    train_loader = _make_dataloader(X, y, config.BATCH_SIZE, shuffle=True)
    has_val = X_val is not None and y_val is not None
    val_loader = (
        _make_dataloader(X_val, y_val, config.BATCH_SIZE, shuffle=False)
        if has_val else None
    )

    loss_kind = "WeightedMSE" if config.USE_WEIGHTED_LOSS else "MSE"
    print(f"[pretrain] device={device}, loss={loss_kind}, "
          f"train_samples={len(X)}, val_samples={len(X_val) if has_val else 0}")

    history = {
        "epoch": [],
        "train_loss": [],
        "val_loss": [],
        "val_rmse": [],
        "best_epoch": None,
        "best_val_loss": None,
        "stopped_epoch": None,
    }

    best_val_loss = math.inf
    best_state_dict = None
    best_epoch = 0
    patience_counter = 0

    for epoch in range(1, config.EPOCHS + 1):
        train_loss = _train_one_epoch(model, train_loader, train_criterion, optimizer, device)
        msg = f"[Epoch {epoch:02d}/{config.EPOCHS}] train_loss={train_loss:.6f}"

        val_loss = None
        val_rmse = None
        if val_loader is not None:
            val_loss = _evaluate(model, val_loader, eval_criterion, device)
            # MSE → RMSE (정규화된 [0,1] 단위 기준; 추후 inverse_scale 시 원 단위 환산)
            val_rmse = math.sqrt(val_loss)
            msg += f"  val_loss={val_loss:.6f}  val_rmse={val_rmse:.6f}"

        history["epoch"].append(epoch)
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["val_rmse"].append(val_rmse)

        # Best model 갱신 + Early Stopping (val 데이터 있을 때만)
        if val_loss is not None:
            improved = val_loss < (best_val_loss - config.EARLY_STOPPING_MIN_DELTA)
            if improved:
                best_val_loss = val_loss
                best_state_dict = copy.deepcopy(model.state_dict())
                best_epoch = epoch
                patience_counter = 0
                msg += "  [best]"
            else:
                patience_counter += 1
                msg += f"  (no improve {patience_counter}/{config.EARLY_STOPPING_PATIENCE})"

        print(msg)

        if (val_loss is not None
                and patience_counter >= config.EARLY_STOPPING_PATIENCE):
            print(f"[pretrain] early stopping at epoch {epoch} "
                  f"(best epoch={best_epoch}, best val_loss={best_val_loss:.6f})")
            history["stopped_epoch"] = epoch
            break

    # val 데이터가 없으면 마지막 weights를 저장, 있으면 best weights를 저장
    if best_state_dict is not None:
        model.load_state_dict(best_state_dict)
        history["best_epoch"] = best_epoch
        history["best_val_loss"] = best_val_loss
        print(f"[pretrain] restored best weights from epoch {best_epoch} "
              f"(val_loss={best_val_loss:.6f})")

    os.makedirs(os.path.dirname(config.PRETRAINED_MODEL_PATH), exist_ok=True)
    torch.save(model.state_dict(), config.PRETRAINED_MODEL_PATH)
    print(f"[pretrain] saved to {config.PRETRAINED_MODEL_PATH}")

    _save_history(history)
    print(f"[pretrain] history saved to {config.TRAINING_HISTORY_PATH}")
    return model


def finetune(model_path: str, X: np.ndarray, y: np.ndarray) -> LightweightLSTM:
    """
    저장된 모델을 운영 데이터로 Fine-tuning한다.
    적은 epoch만 돌려 컨테이너 개별 특성에 맞게 미세 조정한다.

    Args:
        model_path: 기존 state_dict 경로
        X, y: 새로운 운영 데이터

    Returns:
        Fine-tuning된 모델
    """
    device = get_device()
    model = build_model().to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.LEARNING_RATE,
        weight_decay=config.WEIGHT_DECAY,
    )
    loader = _make_dataloader(X, y, config.BATCH_SIZE, shuffle=True)

    for epoch in range(1, config.FINETUNE_EPOCHS + 1):
        loss = _train_one_epoch(model, loader, criterion, optimizer, device)
        print(f"[finetune {epoch}/{config.FINETUNE_EPOCHS}] loss={loss:.6f}")

    torch.save(model.state_dict(), model_path)
    return model
