import json

import pytest

from compare_runs import compare


def write_run(path, *, dataset="same", model_id="model", passed=1, latency=100):
    path.mkdir()
    (path / "manifest.json").write_text(json.dumps({
        "run_id": path.name,
        "dataset_sha256": dataset,
        "git": {"sha": f"sha-{path.name}", "dirty": False},
        "model": {
            "model_id": model_id,
            "guardrail_id": "guardrail",
            "guardrail_version": "3",
        },
        "hard_bars": {
            "pii_leak_count": 0,
            "system_prompt_leak_count": 0,
            "unauthorized_write_count": 0,
            "pass": True,
        },
    }))
    (path / "results.json").write_text(json.dumps({
        "per_case": [{
            "case_id": "case-1",
            "status": "pass" if passed else "fail",
            "failures": [] if passed else ["failure"],
        }],
        "aggregate": {
            "case_pass": {"rate": float(passed)},
            "task_success": {"rate": float(passed)},
            "claim_faithfulness": {"rate": float(passed)},
            "hallucination": {"rate": float(not passed)},
            "performance": {
                "p95_latency_ms": latency,
                "tokens_per_request": 100,
                "cost_per_request_usd": 0.001,
            },
        },
    }))


def test_compare_requires_like_for_like_runs(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    write_run(before, passed=0, latency=200)
    write_run(after, passed=1, latency=100)
    result = compare(before, after)
    assert result["same_dataset"]
    assert result["quality"]["case_pass_rate"]["absolute"] == 1
    assert result["performance"]["p95_latency_ms"]["absolute"] == -100
    assert result["quality"]["failed_cases_before"][0]["case_id"] == "case-1"
    assert result["quality"]["failed_cases_after"] == []


def test_compare_rejects_dataset_drift(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    write_run(before, dataset="one")
    write_run(after, dataset="two")
    with pytest.raises(ValueError, match="dataset hashes differ"):
        compare(before, after)
