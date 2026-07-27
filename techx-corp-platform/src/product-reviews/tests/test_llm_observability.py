from types import SimpleNamespace

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

import llm_observability


@pytest.fixture
def spans(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test.mandate24")
    monkeypatch.setattr(llm_observability, "_TRACER", tracer)
    return tracer, exporter


def test_pseudonym_is_stable_bounded_and_salted(monkeypatch):
    monkeypatch.setenv("LLM_OBSERVABILITY_HASH_SALT", "test-only-salt")

    first = llm_observability.pseudonymize("customer-123")
    second = llm_observability.pseudonymize("customer-123")

    assert first == second
    assert len(first) == 24
    assert "customer" not in first


def test_request_annotation_retains_only_pseudonyms(monkeypatch, spans):
    tracer, exporter = spans
    monkeypatch.setenv("LLM_OBSERVABILITY_HASH_SALT", "test-only-salt")

    with tracer.start_as_current_span("request"):
        trace_id = llm_observability.annotate_request(
            "shopping_copilot",
            "raw-user",
            "raw-session",
        )

    span = exporter.get_finished_spans()[0]
    assert trace_id != "0" * 32
    assert span.attributes["app.ai.surface"] == "shopping_copilot"
    assert span.attributes["app.content.retained"] is False
    assert "raw-user" not in str(span.attributes)
    assert "raw-session" not in str(span.attributes)


def test_model_span_records_usage_cost_and_safe_contract_metadata(
    monkeypatch,
    spans,
):
    _, exporter = spans
    monkeypatch.setenv("BEDROCK_INPUT_USD_PER_MILLION", "0.30")
    monkeypatch.setenv("BEDROCK_OUTPUT_USD_PER_MILLION", "2.50")

    class Provider:
        model_id = "model-v1"
        guardrail_version = "3"

        @llm_observability.trace_model_call("search_intent", "emit_search_intent")
        def invoke(self):
            return {
                "_metadata": {
                    "latency_ms": 125,
                    "input_tokens": 100,
                    "output_tokens": 20,
                }
            }

    Provider().invoke()

    span = exporter.get_finished_spans()[0]
    assert span.name == "bedrock.converse"
    assert span.attributes["gen_ai.request.model"] == "model-v1"
    assert span.attributes["gen_ai.usage.input_tokens"] == 100
    assert span.attributes["gen_ai.usage.output_tokens"] == 20
    assert span.attributes["app.ai.estimated_cost_usd"] == pytest.approx(
        0.00008
    )
    assert span.attributes["app.ai.outcome"] == "success"
    assert span.attributes["app.content.retained"] is False


def test_model_failure_span_preserves_billed_metadata(spans):
    _, exporter = spans

    class Provider:
        model_id = "model-v1"
        guardrail_version = "3"

        @llm_observability.trace_model_call(
            "product_review_qa",
            "emit_grounded_answer",
        )
        def invoke(self):
            error = RuntimeError("timeout")
            error.error_class = "timeout"
            error.latency_ms = 321
            error.input_tokens = 101
            error.output_tokens = 21
            raise error

    with pytest.raises(RuntimeError, match="timeout"):
        Provider().invoke()

    span = exporter.get_finished_spans()[0]
    assert span.attributes["app.ai.outcome"] == "error"
    assert span.attributes["error.type"] == "timeout"
    assert span.attributes["gen_ai.usage.input_tokens"] == 101
    assert span.attributes["gen_ai.usage.output_tokens"] == 21


def test_tool_span_records_name_and_outcome_without_arguments(spans):
    _, exporter = spans

    with llm_observability.tool_span(
        SimpleNamespace(value="product_search"),
        "catalog_search",
    ):
        pass

    span = exporter.get_finished_spans()[0]
    assert span.name == "tool.catalog_search"
    assert span.attributes["app.ai.tool.name"] == "catalog_search"
    assert span.attributes["app.ai.tool.outcome"] == "success"
    assert span.attributes["app.content.retained"] is False
