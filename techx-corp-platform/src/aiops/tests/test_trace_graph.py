from app.trace_graph import (
    analyze_trace_origins,
    parse_jaeger_traces,
    parse_normalized_spans,
)


def test_jaeger_v1_process_mapping():
    traces = [
        {
            "traceID": "t1",
            "processes": {"p1": {"serviceName": "checkout"}, "p2": {"serviceName": "payment"}},
            "spans": [
                {
                    "spanID": "s1",
                    "processID": "p1",
                    "operationName": "PlaceOrder",
                    "startTime": 1000,
                    "duration": 100,
                    "tags": [{"key": "span.kind", "value": "client"}, {"key": "peer.service", "value": "payment"}, {"key": "error", "value": True}],
                    "references": [],
                },
                {
                    "spanID": "s2",
                    "processID": "p2",
                    "operationName": "Charge",
                    "startTime": 1050,
                    "duration": 50,
                    "tags": [{"key": "span.kind", "value": "server"}, {"key": "error", "value": True}],
                    "references": [{"refType": "CHILD_OF", "spanID": "s1"}],
                },
            ],
        }
    ]
    result = parse_jaeger_traces(traces)
    services = {s.service for s in result.spans}
    assert services == {"checkout", "payment"}
    assert any(e[0] == "checkout" and e[1] == "payment" for e in result.edges)


def test_normalized_spans_and_parent_child():
    spans = [
        {
            "trace_id": "t",
            "span_id": "1",
            "service": "frontend",
            "kind": "server",
            "error": True,
            "start_us": 1,
            "duration_us": 10,
            "parent_span_ids": [],
        },
        {
            "trace_id": "t",
            "span_id": "2",
            "service": "checkout",
            "kind": "server",
            "error": True,
            "start_us": 2,
            "duration_us": 5,
            "parent_span_ids": ["1"],
        },
    ]
    result = parse_normalized_spans(spans)
    assert len(result.spans) == 2
    assert ("frontend", "checkout", "trace-parent:t") in [
        (a, b, p) for a, b, p in result.edges
    ] or any(a == "frontend" and b == "checkout" for a, b, _ in result.edges)


def test_client_timeout_without_server_span():
    spans = [
        {
            "trace_id": "t",
            "span_id": "1",
            "service": "checkout",
            "kind": "client",
            "peer_service": "payment",
            "error": True,
            "start_us": 1,
            "duration_us": 100,
            "parent_span_ids": [],
        }
    ]
    result = parse_normalized_spans(spans)
    origins = analyze_trace_origins(result)
    assert "checkout" in origins
    assert origins["checkout"].root_like_score > 0 or origins["checkout"].client_error_count == 1


def test_duplicate_trace_and_span_ids():
    traces = [
        {
            "traceID": "dup",
            "processes": {"p1": {"serviceName": "a"}},
            "spans": [
                {
                    "spanID": "s1",
                    "processID": "p1",
                    "startTime": 1,
                    "duration": 1,
                    "tags": [],
                    "references": [],
                },
                {
                    "spanID": "s1",
                    "processID": "p1",
                    "startTime": 2,
                    "duration": 1,
                    "tags": [],
                    "references": [],
                },
            ],
        },
        {
            "traceID": "dup",
            "processes": {"p1": {"serviceName": "a"}},
            "spans": [
                {
                    "spanID": "s2",
                    "processID": "p1",
                    "startTime": 3,
                    "duration": 1,
                    "tags": [],
                    "references": [],
                }
            ],
        },
    ]
    result = parse_jaeger_traces(traces)
    assert result.warnings


def test_service_alias_normalization():
    spans = [
        {
            "trace_id": "t",
            "span_id": "1",
            "service": "frontend-web",
            "kind": "server",
            "error": False,
            "start_us": 1,
            "duration_us": 1,
            "parent_span_ids": [],
        }
    ]
    result = parse_normalized_spans(spans)
    assert result.spans[0].service == "frontend"


def test_root_like_vs_victim_like():
    spans = [
        {
            "trace_id": "t",
            "span_id": "1",
            "service": "checkout",
            "kind": "client",
            "peer_service": "payment",
            "error": True,
            "start_us": 100,
            "duration_us": 50,
            "parent_span_ids": [],
        },
        {
            "trace_id": "t",
            "span_id": "2",
            "service": "payment",
            "kind": "server",
            "error": True,
            "start_us": 110,
            "duration_us": 30,
            "parent_span_ids": ["1"],
        },
    ]
    origins = analyze_trace_origins(parse_normalized_spans(spans))
    assert origins["payment"].root_like_score >= origins["checkout"].root_like_score
