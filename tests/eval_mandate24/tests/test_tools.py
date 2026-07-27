import io
import json

import pytest

from tests.eval_mandate24 import aggregate
from tests.eval_mandate24 import compare_latency
from tests.eval_mandate24 import fetch_trace
from tests.eval_mandate24 import replay
from tests.eval_mandate24 import verify_marker_absence
from tests.eval_mandate24.common import request_digest, validate_trace_id


class JsonResponse:
    def __init__(self, value):
        self._buffer = io.BytesIO(json.dumps(value).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *args):
        return self._buffer.read(*args)


def test_trace_id_validation_and_request_digest_are_content_free():
    value = "1234567890abcdef1234567890abcdef"
    assert validate_trace_id(value) == value
    assert request_digest("sensitive request") != "sensitive request"
    with pytest.raises(ValueError):
        validate_trace_id("0" * 32)


def test_replay_case_schema_rejects_unknown_fields():
    case = replay.validate_case(
        {"case_id": "one", "query": "show telescopes"},
        1,
    )
    assert case["case_id"] == "one"
    assert case["query"] == "show telescopes"
    with pytest.raises(ValueError, match="unknown fields"):
        replay.validate_case(
            {"case_id": "one", "query": "q", "prompt_copy": "forbidden"},
            1,
        )


def test_fetch_trace_requires_exact_returned_id(monkeypatch):
    trace_id = "1234567890abcdef1234567890abcdef"
    monkeypatch.setattr(
        fetch_trace.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: JsonResponse({
            "data": [{"traceID": trace_id, "spans": []}]
        }),
    )

    payload = fetch_trace.fetch_trace(trace_id, "http://jaeger")

    assert payload["data"][0]["traceID"] == trace_id


def test_aggregate_uses_model_surface_and_time_window(monkeypatch):
    monkeypatch.setattr(
        aggregate.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: JsonResponse({
            "status": "success",
            "data": {"result": []},
        }),
    )

    report = aggregate.aggregate("http://prometheus", "1h")

    assert len(report["queries"]) == 3
    assert all("ai_surface" in item["promql"] for item in report["queries"])
    assert all("[1h]" in item["promql"] for item in report["queries"])
    with pytest.raises(ValueError):
        aggregate.aggregate("http://prometheus", "1 hour")


def test_marker_absence_report_never_retains_marker(monkeypatch, tmp_path):
    marker = "m24-private-marker@example.test"
    trace_path = tmp_path / "trace.json"
    trace_path.write_text('{"data":[]}', encoding="utf-8")
    monkeypatch.setattr(
        verify_marker_absence.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: JsonResponse({
            "hits": {"total": {"value": 0}}
        }),
    )

    report = verify_marker_absence.verify(
        marker,
        trace_path,
        "http://opensearch",
        "otel-logs-*",
    )

    assert report["pass"] is True
    assert marker not in json.dumps(report)


def test_latency_comparison_requires_matched_cases(tmp_path):
    baseline = tmp_path / "baseline.jsonl"
    candidate = tmp_path / "candidate.jsonl"
    baseline.write_text(
        '{"case_id":"one","latency_ms":100}\n'
        '{"case_id":"two","latency_ms":200}\n',
        encoding="utf-8",
    )
    candidate.write_text(
        '{"case_id":"one","latency_ms":102}\n'
        '{"case_id":"two","latency_ms":205}\n',
        encoding="utf-8",
    )

    report = compare_latency.compare(baseline, candidate, 5)

    assert report["matched_cases"] == 2
    assert report["p95_increase_percent"] == pytest.approx(2.5)
    assert report["pass"] is True
