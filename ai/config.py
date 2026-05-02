"""
AI 에이전트 설정값
하이퍼파라미터, 임계값, 경로 등을 한곳에서 관리한다.
"""

# ── LSTM 모델 하이퍼파라미터 ──────────────────────────────
WINDOW_SIZE = 60          # 입력 시계열 길이 (과거 60 step)
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
FINETUNE_INTERVAL_SEC = 3600   # 1시간마다 fine-tune
FINETUNE_EPOCHS = 5             # fine-tune 시 적은 epoch

# ── 추론 설정 ─────────────────────────────────────────────
# 데모용으로 짧게 설정. 운영에서는 학습 단위(5분)에 맞춰 INTERVAL=300, STEP=300 권장.
INFERENCE_INTERVAL_SEC = 60     # 1분마다 추론 사이클
INFERENCE_STEP_SEC = 30         # Prometheus 쿼리 step (60 step × 30s = 30분치 윈도우)

# torch.compile JIT 가속 활성화 여부.
# - True: 첫 호출 시 컴파일 오버헤드(10~30s) 후 추론 빨라짐
# - False: eager mode (기본). Windows/디버깅 시 안전
# 환경에서 측정 후 효과 있으면 True로 변경.
USE_TORCH_COMPILE = False

# ── 안전 장치 ─────────────────────────────────────────────
SAFETY_BUFFER = 0.30            # 예측값 위에 30% 버퍼
MIN_CPU_QUOTA = 0.1             # 최소 CPU (코어 단위)
MIN_MEMORY_BYTES = 64 * 1024 * 1024  # 최소 메모리 64MB

# ── Watchdog (비상 롤백) ──────────────────────────────────
WATCHDOG_INTERVAL_SEC = 1       # 1초마다 사용률 체크
WATCHDOG_THRESHOLD = 0.90       # 사용률 90% 초과 시 롤백

# ── 외부 연동 ─────────────────────────────────────────────
PROMETHEUS_URL = "http://localhost:9090"
DOCKER_SOCKET = ""  # 비워두면 docker.from_env()로 자동 감지 (Windows: named pipe, Linux: unix socket).
# 운영(Linux 서버)에서 명시 강제하려면 "unix://var/run/docker.sock" 사용.

# ── 경로 ──────────────────────────────────────────────────
MODEL_DIR = "models"
PRETRAINED_MODEL_PATH = f"{MODEL_DIR}/pretrained.pt"
SCALER_PATH = f"{MODEL_DIR}/scaler.pkl"
TRAINING_HISTORY_PATH = f"{MODEL_DIR}/training_history.json"
TRAINING_CURVE_PATH = f"{MODEL_DIR}/training_curve.png"
