import pytest

from tests.eval_mandate27.baseline import (
    DEFAULT_CONFIG,
    build_baseline,
    histogram,
    wilson_interval,
)
from tests.eval_mandate27.generate_fixtures import build_series


def test_baseline_is_ready_versioned_and_content_free():
    baseline = build_baseline(
        build_series("baseline"),
        created_at_utc="2026-07-30T00:00:00Z",
        git={"sha": "abc123", "dirty": False},
    )

    assert baseline["schema_version"] == "mandate27-baseline-v1"
    assert set(baseline["surfaces"]) == {"review_summary", "copilot"}
    assert baseline["surfaces"]["copilot"]["metrics"]["fallback"]["ready"]
    assert baseline["surfaces"]["review_summary"]["metrics"]["faithfulness"]["ready"]
    assert baseline["compatibility"] == {
        "model_id": "fixture-model-v1",
        "guardrail_version": "3",
        "scorer_version": "mandate14-v2",
    }
    serialized = str(baseline)
    assert "prompt" not in serialized
    assert "response" not in serialized


def test_small_baseline_is_retained_but_not_ready():
    baseline = build_baseline(
        build_series("baseline", samples_per_surface=10),
        created_at_utc="2026-07-30T00:00:00Z",
        git={"sha": "abc123", "dirty": False},
    )

    assert not baseline["surfaces"]["copilot"]["metrics"]["fallback"]["ready"]
    assert DEFAULT_CONFIG["min_baseline_samples"] == 50


def test_baseline_rejects_mixed_model_versions():
    rows = build_series("baseline")
    rows[-1]["model_id"] = "different-model"

    with pytest.raises(ValueError, match="multiple model_id"):
        build_baseline(rows)


def test_wilson_interval_and_histogram_boundaries():
    lower, upper = wilson_interval(0, 100, 2.576)
    assert lower == 0
    assert 0 < upper < 0.1
    assert histogram([0.0, 0.2, 0.99, 1.0], [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]) == [
        1,
        1,
        0,
        0,
        2,
    ]
