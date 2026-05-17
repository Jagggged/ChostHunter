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
from ai.agent.controller import (
    limits_already_applied,
    list_managed_containers,
    update_limits,
)
from ai.agent.finetune import (
    active_model_mtime,
    ensure_active_model,
    start_finetune_scheduler,
)
from ai.agent.global_state import (
    get_finetune_settings,
    is_autopilot_enabled,
    is_finetune_enabled,
)
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
            limits = recommend_limits(pred, current_limits=current_limits)

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

            if limits_already_applied(current_limits, limits):
                record_action(
                    container_name=name,
                    policy=policy,
                    status="recommended",
                    current_limits=current_limits,
                    recommended_limits=limits,
                    reason="recommended limits already applied; no docker update",
                )
                print(f"[infer][no-op] {name}: recommend "
                      f"cpu={limits['cpu_quota']:.2f} "
                      f"mem={limits['memory_bytes']} (already applied)")
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


def sync_finetune_runtime(
    *,
    scheduler,
    model,
    model_mtime,
) -> tuple[object | None, object, float | None]:
    """Start/stop runtime fine-tuning based on persisted dashboard state."""
    if is_finetune_enabled():
        scheduler_key = _finetune_scheduler_key()
        if scheduler is not None and getattr(scheduler, "runtime_key", None) != scheduler_key:
            print("[boot] fine-tune settings changed; restarting scheduler...")
            scheduler.stop()
            scheduler = None

        if scheduler is None:
            print("[boot] preparing runtime active model...")
            ensure_active_model()
            print("[boot] loading active model for runtime fine-tuning...")
            model = load_pretrained(config.ACTIVE_MODEL_PATH)
            model_mtime = active_model_mtime()
            print("[boot] starting fine-tune scheduler...")
            scheduler = start_finetune_scheduler()

        latest_mtime = active_model_mtime()
        if latest_mtime is not None and latest_mtime != model_mtime:
            print(f"[boot] reloading active model from {config.ACTIVE_MODEL_PATH}")
            model = load_pretrained(config.ACTIVE_MODEL_PATH)
            model_mtime = latest_mtime
        return scheduler, model, model_mtime

    if scheduler is not None:
        print("[boot] stopping fine-tune scheduler...")
        scheduler.stop()
        scheduler = None
        model_mtime = None
        print(f"[boot] loading model from {config.PRETRAINED_MODEL_PATH}...")
        model = load_pretrained(config.PRETRAINED_MODEL_PATH)
    return scheduler, model, model_mtime


def _finetune_scheduler_key() -> tuple[int, int]:
    settings = get_finetune_settings()
    return (
        int(settings.get("interval_sec", config.FINETUNE_INTERVAL_SEC)),
        int(settings.get("initial_delay_sec", config.FINETUNE_INITIAL_DELAY_SEC)),
    )


def main():
    scheduler = None
    model_mtime = None
    print(f"[boot] loading model from {config.PRETRAINED_MODEL_PATH}...")
    model = load_pretrained(config.PRETRAINED_MODEL_PATH)

    api_server = None
    if config.ENABLE_CONTROL_API:
        print("[boot] starting control API...")
        api_server = start_api_server(config.CONTROL_API_HOST, config.CONTROL_API_PORT)

    print("[boot] starting watchdog...")
    watchdog = Watchdog()
    watchdog.start()

    scheduler, model, model_mtime = sync_finetune_runtime(
        scheduler=scheduler,
        model=model,
        model_mtime=model_mtime,
    )

    print(f"[boot] inference loop starts (every {config.INFERENCE_INTERVAL_SEC}s)")
    try:
        while True:
            scheduler, model, model_mtime = sync_finetune_runtime(
                scheduler=scheduler,
                model=model,
                model_mtime=model_mtime,
            )
            run_inference_cycle(model, watchdog)
            time.sleep(config.INFERENCE_INTERVAL_SEC)
    except KeyboardInterrupt:
        print("[shutdown] interrupted")
    finally:
        if scheduler is not None:
            scheduler.stop()
        watchdog.stop()
        if api_server is not None:
            api_server.shutdown()
            api_server.server_close()


if __name__ == "__main__":
    main()
