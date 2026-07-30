import pytest

from metrics import (
    canonical_quality_outcome,
    init_metrics,
    llm_metric_identity,
    quality_metric_attributes,
)


class FakeInstrument:
    def add(self, value, attributes=None):
        pass

    def record(self, value, attributes=None):
        pass


class FakeMeter:
    def __init__(self):
        self.names = []

    def create_counter(self, name, **kwargs):
        self.names.append(name)
        return FakeInstrument()

    def create_histogram(self, name, **kwargs):
        self.names.append(name)
        return FakeInstrument()


def test_pr131_metric_contract_is_preserved_for_bedrock():
    meter = FakeMeter()
    metrics = init_metrics(meter)

    assert {
        "app_llm_prompt_tokens_total",
        "app_llm_completion_tokens_total",
        "app_llm_estimated_cost_usd_total",
        "app_llm_latency_seconds",
        "app_llm_errors_total",
        "app_llm_calls_total",
        "app_ai_quality_events_total",
    }.issubset(meter.names)
    assert {
        "app_llm_prompt_tokens_counter",
        "app_llm_completion_tokens_counter",
        "app_llm_estimated_cost_counter",
        "app_llm_latency_histogram",
        "app_llm_error_counter",
        "app_llm_call_counter",
        "app_ai_quality_event_counter",
    }.issubset(metrics)


def test_llm_metrics_carry_dynamic_caller_and_operation_labels():
    assert llm_metric_identity("shopping-copilot") == {
        "service.name": "shopping-copilot",
        "llm.operation": "ask_product_ai_assistant",
    }


@pytest.mark.parametrize(
    ("raw_outcome", "expected"),
    [
        ("answered", "answered"),
        ("success", "answered"),
        ("no_match", "abstained"),
        ("clarification_required", "abstained"),
        ("unavailable", "fallback"),
        ("provider_unavailable", "fallback"),
        ("degraded", "fallback"),
        ("blocked", "blocked"),
        ("memory_recalled", "other"),
    ],
)
def test_quality_outcome_has_bounded_cardinality(raw_outcome, expected):
    assert canonical_quality_outcome(raw_outcome) == expected


def test_quality_metric_attributes_reject_unknown_surface(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-v1")
    monkeypatch.setenv("BEDROCK_GUARDRAIL_VERSION", "3")
    monkeypatch.setenv("AI_QUALITY_SCORER_VERSION", "outcome-v1")
    assert quality_metric_attributes("copilot", "no_match") == {
        "ai.surface": "copilot",
        "quality.outcome": "abstained",
        "model.id": "model-v1",
        "guardrail.version": "3",
        "scorer.version": "outcome-v1",
    }
    with pytest.raises(ValueError, match="unsupported quality surface"):
        quality_metric_attributes("raw-user-supplied-surface", "answered")


def test_quality_metric_identity_fails_closed_when_runtime_unconfigured(
    monkeypatch,
):
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    monkeypatch.delenv("BEDROCK_GUARDRAIL_VERSION", raising=False)

    attributes = quality_metric_attributes("review_summary", "answered")

    assert attributes["model.id"] == "unconfigured"
    assert attributes["guardrail.version"] == "unconfigured"
