import json
from dataclasses import replace

from app.config import Settings
from benchmark.calibrate_detection import Case, evaluate, load_cases
from benchmark.collect_prometheus_dataset import collect


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"service_name": "frontend"},
                        "values": [[1, "100"], [2, "NaN"], [3, "110"]],
                    }
                ]
            },
        }


class FakeClient:
    def get(self, url, params):
        assert url.endswith("/api/v1/query_range")
        assert params["step"] == 60
        return FakeResponse()


def test_documented_detector_seed_classifies_all_design_fixtures():
    result = evaluate(Settings())

    assert result["fp"] == 0
    assert result["fn"] == 0


def test_sensitivity_fixture_exposes_more_aggressive_ratio_tradeoff():
    seed = evaluate(Settings())
    aggressive = evaluate(replace(Settings(), ratio_threshold=1.3))

    assert seed["fp"] == 0
    assert aggressive["fp"] > seed["fp"]


def test_external_labelled_dataset_can_be_replayed(tmp_path):
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps(
            {
                "scope": "test production replay",
                "source": {"kind": "prometheus_query_range"},
                "cases": [
                    {
                        "name": "normal",
                        "points": [100, 101, 99, 100, 102],
                        "floor": 1000,
                        "anomalous": False,
                    },
                    {
                        "name": "incident",
                        "points": [100, 101, 99, 100, 1750, 1800],
                        "floor": 1000,
                        "anomalous": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    cases, metadata = load_cases(path)
    result = evaluate(Settings(), cases)

    assert metadata["source"]["kind"] == "prometheus_query_range"
    assert len(metadata["source"]["dataset_canonical_sha256"]) == 64
    assert result["fp"] == 0
    assert result["fn"] == 0


def test_rolling_replay_detects_incident_that_recovers_before_window_end():
    case = Case(
        "recovered-incident",
        (100, 100, 100, 100, 1800, 1800, 100, 100),
        1000,
        True,
        "incident should not disappear because the final sample recovered",
    )

    final_only = evaluate(Settings(), (case,))
    rolling = evaluate(Settings(), (case,), replay_all_points=True)

    assert final_only["fn"] == 1
    assert rolling["tp"] == 1
    assert rolling["cases"][0]["first_detection_index"] is not None


def test_prometheus_collector_preserves_explicit_label_and_provenance():
    payload = collect(
        {
            "prometheus_url": "http://prometheus:9090",
            "start": "2026-07-21T00:00:00Z",
            "end": "2026-07-21T01:00:00Z",
            "step_seconds": 60,
            "label_authority": "incident-commander",
            "label_evidence": ["INC-123"],
            "cases": [
                {
                    "name": "frontend-normal",
                    "query": "test_query",
                    "floor": 1000,
                    "anomalous": False,
                }
            ],
        },
        FakeClient(),
    )

    assert payload["cases"][0]["points"] == [100.0, 110.0]
    assert payload["cases"][0]["anomalous"] is False
    assert payload["source"]["label_authority"] == "incident-commander"
    assert len(payload["sha256_before_hash_field"]) == 64
