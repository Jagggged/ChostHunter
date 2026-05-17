from ai.data.loader import prometheus_rate_window


def test_prometheus_rate_window_is_never_too_narrow_for_fast_demo_steps():
    assert prometheus_rate_window(5) == "30s"


def test_prometheus_rate_window_scales_with_regular_steps():
    assert prometheus_rate_window(30) == "60s"
