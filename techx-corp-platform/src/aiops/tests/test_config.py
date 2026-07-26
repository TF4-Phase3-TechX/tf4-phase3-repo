import pytest

from app.config import Settings, _float_map


def test_service_slo_targets_are_explicit_and_bounded(monkeypatch):
    monkeypatch.setenv("TEST_SLO_TARGETS", "frontend=0.995,checkout=0.99")
    assert _float_map("TEST_SLO_TARGETS", "") == {
        "frontend": 0.995,
        "checkout": 0.99,
    }


@pytest.mark.parametrize("value", ["checkout", "checkout=1", "checkout=0"])
def test_invalid_service_slo_target_fails_closed(monkeypatch, value):
    monkeypatch.setenv("TEST_SLO_TARGETS", value)
    with pytest.raises(ValueError):
        _float_map("TEST_SLO_TARGETS", "")


def test_burn_rate_windows_must_be_ordered():
    values = Settings().__dict__ | {
        "burn_rate_short_window_minutes": 30,
        "burn_rate_long_window_minutes": 5,
    }
    with pytest.raises(ValueError):
        Settings(**values)


@pytest.mark.parametrize("window", ["", "0s", "30", "30 seconds", "5m30s"])
def test_invalid_verification_metric_window_fails_closed(window):
    values = Settings().__dict__ | {"verification_metric_window": window}

    with pytest.raises(ValueError):
        Settings(**values)


def test_negative_verification_settle_time_fails_closed():
    values = Settings().__dict__ | {"verification_settle_seconds": -1}

    with pytest.raises(ValueError):
        Settings(**values)


def test_generic_signal_services_are_configured_separately(monkeypatch):
    monkeypatch.setenv(
        "AIOPS_GENERIC_SIGNAL_SERVICES",
        "product-reviews,frontend,cart,checkout",
    )

    settings = Settings()

    assert settings.generic_signal_services == (
        "product-reviews",
        "frontend",
        "cart",
        "checkout",
    )
    assert "llm" not in settings.generic_signal_services
