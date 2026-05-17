import importlib

from ai import config as config_module


def test_online_finetune_default_is_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_ONLINE_FINETUNE", raising=False)

    config = importlib.reload(config_module)

    assert config.ENABLE_ONLINE_FINETUNE is False


def test_online_finetune_can_be_enabled_from_env(monkeypatch):
    monkeypatch.setenv("ENABLE_ONLINE_FINETUNE", "true")

    config = importlib.reload(config_module)

    assert config.ENABLE_ONLINE_FINETUNE is True

    monkeypatch.delenv("ENABLE_ONLINE_FINETUNE", raising=False)
    importlib.reload(config_module)


def test_finetune_thresholds_can_be_overridden_from_env(monkeypatch):
    monkeypatch.setenv("FINETUNE_MIN_SAMPLES", "8")
    monkeypatch.setenv("FINETUNE_VALIDATION_SPLIT", "0.25")

    config = importlib.reload(config_module)

    assert config.FINETUNE_MIN_SAMPLES == 8
    assert config.FINETUNE_VALIDATION_SPLIT == 0.25

    monkeypatch.delenv("FINETUNE_MIN_SAMPLES", raising=False)
    monkeypatch.delenv("FINETUNE_VALIDATION_SPLIT", raising=False)
    importlib.reload(config_module)


def test_invalid_finetune_env_values_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("FINETUNE_MIN_SAMPLES", "many")
    monkeypatch.setenv("FINETUNE_VALIDATION_SPLIT", "wide")

    config = importlib.reload(config_module)

    assert config.FINETUNE_MIN_SAMPLES == 32
    assert config.FINETUNE_VALIDATION_SPLIT == 0.2

    monkeypatch.delenv("FINETUNE_MIN_SAMPLES", raising=False)
    monkeypatch.delenv("FINETUNE_VALIDATION_SPLIT", raising=False)
    importlib.reload(config_module)


def test_inference_window_settings_can_be_overridden_from_env(monkeypatch):
    monkeypatch.setenv("WINDOW_SIZE", "8")
    monkeypatch.setenv("INFERENCE_STEP_SEC", "5")
    monkeypatch.setenv("INFERENCE_INTERVAL_SEC", "10")

    config = importlib.reload(config_module)

    assert config.WINDOW_SIZE == 8
    assert config.INFERENCE_STEP_SEC == 5
    assert config.INFERENCE_INTERVAL_SEC == 10

    monkeypatch.delenv("WINDOW_SIZE", raising=False)
    monkeypatch.delenv("INFERENCE_STEP_SEC", raising=False)
    monkeypatch.delenv("INFERENCE_INTERVAL_SEC", raising=False)
    importlib.reload(config_module)


def test_watchdog_settings_can_be_overridden_from_env(monkeypatch):
    monkeypatch.setenv("WATCHDOG_INTERVAL_SEC", "0.2")
    monkeypatch.setenv("WATCHDOG_THRESHOLD", "0.5")

    config = importlib.reload(config_module)

    assert config.WATCHDOG_INTERVAL_SEC == 0.2
    assert config.WATCHDOG_THRESHOLD == 0.5

    monkeypatch.delenv("WATCHDOG_INTERVAL_SEC", raising=False)
    monkeypatch.delenv("WATCHDOG_THRESHOLD", raising=False)
    importlib.reload(config_module)
