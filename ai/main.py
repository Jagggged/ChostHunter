"""
AI 에이전트 진입점
사전학습 모델을 로드하고 추론 루프 + Watchdog을 실행한다.

실행 흐름:
1. Pretrained 모델 로드 + Watchdog 스레드 시작
2. 추론 루프 (INFERENCE_INTERVAL_SEC마다):
   - 대상 컨테이너 목록 조회
   - 각 컨테이너에 대해:
     a. Prometheus에서 최근 윈도우 조회 (정규화)
     b. LSTM 추론 -> 정규화 해제 -> 권고 limit 산출
     c. 이전 limit을 Watchdog에 등록 (롤백 대비)
     d. docker update로 limit 적용
3. (선택) FINETUNE_INTERVAL_SEC마다 Fine-tuning

운영 데이터로 윈도우를 가져오는 부분(fetch_recent_window)은
loader.load_prometheus 구현 이후 채워 넣는다.
"""

import time
import traceback

from ai import config
from ai.agent.action_log import record_action
from ai.agent.api import start_api_server
from ai.agent.controller import list_managed_containers, update_limits
from ai.agent.global_state import is_autopilot_enabled
from ai.agent.predictor import (
    inverse_scale,
    load_pretrained,
    predict,
    recommend_limits,
)
from ai.agent.watchdog import Watchdog
from ai.data.loader import fetch_container_window


def run_inference_cycle(model, watchdog: Watchdog) -> None:
    """추론 1 사이클: 대상 컨테이너 전체 처리."""
    for target in list_managed_containers(include_skipped=True):
        name = target["name"]
        policy = target["policy"]
        current_limits = target.get("limits")
        try:
            if policy == "skip":
                record_action(
                    container_name=name,
                    policy=policy,
                    status="skipped",
                    current_limits=current_limits,
                    reason="container policy is skip",
                )
                continue

            window = fetch_container_window(name)
            pred_scaled = predict(model, window)
            pred = inverse_scale(pred_scaled)
            limits = recommend_limits(pred)

            if policy == "advisory":
                record_action(
                    container_name=name,
                    policy=policy,
                    status="recommended",
                    current_limits=current_limits,
                    recommended_limits=limits,
                    reason="advisory policy; no docker update",
                )
                print(f"[infer][advisory] {name}: recommend "
                      f"cpu={limits['cpu_quota']:.2f} "
                      f"mem={limits['memory_bytes']} "
                      f"(current={target.get('limits')}, no docker update)")
                continue

            if policy != "auto":
                record_action(
                    container_name=name,
                    policy=policy,
                    status="skipped",
                    current_limits=current_limits,
                    recommended_limits=limits,
                    reason=f"unsupported policy '{policy}'",
                )
                print(f"[infer][skip] {name}: unsupported policy '{policy}'")
                continue

            if not is_autopilot_enabled():
                record_action(
                    container_name=name,
                    policy=policy,
                    status="recommended",
                    current_limits=current_limits,
                    recommended_limits=limits,
                    reason="global autopilot disabled; no docker update",
                )
                print(f"[infer][autopilot-off] {name}: recommend "
                      f"cpu={limits['cpu_quota']:.2f} "
                      f"mem={limits['memory_bytes']} (no docker update)")
                continue

            prev = current_limits or {}
            watchdog.register(name, prev)
            try:
                applied_prev = update_limits(name, **limits)
            except Exception:
                watchdog.unregister(name)
                raise

            if applied_prev != prev:
                watchdog.register(name, applied_prev)
                prev = applied_prev

            print(f"[infer][auto] {name}: applied "
                  f"cpu={limits['cpu_quota']:.2f} "
                  f"mem={limits['memory_bytes']} (prev={prev})")
            record_action(
                container_name=name,
                policy=policy,
                status="applied",
                current_limits=current_limits,
                recommended_limits=limits,
                applied_limits=limits,
                previous_limits=prev,
            )
        except ValueError as e:
            # 데이터 부족 등 예상된 실패 - 다음 사이클에 다시 시도
            record_action(
                container_name=name,
                policy=policy,
                status="skipped",
                current_limits=current_limits,
                reason=str(e),
            )
            print(f"[infer] skipped {name}: {e}")
        except Exception as e:
            record_action(
                container_name=name,
                policy=policy,
                status="failed",
                current_limits=current_limits,
                error=str(e),
            )
            print(f"[infer] error for {name}:")
            traceback.print_exc()


def main():
    print("[boot] loading pretrained model...")
    model = load_pretrained()

    api_server = None
    if config.ENABLE_CONTROL_API:
        print("[boot] starting control API...")
        api_server = start_api_server(config.CONTROL_API_HOST, config.CONTROL_API_PORT)

    print("[boot] starting watchdog...")
    watchdog = Watchdog()
    watchdog.start()

    print(f"[boot] inference loop starts (every {config.INFERENCE_INTERVAL_SEC}s)")
    try:
        while True:
            run_inference_cycle(model, watchdog)
            time.sleep(config.INFERENCE_INTERVAL_SEC)
    except KeyboardInterrupt:
        print("[shutdown] interrupted")
    finally:
        watchdog.stop()
        if api_server is not None:
            api_server.shutdown()
            api_server.server_close()


if __name__ == "__main__":
    main()
