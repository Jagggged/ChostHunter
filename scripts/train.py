"""
Bitbrain 데이터셋으로 LSTM 사전 학습을 실행한다.

사용:
    # 작은 샘플로 빠른 검증 (5분 내외)
    python -m scripts.train --max-files 10 --epochs 5

    # 전체 데이터로 본격 학습
    python -m scripts.train

    # 학습 곡선 PNG 자동 생성 비활성
    python -m scripts.train --no-plot

산출물:
    models/pretrained.pt          학습된 가중치 (best epoch 기준)
    models/scaler.pkl             MinMax 스케일러 (운영에서 동일 변환 적용)
    models/training_history.json  epoch별 train/val loss + RMSE
    models/training_curve.png     학습 곡선 시각화 (발표용)
"""

import argparse

import numpy as np

from ai import config
from ai.data.loader import balance_dataset, build_dataset, save_scaler
from ai.model.trainer import pretrain


DEFAULT_DATA_DIR = "datasets/fastStorage/2013-8"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                   help="Bitbrain CSV가 들어 있는 디렉터리")
    p.add_argument("--max-files", type=int, default=None,
                   help="사용할 VM CSV 수 (디버깅 시 작게)")
    p.add_argument("--epochs", type=int, default=None,
                   help="config.EPOCHS 오버라이드 (디버깅용)")
    p.add_argument("--val-split", type=float, default=0.2,
                   help="검증셋 비율 (시간순 분리)")
    p.add_argument("--no-plot", action="store_true",
                   help="학습 종료 후 곡선 PNG 생성을 건너뜀")
    return p.parse_args()


def main():
    args = parse_args()

    if args.epochs is not None:
        config.EPOCHS = args.epochs

    print(f"[1/3] 데이터 로드: dir={args.data_dir}, max_files={args.max_files}")
    X, y, scaler = build_dataset(args.data_dir, max_files=args.max_files)
    print(f"      X shape={X.shape}, y shape={y.shape}")

    print("[2/3] 학습/검증 분리 (시간순, 무작위 X)")
    split = int(len(X) * (1 - args.val_split))
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]
    print(f"      train={len(X_train)}, val={len(X_val)}")

    # 오버샘플링은 train에만 적용 (val은 원본 분포 유지해서 평가 일관성 확보)
    if config.USE_OVERSAMPLING:
        print("[2.5/3] 스파이크 오버샘플링 (train만)")
        X_train, y_train = balance_dataset(X_train, y_train, scaler)

    print(f"[3/3] 사전 학습 시작 (epochs={config.EPOCHS})")
    pretrain(X_train, y_train, X_val, y_val)

    save_scaler(scaler)
    print(f"      scaler saved to {config.SCALER_PATH}")

    if not args.no_plot:
        print("[plot] 학습 곡선 생성 중...")
        try:
            from scripts.plot_curves import main as plot_main
            import sys
            # plot_curves의 argparse가 sys.argv를 읽으므로 일시적으로 비움
            saved_argv = sys.argv
            sys.argv = ["plot_curves"]
            try:
                plot_main()
            finally:
                sys.argv = saved_argv
        except ImportError as e:
            print(f"[plot] matplotlib 미설치 - 곡선 생성 스킵: {e}")
        except Exception as e:
            print(f"[plot] 곡선 생성 실패 (학습 결과는 정상 저장됨): {e}")

    print("Done.")


if __name__ == "__main__":
    main()
