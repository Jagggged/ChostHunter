"""
데이터 로더 (Bitbrain GWA-T-12 데이터셋)

Bitbrain CSV 파일들을 읽어 LSTM 입력용 슬라이딩 윈도우로 변환한다.
각 CSV는 한 VM의 한 달치 시계열로, 구분자는 ';\\t' (세미콜론+탭) 이다.
사용 컬럼은 CPU 사용률(%)과 메모리 사용량(KB) 두 가지.
"""

import glob
import os
import time

import joblib
import numpy as np
import pandas as pd
import requests
from sklearn.preprocessing import MinMaxScaler

from ai import config


# Bitbrain CSV에서 사용할 컬럼명
CPU_COL = "CPU usage [%]"
MEM_COL = "Memory usage [KB]"
FEATURE_COLS = [CPU_COL, MEM_COL]


def load_csv(path: str) -> pd.DataFrame:
    """
    Bitbrain CSV 한 개를 DataFrame으로 로드한다.
    구분자가 일반적이지 않아(';\\t') 정규식 분리가 필요하다.
    """
    df = pd.read_csv(path, sep=r";\s*", engine="python")
    # 컬럼명 양쪽 공백/탭 제거
    df.columns = [c.strip() for c in df.columns]
    return df


def load_directory(directory: str, max_files: int | None = None) -> list[pd.DataFrame]:
    """
    디렉터리 안의 모든 CSV를 VM별 DataFrame 리스트로 반환한다.
    VM별로 시계열이 분리되어야 하므로 한 DataFrame으로 합치지 않는다.

    Args:
        directory: 예) "datasets/fastStorage/2013-8"
        max_files: 빠른 실험을 위한 파일 수 제한 (None이면 전체)
    """
    paths = sorted(glob.glob(os.path.join(directory, "*.csv")))
    if max_files is not None:
        paths = paths[:max_files]
    return [load_csv(p) for p in paths]


def filter_active_vms(
    dfs: list[pd.DataFrame],
    min_cpu_max: float = config.ACTIVE_VM_MIN_CPU_MAX,
    min_cpu_std: float = config.ACTIVE_VM_MIN_CPU_STD,
) -> list[pd.DataFrame]:
    """
    "활성 VM"만 필터링한다.

    Bitbrain의 1,250개 VM 중 다수는 항상 CPU 0% 근처인 "죽은 VM"이라 학습 신호를 흐린다.
    CPU max가 임계 % 이상이거나 표준편차가 충분히 큰 VM만 남겨,
    오버샘플링/가중치 없이도 자연스럽게 데이터 균형을 맞춘다.

    필터 기준 (둘 중 하나만 만족하면 통과):
    - CPU max >= min_cpu_max  : 한 번이라도 의미 있는 부하가 있었던 VM
    - CPU std >= min_cpu_std  : 변동성이 있는 VM (작은 값에서도 패턴이 있는 경우)
    """
    active = []
    rejected = 0
    for df in dfs:
        if CPU_COL not in df.columns:
            continue
        cpu = df[CPU_COL]
        if cpu.max() >= min_cpu_max or cpu.std() >= min_cpu_std:
            active.append(df)
        else:
            rejected += 1

    print(f"[filter] 활성 VM {len(active)} / 비활성 {rejected} "
          f"(기준: max>={min_cpu_max}% or std>={min_cpu_std})")
    return active


def preprocess(df: pd.DataFrame, feature_cols: list[str] = FEATURE_COLS) -> pd.DataFrame:
    """
    필요한 컬럼만 추출하고 결측치를 채운다.
    Bitbrain은 일부 행에서 메모리 0KB로 측정 누락이 있으므로 ffill/bfill로 보간한다.
    """
    out = df[feature_cols].copy()
    out = out.ffill().bfill()
    out = out.dropna()
    return out


def fit_scaler(dfs: list[pd.DataFrame], feature_cols: list[str] = FEATURE_COLS) -> MinMaxScaler:
    """
    여러 VM 데이터를 합쳐 MinMaxScaler를 학습시킨다.
    학습/추론 시 동일한 스케일러를 써야 하므로 운영에서는 저장/로드해 사용한다.
    """
    combined = pd.concat([df[feature_cols] for df in dfs], ignore_index=True)
    scaler = MinMaxScaler()
    scaler.fit(combined)
    return scaler


def save_scaler(scaler: MinMaxScaler, path: str = config.SCALER_PATH) -> None:
    """학습된 스케일러를 디스크에 저장한다 (추론 시 동일한 변환을 적용해야 하므로)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(scaler, path)


def load_scaler(path: str = config.SCALER_PATH) -> MinMaxScaler:
    """저장된 스케일러를 로드한다."""
    return joblib.load(path)


def to_sliding_window(
    df: pd.DataFrame,
    window_size: int = config.WINDOW_SIZE,
    horizon: int = config.PREDICT_HORIZON,
    feature_cols: list[str] = FEATURE_COLS,
) -> tuple[np.ndarray, np.ndarray]:
    """
    한 VM의 시계열 DataFrame을 LSTM 입력용 슬라이딩 윈도우로 변환한다.

    각 샘플:
        X[i] = data[i              : i+window_size]              # 과거 window_size step
        y[i] = data[i+window_size  : i+window_size+horizon]      # 그 직후 horizon step

    Returns:
        X: (samples, window_size, n_features)
        y: (samples, horizon, n_features)
    """
    data = df[feature_cols].values
    n = len(data)
    n_samples = n - window_size - horizon + 1

    if n_samples <= 0:
        # 데이터가 너무 짧으면 빈 배열 반환
        empty_X = np.empty((0, window_size, len(feature_cols)))
        empty_y = np.empty((0, horizon, len(feature_cols)))
        return empty_X, empty_y

    X = np.zeros((n_samples, window_size, len(feature_cols)))
    y = np.zeros((n_samples, horizon, len(feature_cols)))
    for i in range(n_samples):
        X[i] = data[i : i + window_size]
        y[i] = data[i + window_size : i + window_size + horizon]
    return X, y


def balance_dataset(
    X: np.ndarray,
    y: np.ndarray,
    scaler: MinMaxScaler,
    threshold_pct: float = config.SPIKE_CPU_THRESHOLD_PCT,
    max_ratio: int = config.MAX_OVERSAMPLE_RATIO,
) -> tuple[np.ndarray, np.ndarray]:
    """
    스파이크 샘플을 오버샘플링하여 데이터 불균형을 완화한다.

    Bitbrain은 유휴 샘플이 99%라 모델이 평균(거의 0%)만 출력하면 MSE가 작게 나오는
    Model Collapse가 발생한다. 스파이크 샘플을 N배 복제해서 학습 신호를 키운다.

    Args:
        X, y: 학습 데이터 (정규화된 [0, 1] 범위)
        scaler: 학습된 MinMaxScaler (역정규화로 원 단위 CPU% 확인용)
        threshold_pct: 정답 horizon의 max CPU%가 이 값 이상이면 스파이크
        max_ratio: 스파이크 샘플 1개당 최대 복제 배수 (메모리 보호)

    Returns:
        (X_balanced, y_balanced): 스파이크 비율이 끌어올려진 데이터셋
    """
    n_samples, horizon, n_feats = y.shape

    # 정답값을 원 단위로 환원해 CPU% 임계값 검사 (CPU는 컬럼 0)
    y_flat = y.reshape(-1, n_feats)
    y_unscaled = scaler.inverse_transform(y_flat).reshape(n_samples, horizon, n_feats)
    cpu_max_per_sample = y_unscaled[:, :, 0].max(axis=1)

    spike_mask = cpu_max_per_sample >= threshold_pct
    n_spike = int(spike_mask.sum())
    n_idle = n_samples - n_spike

    if n_spike == 0:
        print(f"[balance] 스파이크 샘플 없음 (threshold={threshold_pct}%) - 원본 반환")
        return X, y

    # 유휴 샘플 수에 맞춰 복제 배수 결정 (단, max_ratio로 상한)
    desired_ratio = n_idle / n_spike
    actual_ratio = min(int(desired_ratio), max_ratio)
    actual_ratio = max(actual_ratio, 1)

    spike_indices = np.where(spike_mask)[0]
    duplicated_indices = np.repeat(spike_indices, actual_ratio)

    X_aug = np.concatenate([X, X[duplicated_indices]], axis=0)
    y_aug = np.concatenate([y, y[duplicated_indices]], axis=0)

    # 시간 순서를 유지하기보다 무작위 셔플 — 학습 시 안정성 향상
    perm = np.random.permutation(len(X_aug))
    X_aug = X_aug[perm]
    y_aug = y_aug[perm]

    print(f"[balance] 원본: {n_samples} (idle={n_idle}, spike={n_spike}) "
          f"→ {actual_ratio}배 복제 후 {len(X_aug)} 샘플")
    print(f"[balance] 스파이크 비율: {n_spike/n_samples*100:.2f}% "
          f"→ {(n_spike*actual_ratio)/(n_samples + n_spike*(actual_ratio-1))*100:.2f}%")
    return X_aug, y_aug


def build_dataset(
    directory: str,
    window_size: int = config.WINDOW_SIZE,
    horizon: int = config.PREDICT_HORIZON,
    max_files: int | None = None,
) -> tuple[np.ndarray, np.ndarray, MinMaxScaler]:
    """
    디렉터리에서 데이터셋을 빌드하는 통합 파이프라인.
    load → preprocess → fit_scaler → 정규화 → 슬라이딩 윈도우 → 모든 VM stack.

    VM 경계를 넘어 윈도우가 만들어지지 않도록 VM별로 분리하여 처리한 뒤 마지막에 합친다.

    Returns:
        X: (samples, window_size, n_features)
        y: (samples, horizon, n_features)
        scaler: 학습된 스케일러 (운영에서 동일 변환 적용에 사용)
    """
    raw_dfs = load_directory(directory, max_files=max_files)

    # 죽은 VM(항상 0%)을 제거해 데이터 균형을 자연 개선
    if config.USE_ACTIVE_VM_FILTER:
        raw_dfs = filter_active_vms(raw_dfs)

    pre_dfs = [preprocess(df) for df in raw_dfs]
    scaler = fit_scaler(pre_dfs)

    X_chunks, y_chunks = [], []
    for df in pre_dfs:
        scaled = df.copy()
        scaled[FEATURE_COLS] = scaler.transform(df[FEATURE_COLS])
        X, y = to_sliding_window(scaled, window_size, horizon)
        if len(X) > 0:
            X_chunks.append(X)
            y_chunks.append(y)

    X = np.concatenate(X_chunks, axis=0)
    y = np.concatenate(y_chunks, axis=0)
    return X, y, scaler


def load_prometheus(
    query: str,
    start: float,
    end: float,
    step: str = f"{config.INFERENCE_STEP_SEC}s",
    prometheus_url: str = config.PROMETHEUS_URL,
) -> pd.DataFrame:
    """
    Prometheus /api/v1/query_range를 호출해 시계열을 DataFrame으로 반환한다.

    Args:
        query: PromQL 쿼리 (예: 'rate(container_cpu_usage_seconds_total[5m])')
        start, end: Unix epoch (초)
        step: 쿼리 해상도 (예: "300s" = 5분)

    Returns:
        DataFrame
        - index: timestamp (float, Unix epoch 초)
        - columns: 결과 시리즈별 식별자 (라벨의 'name' 우선, 없으면 라벨 dict 문자열)
        - 결과가 없으면 빈 DataFrame
    """
    response = requests.get(
        f"{prometheus_url}/api/v1/query_range",
        params={"query": query, "start": start, "end": end, "step": step},
        timeout=10,
    )
    response.raise_for_status()
    result = response.json().get("data", {}).get("result", [])
    if not result:
        return pd.DataFrame()

    series_dict = {}
    for entry in result:
        # 컨테이너별 메트릭은 보통 'name' 라벨로 구분됨
        label = entry["metric"].get("name") or str(entry["metric"])
        values = entry["values"]
        ts = [float(v[0]) for v in values]
        vals = [float(v[1]) for v in values]
        series_dict[label] = pd.Series(vals, index=ts)

    df = pd.DataFrame(series_dict).sort_index()
    df.index.name = "timestamp"
    return df


def fetch_container_window(
    container_name: str,
    window_size: int = config.WINDOW_SIZE,
    step_sec: int = config.INFERENCE_STEP_SEC,
    prometheus_url: str = config.PROMETHEUS_URL,
) -> np.ndarray:
    """
    추론용 입력 윈도우를 Prometheus에서 가져와 (1, window_size, 2) 정규화 배열로 반환한다.

    학습 데이터(Bitbrain) 단위에 맞춰 변환:
        CPU usage [%]      <- rate(container_cpu_usage_seconds_total[5m]) * 100
        Memory usage [KB]  <- container_memory_usage_bytes / 1024

    Args:
        container_name: 대상 컨테이너의 'name' 라벨 값
        window_size: 가져올 step 수 (학습과 동일하게 60)
        step_sec: 쿼리 step (학습 granularity와 일치, 기본 300s)

    Returns:
        (1, window_size, 2) shape의 정규화된 NumPy 배열
    """
    end = time.time()
    start = end - window_size * step_sec
    rate_window = f"{step_sec}s"   # rate() 윈도우는 step과 같게

    cpu_query = (
        f'rate(container_cpu_usage_seconds_total'
        f'{{name="{container_name}"}}[{rate_window}]) * 100'
    )
    mem_query = (
        f'container_memory_usage_bytes{{name="{container_name}"}} / 1024'
    )

    cpu_df = load_prometheus(cpu_query, start, end, f"{step_sec}s", prometheus_url)
    mem_df = load_prometheus(mem_query, start, end, f"{step_sec}s", prometheus_url)

    if cpu_df.empty or mem_df.empty:
        raise ValueError(
            f"insufficient prometheus data for '{container_name}' "
            f"(cpu_empty={cpu_df.empty}, mem_empty={mem_df.empty})"
        )

    # 컨테이너 1개라 컬럼은 1개. 두 시리즈를 시간 인덱스로 정렬해서 합침
    cpu_series = cpu_df.iloc[:, 0]
    mem_series = mem_df.iloc[:, 0]
    df = pd.DataFrame({CPU_COL: cpu_series, MEM_COL: mem_series})
    df = df.ffill().bfill().dropna()

    if len(df) < window_size:
        raise ValueError(
            f"not enough samples for '{container_name}': "
            f"got {len(df)}, need {window_size}"
        )

    # 마지막 window_size개만 사용 (혹시 더 많이 왔을 경우)
    df = df.iloc[-window_size:]

    # 학습 시 사용한 스케일러로 동일 변환
    scaler = load_scaler()
    scaled = scaler.transform(df[FEATURE_COLS].values)

    return scaled.reshape(1, window_size, len(FEATURE_COLS)).astype(np.float32)
