from ai.agent.global_state import (
    get_finetune_settings,
    is_finetune_enabled,
    read_global_state,
    set_finetune_enabled,
    update_finetune_settings,
)


def test_finetune_state_can_be_enabled_and_disabled(tmp_path, monkeypatch):
    path = tmp_path / "global_state.json"

    enabled = set_finetune_enabled(True, path=str(path))
    assert enabled["finetune_enabled"] is True
    assert read_global_state(path=str(path))["finetune_enabled"] is True

    disabled = set_finetune_enabled(False, path=str(path))
    assert disabled["finetune_enabled"] is False
    assert read_global_state(path=str(path))["finetune_enabled"] is False


def test_is_finetune_enabled_reads_persisted_state(tmp_path, monkeypatch):
    path = tmp_path / "global_state.json"
    set_finetune_enabled(True, path=str(path))
    monkeypatch.setattr(
        "ai.agent.global_state.read_global_state",
        lambda: read_global_state(path=str(path)),
    )

    assert is_finetune_enabled() is True


def test_finetune_settings_are_merged_with_defaults(tmp_path):
    path = tmp_path / "global_state.json"

    settings = update_finetune_settings(
        {
            "interval_sec": 42,
            "target_containers": ["api"],
            "unknown": "ignored",
        },
        path=str(path),
    )

    assert settings["interval_sec"] == 42
    assert settings["target_containers"] == ["api"]
    assert "unknown" not in settings

    persisted = get_finetune_settings(path=str(path))
    assert persisted["interval_sec"] == 42
    assert persisted["target_containers"] == ["api"]
    assert "history_sec" in persisted
