from tests.eval_mandate27.baseline import build_baseline
from tests.eval_mandate27.common import write_json, write_jsonl
from tests.eval_mandate27.generate_fixtures import build_series
from tests.eval_mandate27.replay import replay


def test_replay_accepts_external_jsonl_and_writes_signal(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    series_path = tmp_path / "series.jsonl"
    output_path = tmp_path / "report.json"
    write_json(
        baseline_path,
        build_baseline(
            build_series("baseline"),
            created_at_utc="2026-07-30T00:00:00Z",
            git={"sha": "baseline", "dirty": False},
        ),
    )
    write_jsonl(series_path, build_series("shifted_copilot_fallback"))

    report = replay(series_path, baseline_path, output_path)

    assert output_path.exists()
    assert report["status"] == "drift"
    assert report["signals"][0]["metric"] == "fallback_rate"
