"""
AI 에이전트 설정값
하이퍼파라미터, 임계값, 경로 등을 한곳에서 관리한다.
"""

import os

from ai.env import load_env_file

load_env_file()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default

# ── LSTM 모델 하이퍼파라미터 ──────────────────────────────
WINDOW_SIZE = _env_int("WINDOW_SIZE", 60)          # 입력 시계열 길이 (과거 60 step)
PREDICT_HORIZON = 10      # 예측 길이 (미래 10 step)
N_FEATURES = 2            # 입력 피처 수 (CPU, Memory)
LSTM_UNITS = [64, 32]     # 2층 LSTM unit 수 (Lightweight)
DROPOUT_RATE = 0.2

# ── 학습 설정 ─────────────────────────────────────────────
BATCH_SIZE = 64
EPOCHS = 50
LEARNING_RATE = 0.001
WEIGHT_DECAY = 1e-5         # L2 정규화 (과적합 방지)
VALIDATION_SPLIT = 0.2

# Early Stopping: val_loss가 PATIENCE epoch 동안 개선되지 않으면 학습 중단
EARLY_STOPPING_PATIENCE = 10
EARLY_STOPPING_MIN_DELTA = 1e-5  # 이 값 이상 줄어야 "개선"으로 인정

# ── 데이터 불균형 대응 ────────────────────────────────────
# Bitbrain은 유휴 샘플이 압도적이라 모델이 평균값만 출력하는 model collapse가 발생.
# (1) 스파이크 샘플 오버샘플링 + (2) 가중 MSE Loss 두 축으로 해결.

# 오버샘플링: 정답 horizon의 max CPU%가 이 값 이상이면 "스파이크"로 분류
SPIKE_CPU_THRESHOLD_PCT = 10.0
USE_OVERSAMPLING = True       # False로 두면 원본 분포 그대로 학습
MAX_OVERSAMPLE_RATIO = 5      # 스파이크 샘플 1개당 최대 5배까지만 복제 (메모리 보호)

# 가중 MSE Loss: 정규화된 정답값에 가중치를 둬서 큰 값(스파이크)의 오차에 더 페널티
USE_WEIGHTED_LOSS = True
WEIGHTED_LOSS_ALPHA = 10.0    # weight = 1 + alpha * normalized_target. 클수록 스파이크 강조

# ── 활성 VM 필터링 ────────────────────────────────────────
# Bitbrain은 항상 0%인 "죽은 VM"이 다수 포함되어 있어 학습 신호를 흐림.
# CPU max나 표준편차가 임계 이상인 VM만 골라서 학습하면 데이터 균형이 자연 개선됨.
USE_ACTIVE_VM_FILTER = True
ACTIVE_VM_MIN_CPU_MAX = 10.0  # CPU max가 이 % 이상인 VM만 사용
ACTIVE_VM_MIN_CPU_STD = 1.0   # 또는 표준편차가 이 값 이상인 VM (둘 중 하나만 만족하면 OK)

# ── Online Learning (Fine-tuning) ────────────────────────
ENABLE_ONLINE_FINETUNE = _env_bool("ENABLE_ONLINE_FINETUNE", False)
FINETUNE_INTERVAL_SEC = _env_int("FINETUNE_INTERVAL_SEC", 6 * 60 * 60)
FINETUNE_INITIAL_DELAY_SEC = _env_int("FINETUNE_INITIAL_DELAY_SEC", 5 * 60)
FINETUNE_EPOCHS = _env_int("FINETUNE_EPOCHS", 2)
FINETUNE_HISTORY_SEC = _env_int("FINETUNE_HISTORY_SEC", 6 * 60 * 60)
FINETUNE_MAX_CONTAINERS = _env_int("FINETUNE_MAX_CONTAINERS", 3)
FINETUNE_MIN_SAMPLES = _env_int("FINETUNE_MIN_SAMPLES", 32)
FINETUNE_MAX_SAMPLES = _env_int("FINETUNE_MAX_SAMPLES", 512)
FINETUNE_VALIDATION_SPLIT = _env_float("FINETUNE_VALIDATION_SPLIT", 0.2)
FINETUNE_CPU_THREADS = _env_int("FINETUNE_CPU_THREADS", 1)
FINETUNE_MAX_DURATION_SEC = _env_int("FINETUNE_MAX_DURATION_SEC", 120)
FINETUNE_MIN_IMPROVEMENT = _env_float("FINETUNE_MIN_IMPROVEMENT", 0.0)
FINETUNE_AUTO_PROMOTE = _env_bool("FINETUNE_AUTO_PROMOTE", True)
FINETUNE_SKIP_CPU_THRESHOLD = _env_float("FINETUNE_SKIP_CPU_THRESHOLD", 0.85)
FINETUNE_SKIP_MEMORY_THRESHOLD = _env_float("FINETUNE_SKIP_MEMORY_THRESHOLD", 0.85)

# ── 추론 설정 ─────────────────────────────────────────────
# 데모용으로 짧게 설정. 운영에서는 학습 단위(5분)에 맞춰 INTERVAL=300, STEP=300 권장.
INFERENCE_INTERVAL_SEC = _env_int("INFERENCE_INTERVAL_SEC", 60)     # 1분마다 추론 사이클
INFERENCE_STEP_SEC = _env_int("INFERENCE_STEP_SEC", 30)         # Prometheus 쿼리 step (60 step × 30s = 30분치 윈도우)

# torch.compile JIT 가속 활성화 여부.
# - True: 첫 호출 시 컴파일 오버헤드(10~30s) 후 추론 빨라짐
# - False: eager mode (기본). Windows/디버깅 시 안전
# 환경에서 측정 후 효과 있으면 True로 변경.
USE_TORCH_COMPILE = False

# ── 안전 장치 ─────────────────────────────────────────────
SAFETY_BUFFER = 0.30            # 예측값 위에 30% 버퍼
MIN_CPU_QUOTA = 0.1             # 최소 CPU (코어 단위)
MIN_MEMORY_BYTES = 64 * 1024 * 1024  # 최소 메모리 64MB
MAX_CPU_QUOTA = _env_float("MAX_CPU_QUOTA", 4.0)
MAX_MEMORY_BYTES = _env_int("MAX_MEMORY_BYTES", 2 * 1024 * 1024 * 1024)
MAX_LIMIT_INCREASE_RATIO = _env_float("MAX_LIMIT_INCREASE_RATIO", 1.0)
CPU_QUOTA_STEP = _env_float("CPU_QUOTA_STEP", 0.01)
MEMORY_STEP_BYTES = _env_int("MEMORY_STEP_BYTES", 16 * 1024 * 1024)

# ── Watchdog (비상 롤백) ──────────────────────────────────
WATCHDOG_INTERVAL_SEC = 1       # 1초마다 사용률 체크
WATCHDOG_THRESHOLD = 0.90       # 사용률 90% 초과 시 롤백

# ── 외부 연동 ─────────────────────────────────────────────
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "")  # 비워두면 docker.from_env()로 자동 감지 (Windows: named pipe, Linux: unix socket).
# 운영(Linux 서버)에서 명시 강제하려면 "unix://var/run/docker.sock" 사용.

# ── Control API ───────────────────────────────────────────
ENABLE_CONTROL_API = os.getenv("ENABLE_CONTROL_API", "true").lower() == "true"
CONTROL_API_HOST = os.getenv("CONTROL_API_HOST", "127.0.0.1")
CONTROL_API_PORT = int(os.getenv("CONTROL_API_PORT", "8000"))

# ── 컨테이너 라벨 정책 ─────────────────────────────────────
# 운영자가 컨테이너에 라벨을 붙여 AI 동작을 제어할 수 있다.
#
#   chost-hunter.skip=true            → 완전 무시 (감시/적용 둘 다 X)
#   chost-hunter.policy=skip          → skip=true와 동일
#   chost-hunter.policy=advisory      → 권고만 출력, 실제 docker update X
#   chost-hunter.policy=auto          → 자동 적용 (기본값)
#   라벨 없음                          → DEFAULT_POLICY가 적용됨
#
# 신규 도입 시 안전을 위해 advisory를 기본으로 하고 검증 후 auto로 전환 가능.
LABEL_PREFIX = "chost-hunter"
DEFAULT_POLICY = "auto"  # "auto" | "advisory"
ADVISORY_FOR_UNLABELED_UNLIMITED = True
# DEFAULT_POLICY가 auto여도 cpu_quota=0 또는 memory=0인 라벨 없는 컨테이너는
# advisory로 처리한다. 운영자가 명시적으로 chost-hunter.policy=auto를 붙인
# 경우에만 AI가 unlimited 컨테이너에 최초 limit을 생성한다.

# 인프라 컨테이너(우리가 띄운 모니터링 스택)는 항상 무시한다.
# 라벨로 관리하기 어려운 외부 이미지(prom/grafana/cadvisor)를 위한 안전망.
INFRA_CONTAINER_NAMES = ["cadvisor", "prometheus", "grafana", "ai-agent", "alertmanager"]

# ── 경로 ──────────────────────────────────────────────────
MODEL_DIR = "models"
PRETRAINED_MODEL_PATH = f"{MODEL_DIR}/pretrained.pt"
RUNTIME_MODEL_DIR = f"{MODEL_DIR}/runtime"
ACTIVE_MODEL_PATH = f"{RUNTIME_MODEL_DIR}/active.pt"
CANDIDATE_MODEL_DIR = f"{RUNTIME_MODEL_DIR}/candidates"
SCALER_PATH = f"{MODEL_DIR}/scaler.pkl"
TRAINING_HISTORY_PATH = f"{MODEL_DIR}/training_history.json"
TRAINING_CURVE_PATH = f"{MODEL_DIR}/training_curve.png"
LOG_DIR = "logs"
ACTION_LOG_PATH = f"{LOG_DIR}/actions.jsonl"
FINETUNE_RUN_LOG_PATH = f"{LOG_DIR}/finetune_runs.jsonl"
POLICY_OVERRIDE_PATH = f"{LOG_DIR}/policy_overrides.json"
GLOBAL_STATE_PATH = f"{LOG_DIR}/global_state.json"
NOTIFICATION_LOG_PATH = f"{LOG_DIR}/notifications.jsonl"
SETTINGS_PATH = f"{LOG_DIR}/settings.json"

# ── Slack notifications ───────────────────────────────────
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_NOTIFY_ENABLED = os.getenv("SLACK_NOTIFY_ENABLED", "true").lower() == "true"
SLACK_NOTIFY_STATUSES = {
    "recommended",
    "applied",
    "failed",
    "policy_updated",
    "autopilot_updated",
    "finetune_updated",
    "finetune_settings_updated",
    "notification_test",
    "rollback_failed",
    "rolled_back",
}
SLACK_TIMEOUT_SEC = 5
