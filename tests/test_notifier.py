from ai import config
from ai.agent.notifier import _is_routine_noop_recommendation


def test_slack_default_statuses_include_limit_events():
    assert "recommended" in config.SLACK_NOTIFY_STATUSES
    assert "applied" in config.SLACK_NOTIFY_STATUSES
    assert "failed" in config.SLACK_NOTIFY_STATUSES
    assert "policy_updated" in config.SLACK_NOTIFY_STATUSES
    assert "autopilot_updated" in config.SLACK_NOTIFY_STATUSES
    assert "finetune_settings_updated" in config.SLACK_NOTIFY_STATUSES


def test_routine_noop_recommendations_are_suppressed():
    assert _is_routine_noop_recommendation({
        "status": "recommended",
        "reason": "recommended limits already applied; no docker update",
        "applied_limits": None,
    })


def test_real_limit_recommendations_are_not_suppressed():
    assert not _is_routine_noop_recommendation({
        "status": "recommended",
        "reason": "advisory policy; no docker update",
        "applied_limits": None,
    })
    assert not _is_routine_noop_recommendation({
        "status": "applied",
        "reason": None,
        "applied_limits": {"cpu_quota": 0.5, "memory_bytes": 128},
    })
