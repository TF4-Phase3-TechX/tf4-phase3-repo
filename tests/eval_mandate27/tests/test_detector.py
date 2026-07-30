from copy import deepcopy

from tests.eval_mandate27.baseline import build_baseline
from tests.eval_mandate27.detector import (
    detect,
    jensen_shannon_divergence,
)
from tests.eval_mandate27.generate_fixtures import build_series


def baseline():
    return build_baseline(
        build_series("baseline"),
        created_at_utc="2026-07-30T00:00:00Z",
        git={"sha": "baseline", "dirty": False},
    )


def run(name, samples=120):
    return detect(
        build_series(name, samples_per_surface=samples),
        baseline(),
        generated_at_utc="2026-07-30T03:00:00Z",
        git={"sha": "candidate", "dirty": False},
    )


def test_stable_series_has_no_false_flag():
    report = run("stable")

    assert report["status"] == "no_drift"
    assert report["signals"] == []
    assert {window["state"] for window in report["windows"]} == {"normal"}


def test_seasonal_stable_series_has_no_false_flag():
    report = run("seasonal_stable")

    assert report["status"] == "no_drift"
    assert report["signals"] == []


def test_transient_spike_does_not_become_drift():
    report = run("transient_spike")

    assert report["status"] == "no_drift"
    assert report["signals"] == []


def test_copilot_fallback_shift_names_exact_surface_and_metric():
    report = run("shifted_copilot_fallback")

    assert report["status"] == "drift"
    assert [
        (signal["surface"], signal["metric"])
        for signal in report["signals"]
    ] == [("copilot", "fallback_rate")]
    signal = report["signals"][0]
    assert signal["detected_at"] >= "2026-07-30T01:00:00Z"
    assert signal["consecutive_breaches"] == 2


def test_review_faithfulness_shift_does_not_flag_copilot():
    report = run("shifted_review_faithfulness")

    assert report["status"] == "drift"
    assert [
        (signal["surface"], signal["metric"])
        for signal in report["signals"]
    ] == [("review_summary", "faithfulness")]


def test_short_current_series_reports_warming_up():
    report = run("stable", samples=10)

    assert report["status"] == "warming_up"
    assert report["signals"] == []
    assert all(
        diagnostic["code"] == "current_window_warming_up"
        for diagnostic in report["diagnostics"]
    )


def test_insufficient_baseline_fails_closed():
    small_baseline = build_baseline(
        build_series("baseline", samples_per_surface=10),
        created_at_utc="2026-07-30T00:00:00Z",
        git={"sha": "baseline", "dirty": False},
    )
    report = detect(
        build_series("stable"),
        small_baseline,
        generated_at_utc="2026-07-30T03:00:00Z",
        git={"sha": "candidate", "dirty": False},
    )

    assert report["status"] == "baseline_insufficient"
    assert report["signals"] == []


def test_model_change_requires_new_baseline():
    observations = build_series("stable")
    for row in observations:
        row["model_id"] = "new-model"

    report = detect(
        observations,
        baseline(),
        generated_at_utc="2026-07-30T03:00:00Z",
        git={"sha": "candidate", "dirty": False},
    )

    assert report["status"] == "baseline_incompatible"
    assert report["signals"] == []
    assert report["diagnostics"][0]["field"] == "model_id"


def test_missing_compatibility_metadata_fails_closed():
    observations = build_series("stable")
    for row in observations:
        row.pop("model_id")
        row.pop("guardrail_version")
        row.pop("scorer_version")

    report = detect(
        observations,
        baseline(),
        generated_at_utc="2026-07-30T03:00:00Z",
        git={"sha": "candidate", "dirty": False},
    )

    assert report["status"] == "baseline_incompatible"
    assert report["signals"] == []
    assert {
        diagnostic["field"] for diagnostic in report["diagnostics"]
    } == {"model_id", "guardrail_version", "scorer_version"}
    assert all(
        diagnostic["missing_observations"] == len(observations)
        for diagnostic in report["diagnostics"]
    )


def test_second_drift_episode_emits_after_recovery():
    observations = build_series("stable", samples_per_surface=240)
    copilot_rows = [
        row for row in observations if row["surface"] == "copilot"
    ]
    for index, row in enumerate(copilot_rows):
        if 60 <= index < 120 or index >= 180:
            row["metrics"]["fallback"] = 1

    report = detect(
        observations,
        baseline(),
        generated_at_utc="2026-07-30T05:00:00Z",
        git={"sha": "candidate", "dirty": False},
    )

    fallback_signals = [
        signal
        for signal in report["signals"]
        if signal["surface"] == "copilot"
        and signal["metric"] == "fallback_rate"
    ]
    fallback_states = [
        window["state"]
        for window in report["windows"]
        if window["surface"] == "copilot"
        and window["metric"] == "fallback_rate"
    ]
    assert len(fallback_signals) == 2
    assert "recovered" in fallback_states
    assert fallback_signals[1]["detected_at"] > fallback_signals[0]["detected_at"]


def test_jsd_is_symmetric_and_bounded():
    forward = jensen_shannon_divergence([10, 0], [0, 10])
    reverse = jensen_shannon_divergence([0, 10], [10, 0])

    assert forward == reverse == 1.0
    assert jensen_shannon_divergence([5, 5], [5, 5]) == 0.0


def test_report_is_reproducible_for_fixed_metadata():
    observations = build_series("stable")
    fixed_baseline = baseline()
    first = detect(
        observations,
        fixed_baseline,
        generated_at_utc="2026-07-30T03:00:00Z",
        git={"sha": "candidate", "dirty": False},
    )
    second = detect(
        deepcopy(observations),
        deepcopy(fixed_baseline),
        generated_at_utc="2026-07-30T03:00:00Z",
        git={"sha": "candidate", "dirty": False},
    )

    assert first == second
