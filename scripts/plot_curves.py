"""
학습 이력(JSON)을 읽어 train/val loss 곡선을 PNG로 저장한다.

사용:
    python -m scripts.plot_curves
    python -m scripts.plot_curves --history models/training_history.json --out models/training_curve.png

발표용 그래프 생성:
- Train vs Val Loss (과적합 여부 시각 확인)
- Val RMSE (실제 예측 오차 추이)
- Best epoch / Early stopping 시점 표시
"""

import argparse
import json
import os

from ai import config


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--history", default=config.TRAINING_HISTORY_PATH,
                   help="학습 이력 JSON 경로")
    p.add_argument("--out", default=config.TRAINING_CURVE_PATH,
                   help="저장할 PNG 경로")
    return p.parse_args()


def main():
    args = parse_args()

    # matplotlib는 학습 시 의존성을 늘리지 않으려 별도 import
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not os.path.exists(args.history):
        raise FileNotFoundError(
            f"history not found: {args.history} (먼저 학습을 돌려야 합니다)"
        )

    with open(args.history, "r", encoding="utf-8") as f:
        history = json.load(f)

    epochs = history["epoch"]
    train_loss = history["train_loss"]
    val_loss = history["val_loss"]
    val_rmse = history["val_rmse"]
    best_epoch = history.get("best_epoch")
    stopped_epoch = history.get("stopped_epoch")

    has_val = any(v is not None for v in val_loss)

    fig, axes = plt.subplots(1, 2 if has_val else 1, figsize=(14, 5))
    if not has_val:
        axes = [axes]

    # 1) Loss curve
    ax = axes[0]
    ax.plot(epochs, train_loss, label="train_loss", color="#1f77b4", linewidth=2)
    if has_val:
        ax.plot(epochs, val_loss, label="val_loss", color="#d62728", linewidth=2)
    if best_epoch is not None:
        ax.axvline(best_epoch, color="green", linestyle="--", alpha=0.6,
                   label=f"best epoch ({best_epoch})")
    if stopped_epoch is not None:
        ax.axvline(stopped_epoch, color="gray", linestyle=":", alpha=0.6,
                   label=f"early stop ({stopped_epoch})")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("MSE Loss")
    ax.set_title("Training / Validation Loss")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # 2) RMSE curve
    if has_val:
        ax = axes[1]
        ax.plot(epochs, val_rmse, label="val_rmse", color="#2ca02c", linewidth=2)
        if best_epoch is not None:
            ax.axvline(best_epoch, color="green", linestyle="--", alpha=0.6,
                       label=f"best epoch ({best_epoch})")
        ax.set_xlabel("Epoch")
        ax.set_ylabel("RMSE (normalized)")
        ax.set_title("Validation RMSE")
        ax.legend()
        ax.grid(True, alpha=0.3)

    fig.tight_layout()
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fig.savefig(args.out, dpi=120, bbox_inches="tight")
    print(f"[plot] saved {args.out}")

    # 콘솔에 요약 출력 (발표용 메모)
    if has_val and best_epoch is not None:
        idx = epochs.index(best_epoch)
        print(f"[summary] best_epoch={best_epoch}  "
              f"val_loss={val_loss[idx]:.6f}  val_rmse={val_rmse[idx]:.6f}")
    if stopped_epoch is not None:
        print(f"[summary] early stopped at epoch {stopped_epoch} "
              f"(EPOCHS={config.EPOCHS} 중)")


if __name__ == "__main__":
    main()
