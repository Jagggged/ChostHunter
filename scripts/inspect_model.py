"""
학습된 모델이 어떤 패턴을 인식하는지 확인하는 스크립트.

실행:
    python -m scripts.inspect_model --max-files 10 --n-samples 5
"""

import argparse

import numpy as np
import torch

from ai import config
from ai.data.loader import build_dataset, load_scaler
from ai.model.lstm import build_model, get_device


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default="datasets/fastStorage/2013-8")
    p.add_argument("--max-files", type=int, default=10,
                   help="확인용 VM CSV 수 (다양성 위해 5~20 권장)")
    p.add_argument("--n-samples", type=int, default=5,
                   help="출력할 샘플 수")
    p.add_argument("--batch-size", type=int, default=4096,
                   help="추론 배치 크기 (GPU VRAM에 맞춰 조절)")
    return p.parse_args()


def pick_diverse_samples(X_un, y_un, n_samples):
    """
    원래 스케일 기준으로 다양한 패턴의 샘플을 골라낸다.
    - 정답 CPU의 평균 사용률 분위수(0%, 25%, 50%, 75%, 100%) 위치에서 한 개씩
    """
    cpu_avg = y_un[:, :, 0].mean(axis=1)   # 각 샘플의 정답 평균 CPU
    sorted_idx = np.argsort(cpu_avg)

    # 분위수 위치
    quantiles = np.linspace(0, len(sorted_idx) - 1, n_samples).astype(int)
    return sorted_idx[quantiles]


def main():
    args = parse_args()

    print("[1/4] 모델 로드")
    device = get_device()
    model = build_model().to(device)
    model.load_state_dict(torch.load(config.PRETRAINED_MODEL_PATH, map_location=device))
    model.eval()
    scaler = load_scaler()

    print("[2/4] 검증 데이터 준비")
    X, y, _ = build_dataset(args.data_dir, max_files=args.max_files)
    print(f"      total samples={len(X)}")

    # 학습 시와 동일하게 시간순 분리, 마지막 20%
    split = int(len(X) * 0.8)
    X_val, y_val = X[split:], y[split:]
    print(f"      val samples={len(X_val)}")

    print(f"[3/4] 전체 검증셋 RMSE (batch={args.batch_size})")
    # 한 번에 GPU에 올리면 OOM이 나므로 batch 단위로 나눠서 추론
    pred_chunks = []
    with torch.no_grad():
        for start in range(0, len(X_val), args.batch_size):
            end = start + args.batch_size
            xb = torch.from_numpy(X_val[start:end]).float().to(device)
            pred_chunks.append(model(xb).cpu().numpy())
    pred = np.concatenate(pred_chunks, axis=0)

    rmse_scaled = np.sqrt(np.mean((pred - y_val) ** 2))
    pred_un = scaler.inverse_transform(pred.reshape(-1, 2)).reshape(pred.shape)
    y_un = scaler.inverse_transform(y_val.reshape(-1, 2)).reshape(y_val.shape)

    cpu_rmse = np.sqrt(np.mean((pred_un[:, :, 0] - y_un[:, :, 0]) ** 2))
    mem_rmse = np.sqrt(np.mean((pred_un[:, :, 1] - y_un[:, :, 1]) ** 2))

    print(f"      RMSE (정규화)  = {rmse_scaled:.6f}")
    print(f"      RMSE CPU [%]   = {cpu_rmse:.4f}")
    print(f"      RMSE Memory KB = {mem_rmse:.2f}")

    # 검증셋 분포 정보
    cpu_min, cpu_max = y_un[:, :, 0].min(), y_un[:, :, 0].max()
    mem_min, mem_max = y_un[:, :, 1].min(), y_un[:, :, 1].max()
    cpu_avg_per_sample = y_un[:, :, 0].mean(axis=1)
    print(f"\n      [val 분포]")
    print(f"      CPU%: min={cpu_min:.2f}, max={cpu_max:.2f}, "
          f"평균사용률 25%={np.percentile(cpu_avg_per_sample, 25):.2f}, "
          f"50%={np.percentile(cpu_avg_per_sample, 50):.2f}, "
          f"75%={np.percentile(cpu_avg_per_sample, 75):.2f}")
    print(f"      Mem KB: min={mem_min:.0f}, max={mem_max:.0f}")

    print(f"\n[4/4] 다양한 패턴의 샘플 출력 (CPU 사용률 분위수 기준 {args.n_samples}개)")
    idx_list = pick_diverse_samples(None, y_un, args.n_samples)

    for k, i in enumerate(idx_list):
        # 정답 평균 CPU 기준 라벨
        avg_cpu = y_un[i, :, 0].mean()
        if avg_cpu < 1:
            label = "유휴 (거의 0%)"
        elif avg_cpu < 10:
            label = "저부하"
        elif avg_cpu < 50:
            label = "중부하"
        else:
            label = "고부하"

        last_input = scaler.inverse_transform(X_val[i, -1:, :])[0]
        actual = y_un[i]
        predicted = pred_un[i]

        print(f"\n--- Sample {k + 1} (val idx={i}) | {label} ---")
        print(f"  Input (마지막 시점): CPU={last_input[0]:7.2f}%  Mem={last_input[1]:10.0f}KB")
        print(f"  {'step':>5} | {'Actual CPU':>10} {'Pred CPU':>10} {'err':>7} | "
              f"{'Actual Mem':>12} {'Pred Mem':>12} {'err':>10}")
        for h in range(actual.shape[0]):
            cpu_err = predicted[h, 0] - actual[h, 0]
            mem_err = predicted[h, 1] - actual[h, 1]
            print(f"  {h+1:>5} | "
                  f"{actual[h, 0]:>10.2f} {predicted[h, 0]:>10.2f} {cpu_err:>7.2f} | "
                  f"{actual[h, 1]:>12.0f} {predicted[h, 1]:>12.0f} {mem_err:>10.0f}")


if __name__ == "__main__":
    main()
