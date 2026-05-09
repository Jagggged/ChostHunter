"""
Lightweight LSTM 모델 정의 (PyTorch)
컨테이너 리소스 사용량의 시계열을 입력받아 미래 사용량을 예측한다.

Lightweight 설계 이유:
- 추론 자체가 시스템 부하가 되면 안 됨 (오버헤드 최소화)
- 2층 LSTM (64 -> 32 unit) + Linear + Softplus

출력에 Softplus를 두는 이유:
- 음수 예측(메모리/CPU 음수) 원천 차단 (출력이 항상 > 0)
- Bitbrain은 유휴(거의 0%) 데이터가 압도적이라, 모델이 0 근처를 부드럽게 예측해야 함
- Sigmoid는 saturation 영역(0, 1 근처)에서 그래디언트가 작아 학습이 느림
- ReLU는 pre-activation이 음수면 gradient=0인 dead-ReLU 문제로 학습이 멈출 수 있음
- Softplus는 ReLU의 부드러운 근사로, 어디서든 gradient > 0 → dead zone 없이 안정 학습

PyTorch를 선택한 이유:
- 동적 그래프로 Online Learning 시 학습 루프 제어가 유연함
- Watchdog 등 커스텀 로직과 통합이 용이함
"""

import torch
import torch.nn as nn

from ai import config


class LightweightLSTM(nn.Module):
    """
    2층 LSTM + Linear 출력
    Input:  (batch, window_size, n_features)
    Output: (batch, horizon, n_features)
    """

    def __init__(
        self,
        n_features: int = config.N_FEATURES,
        horizon: int = config.PREDICT_HORIZON,
        units: list[int] = config.LSTM_UNITS,
        dropout: float = config.DROPOUT_RATE,
    ):
        super().__init__()
        self.n_features = n_features
        self.horizon = horizon

        # 1층: 시퀀스 전체를 다음 LSTM에 넘겨야 하므로 return_sequences 효과
        self.lstm1 = nn.LSTM(
            input_size=n_features,
            hidden_size=units[0],
            batch_first=True,
        )
        self.dropout1 = nn.Dropout(dropout)

        # 2층: 마지막 hidden state만 사용
        self.lstm2 = nn.LSTM(
            input_size=units[0],
            hidden_size=units[1],
            batch_first=True,
        )
        self.dropout2 = nn.Dropout(dropout)

        # horizon × n_features 차원의 벡터로 한 번에 출력 (multi-step prediction)
        self.fc = nn.Linear(units[1], horizon * n_features)

        # 음수 예측 차단 (메모리/CPU는 비음수). [0, 1] 상한은 강제하지 않음.
        # Softplus: ln(1 + e^x) — 어디서든 gradient > 0 (dead zone 없음)
        self.activation = nn.Softplus()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, window_size, n_features) - 정규화된 입력 [0, 1]
        Returns:
            (batch, horizon, n_features) - 정규화된 출력 [0, 1]
        """
        # 1층 LSTM: 전체 시퀀스 출력
        out, _ = self.lstm1(x)
        out = self.dropout1(out)

        # 2층 LSTM: 마지막 hidden state만 사용
        _, (h_n, _) = self.lstm2(out)   # h_n: (1, batch, units[1])
        out = h_n.squeeze(0)            # (batch, units[1])
        out = self.dropout2(out)

        # Dense → ReLU → reshape
        out = self.fc(out)
        out = self.activation(out)
        return out.view(-1, self.horizon, self.n_features)


def build_model() -> LightweightLSTM:
    """모델 인스턴스 생성"""
    return LightweightLSTM()


def get_device() -> torch.device:
    """GPU 사용 가능하면 cuda, 아니면 cpu"""
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")
