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


def test_settle_shorter_than_metric_window_fails_closed():
    values = Settings().__dict__ | {
        "verification_metric_window": "2m",
        "verification_settle_seconds": 60,
    }

    with pytest.raises(ValueError, match="settle seconds must be >="):
        Settings(**values)


def test_zero_settle_allowed_for_offline_replay():
    settings = Settings(**(Settings().__dict__ | {"verification_settle_seconds": 0}))
    assert settings.verification_settle_seconds == 0


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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rca_timeout_seconds", float("nan")),
        ("rca_timeout_seconds", float("inf")),
        ("rca_analysis_window_seconds", float("nan")),
        ("rca_analysis_window_seconds", float("inf")),
        ("rca_temporal_tolerance_seconds", float("nan")),
        ("rca_temporal_tolerance_seconds", float("inf")),
    ],
)
def test_non_finite_rca_runtime_settings_fail_at_startup(field, value):
    values = Settings().__dict__ | {field: value}

    with pytest.raises(ValueError, match="must be finite"):
        Settings(**values)


def test_live_autonomous_mode_requires_durable_saga_backend():
    values = Settings().__dict__ | {
        "remediation_mode": "gitops/live",
        "autonomous_remediation_enabled": True,
        "saga_backend": "memory",
    }

    with pytest.raises(ValueError, match="requires a durable saga backend"):
        Settings(**values)


def test_dual_token_demo_requires_explicit_distinct_identities():
    values = Settings().__dict__ | {
        "github_auth_mode": "token-files",
        "gitops_merge_strategy": "dual-token",
        "timeboxed_demo_acknowledged": True,
        "github_creator_login": "creator",
        "github_reviewer_login": "reviewer",
    }
    configured = Settings(**values)
    assert configured.gitops_merge_strategy == "dual-token"

    with pytest.raises(ValueError, match="must be different"):
        Settings(**(values | {"github_reviewer_login": "creator"}))


def test_dual_token_demo_fails_closed_without_acknowledgement():
    values = Settings().__dict__ | {
        "github_auth_mode": "token-files",
        "gitops_merge_strategy": "dual-token",
        "timeboxed_demo_acknowledged": False,
        "github_creator_login": "creator",
        "github_reviewer_login": "reviewer",
    }
    with pytest.raises(ValueError, match="time-boxed demo acknowledgement"):
        Settings(**values)
