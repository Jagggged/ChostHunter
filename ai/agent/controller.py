"""
Docker 컨테이너 리소스 제어
Docker SDK for Python을 통해 컨테이너의 cpu_quota, mem_limit을 동적으로 조정한다.
CLI 호출(docker update) 대신 SDK를 쓰는 이유는 안정성/에러 핸들링이 좋기 때문이다.

CPU quota 변환:
    Docker는 CPU를 'cpu_quota / cpu_period' 비율로 제한한다.
    cpu_period 기본값은 100000 (100ms 단위), 따라서 1코어 = 100000 quota.
    예: cpu_quota=0.5 코어 → 50000 quota
"""

import docker
from docker.errors import NotFound

from ai import config
from ai.agent.policy_store import get_policy_override


CPU_PERIOD_DEFAULT = 100000   # Docker 기본 CPU period (us)


_client = None


def get_client() -> docker.DockerClient:
    """
    Docker 클라이언트 싱글톤.

    DOCKER_SOCKET이 명시되어 있으면 그 경로(Linux 운영용)를 사용하고,
    비어 있으면 docker.from_env()로 환경 자동 감지 (Windows/Mac Docker Desktop은
    named pipe, Linux는 unix socket을 자동 선택).
    """
    global _client
    if _client is None:
        if config.DOCKER_SOCKET:
            _client = docker.DockerClient(base_url=config.DOCKER_SOCKET)
        else:
            _client = docker.from_env()
    return _client


def update_limits(container_name: str, cpu_quota: float, memory_bytes: int) -> dict:
    """
    컨테이너 리소스 limit을 갱신한다.
    적용 전 limit을 반환하여 Watchdog이 롤백 시 사용한다.

    Args:
        container_name: 대상 컨테이너 이름
        cpu_quota: CPU 코어 단위 (예: 0.5 = 반 코어)
        memory_bytes: 메모리 limit (bytes)

    Returns:
        이전 설정값 (롤백용) {"cpu_quota": int(us), "memory_bytes": int}
    """
    client = get_client()
    container = client.containers.get(container_name)

    prev = _extract_limits(container)

    new_cpu_quota = int(cpu_quota * CPU_PERIOD_DEFAULT)
    nano_cpus = _extract_nano_cpus(container)
    if nano_cpus > 0:
        _update_nano_cpu_limits(
            client,
            container,
            nano_cpus=int(cpu_quota * 1_000_000_000),
            memory_bytes=memory_bytes,
        )
        return prev

    # memswap을 mem_limit과 같게 설정해야 Docker가 거부하지 않음
    # (Docker 규칙: memswap_limit >= mem_limit 필수)
    container.update(
        cpu_quota=new_cpu_quota,
        mem_limit=memory_bytes,
        memswap_limit=memory_bytes,
    )
    return prev


def get_container_limits(container_name: str) -> dict:
    """
    Return the container's current Docker resource limits.

    Docker uses 0 for an unlimited CPU quota or memory limit. The policy layer
    treats unlabeled unlimited containers conservatively because the operator may
    have left them unlimited on purpose.
    """
    client = get_client()
    container = client.containers.get(container_name)
    return _extract_limits(container)


def container_exists(container_name: str) -> bool:
    """Return whether a Docker container exists."""
    try:
        get_client().containers.get(container_name)
    except NotFound:
        return False
    return True


def limits_already_applied(
    current_limits: dict | None,
    recommended_limits: dict,
    cpu_tolerance: float = 0.005,
    memory_tolerance_bytes: int = 1024 * 1024,
) -> bool:
    """Return whether a recommendation is close enough to the current limits."""
    if not current_limits:
        return False

    current_cpu = _limits_cpu_cores(current_limits)
    recommended_cpu = float(recommended_limits.get("cpu_quota", 0) or 0)
    current_memory = int(current_limits.get("memory_bytes", 0) or 0)
    recommended_memory = int(recommended_limits.get("memory_bytes", 0) or 0)

    if current_cpu <= 0 or current_memory <= 0:
        return False
    return (
        abs(current_cpu - recommended_cpu) <= cpu_tolerance
        and abs(current_memory - recommended_memory) <= memory_tolerance_bytes
    )


def _extract_limits(container) -> dict:
    """Extract current limit values from Docker's HostConfig."""
    host_config = container.attrs["HostConfig"]
    cpu_quota = host_config.get("CpuQuota", 0)
    nano_cpus = host_config.get("NanoCpus", 0) or 0
    if cpu_quota <= 0 and nano_cpus > 0:
        cpu_quota = int((nano_cpus / 1_000_000_000) * CPU_PERIOD_DEFAULT)
    limits = {
        "cpu_quota": cpu_quota,
        "memory_bytes": host_config.get("Memory", 0),
    }
    if nano_cpus > 0:
        limits["nano_cpus"] = nano_cpus
    return limits


def _limits_cpu_cores(limits: dict) -> float:
    nano_cpus = int(limits.get("nano_cpus", 0) or 0)
    if nano_cpus > 0:
        return nano_cpus / 1_000_000_000
    cpu_quota = float(limits.get("cpu_quota", 0) or 0)
    if cpu_quota > 0:
        return cpu_quota / CPU_PERIOD_DEFAULT
    return 0.0


def _extract_nano_cpus(container) -> int:
    """Return Docker NanoCpus when the container was created with --cpus."""
    return int(container.attrs["HostConfig"].get("NanoCpus", 0) or 0)


def _update_nano_cpu_limits(
    client,
    container,
    *,
    nano_cpus: int,
    memory_bytes: int,
) -> None:
    """Update containers that use Docker's NanoCpus limit mode."""
    response = client.api._post_json(
        client.api._url("/containers/{0}/update", container.id),
        data={
            "NanoCpus": nano_cpus,
            "Memory": memory_bytes,
            "MemorySwap": memory_bytes,
        },
    )
    client.api._raise_for_status(response)


def _has_unlimited_limit(limits: dict) -> bool:
    """Docker limit value 0 means unlimited; either unlimited dimension is risky."""
    return limits.get("cpu_quota", 0) <= 0 or limits.get("memory_bytes", 0) <= 0


def rollback_limits(container_name: str, prev: dict) -> None:
    """
    이전 limit으로 즉시 복구한다 (Watchdog에서 호출).

    주의: Docker는 mem_limit=0을 "0 bytes"로 해석해 거부한다("Minimum memory limit allowed is 6MB").
    원래 unlimited(0)였던 컨테이너로 되돌릴 때는 -1을 보내야 한다.
    cpu_quota=-1은 quota 해제(unlimited)를 의미한다.
    """
    client = get_client()
    container = client.containers.get(container_name)

    prev_cpu = prev.get("cpu_quota", 0)
    prev_mem = prev.get("memory_bytes", 0)

    # 0(unlimited)이면 -1로 변환해서 Docker에게 "제한 해제"를 명시
    cpu_quota = prev_cpu if prev_cpu > 0 else -1
    mem_limit = prev_mem if prev_mem > 0 else -1

    container.update(
        cpu_quota=cpu_quota,
        mem_limit=mem_limit,
        memswap_limit=mem_limit,
    )


def get_current_usage(container_name: str) -> dict:
    """
    현재 컨테이너의 실시간 사용량 (Watchdog용).
    Prometheus를 거치지 않고 Docker에서 직접 읽어 지연을 최소화한다.

    Returns:
        {"cpu_pct": float (0~1), "mem_pct": float (0~1)}
        limit이 없으면 mem_pct는 0으로 반환.
    """
    client = get_client()
    container = client.containers.get(container_name)
    stats = container.stats(stream=False)

    # CPU 사용률 계산: Docker stats 공식
    cpu_delta = (stats["cpu_stats"]["cpu_usage"]["total_usage"]
                 - stats["precpu_stats"]["cpu_usage"]["total_usage"])
    system_delta = (stats["cpu_stats"]["system_cpu_usage"]
                    - stats["precpu_stats"].get("system_cpu_usage", 0))
    online_cpus = stats["cpu_stats"].get("online_cpus", 1) or 1

    cpu_pct = 0.0
    if system_delta > 0 and cpu_delta > 0:
        cpu_pct = (cpu_delta / system_delta) * online_cpus

    # 메모리 사용률
    mem_usage = stats["memory_stats"].get("usage", 0)
    mem_limit = stats["memory_stats"].get("limit", 0)
    mem_pct = (mem_usage / mem_limit) if mem_limit > 0 else 0.0

    return {"cpu_pct": cpu_pct, "mem_pct": mem_pct}


def _resolve_policy(container, limits: dict | None = None) -> str:
    """
    컨테이너 라벨을 보고 적용할 정책(auto/advisory/skip)을 결정한다.

    우선순위:
    1. chost-hunter.skip=true → "skip"
    2. chost-hunter.policy=<value> → 해당 값 (skip/advisory/auto)
    3. 라벨 없음 → config.DEFAULT_POLICY
    잘못된 값은 안전한 advisory로 강등.
    """
    labels = container.labels or {}
    override = get_policy_override(container.name)
    if override is not None:
        return override

    skip_flag = labels.get(f"{config.LABEL_PREFIX}.skip", "").strip().lower()
    if skip_flag == "true":
        return "skip"

    policy = labels.get(f"{config.LABEL_PREFIX}.policy", "").strip().lower()
    if policy == "skip":
        return "skip"

    if policy in ("skip", "advisory", "auto"):
        return policy
    if policy:
        # 알 수 없는 값이 들어오면 운영자 의도를 알 수 없으므로 안전하게 advisory
        print(f"[policy] unknown policy '{policy}' on {container.name}, falling back to advisory")
        return "advisory"
    if limits is None:
        limits = _extract_limits(container)
    if config.ADVISORY_FOR_UNLABELED_UNLIMITED and _has_unlimited_limit(limits):
        print(f"[policy] {container.name}: unlimited container without label -> advisory")
        return "advisory"

    return config.DEFAULT_POLICY


def list_managed_containers(
    infra_exclude: list[str] = None,
    include_skipped: bool = False,
) -> list[dict]:
    """
    감시 대상 컨테이너와 정책을 함께 반환한다.

    Returns:
        [{"name": str, "policy": "auto" | "advisory"}, ...]
        skip 정책 컨테이너는 결과에 포함되지 않는다.

    인프라 컨테이너(라벨을 못 거는 외부 이미지)는 infra_exclude로 차단한다.
    """
    if infra_exclude is None:
        infra_exclude = config.INFRA_CONTAINER_NAMES
    client = get_client()
    result = []
    for c in client.containers.list():
        if c.name in infra_exclude:
            continue
        limits = _extract_limits(c)
        policy = _resolve_policy(c, limits)
        policy_source = "override" if get_policy_override(c.name) == policy else "label-or-default"
        if policy == "skip":
            print(f"[infer][skip] {c.name}: skipped by policy")
            if include_skipped:
                result.append({
                    "name": c.name,
                    "policy": policy,
                    "policy_source": policy_source,
                    "limits": limits,
                })
            continue
        result.append({
            "name": c.name,
            "policy": policy,
            "policy_source": policy_source,
            "limits": limits,
        })
    return result


def list_target_containers(exclude: list[str] = None) -> list[str]:
    """
    하위 호환용. 새 코드는 list_managed_containers()를 사용할 것.
    advisory 컨테이너도 이름은 반환되지만 정책 정보는 사라진다.
    """
    if exclude is None:
        exclude = config.INFRA_CONTAINER_NAMES
    return [c["name"] for c in list_managed_containers(exclude)]
