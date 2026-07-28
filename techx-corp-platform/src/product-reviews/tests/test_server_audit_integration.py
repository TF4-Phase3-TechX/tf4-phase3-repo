from types import SimpleNamespace
from unittest.mock import patch

from ai_assistant import AssistantOutcome
from bedrock_adapter import ProviderFailure

with patch("psycopg2.pool.ThreadedConnectionPool"):
    import product_reviews_server as server


class Counter:
    def add(self, *_args, **_kwargs):
        pass


class Histogram:
    def record(self, *_args, **_kwargs):
        pass


def metrics():
    return {
        "app_ai_assistant_counter": Counter(),
        "app_llm_call_counter": Counter(),
        "app_llm_latency_histogram": Histogram(),
        "app_llm_prompt_tokens_counter": Counter(),
        "app_llm_completion_tokens_counter": Counter(),
        "app_llm_estimated_cost_counter": Counter(),
        "app_ai_fallback_counter": Counter(),
        "app_llm_error_counter": Counter(),
    }


def test_q_and_a_emits_canonical_event_only_after_provider_attempt(monkeypatch):
    audit_events = []
    provider = SimpleNamespace(model_id="model-1", guardrail_version="3")
    assistant = SimpleNamespace(
        provider=provider,
        answer=lambda *_args: AssistantOutcome(
            response="unavailable",
            outcome="unavailable",
            error_class="timeout",
            provider_stop_reason="not_received",
            provider_attempted=True,
        ),
    )
    monkeypatch.setattr(server, "assistant", assistant)
    monkeypatch.setattr(server, "product_review_svc_metrics", metrics())
    monkeypatch.setattr(server, "check_feature_flag", lambda _name: False)
    monkeypatch.setattr(server, "emit_ai_tool_audit", lambda _logger, **event: audit_events.append(event))

    response = server.get_ai_assistant_response(
        "product-1", "content intentionally not captured"
    )

    assert audit_events == [{
        "surface": "product_qa",
        "model_id": "model-1",
        "tool_name": "bedrock.converse",
        "safety_decision": "provider_unavailable",
        "confirmation_status": "not_required",
    }]
    assert response.cache_status == "miss"
    assert response.model_calls == 0
    assert response.memory_status == "not_applicable"


def test_q_and_a_cache_hit_metadata_and_history_use_shared_finalizer(monkeypatch):
    exchanges = []
    provider = SimpleNamespace(model_id="model-1", guardrail_version="3")
    assistant = SimpleNamespace(
        provider=provider,
        answer=lambda *_args: AssistantOutcome(
            response="cached grounded answer",
            outcome="answered",
            cache_status="hit",
            cache_eligible=True,
            cache_reason="hit",
            model_calls=0,
        ),
    )
    monkeypatch.setattr(server, "assistant", assistant)
    monkeypatch.setattr(server, "product_review_svc_metrics", metrics())
    monkeypatch.setattr(server, "check_feature_flag", lambda _name: False)
    monkeypatch.setattr(
        server,
        "session_store",
        SimpleNamespace(
            append_exchange=lambda user, session, question, answer: exchanges.append(
                (user, session, question, answer)
            )
        ),
    )

    response = server.get_ai_assistant_response(
        "product-1",
        "What do reviews say?",
        "session-1",
        "user-1",
    )

    assert response.cache_status == "hit"
    assert response.cache_eligible is True
    assert response.model_calls == 0
    assert response.input_tokens == response.output_tokens == 0
    assert exchanges == [
        (
            "user-1",
            "session-1",
            "What do reviews say?",
            "cached grounded answer",
        )
    ]


def test_copilot_provider_failure_emits_canonical_event(monkeypatch):
    audit_events = []

    class FailingProvider:
        model_id = "model-1"
        guardrail_version = "3"

        def parse_search_intent(self, *_args, **_kwargs):
            raise ProviderFailure("timeout")

    monkeypatch.setattr(server, "assistant", SimpleNamespace(provider=FailingProvider()))
    monkeypatch.setattr(server, "product_review_svc_metrics", metrics())
    monkeypatch.setattr(server, "emit_ai_tool_audit", lambda _logger, **event: audit_events.append(event))

    response = server.search_products_ai("safe catalog query")

    assert response.trace.refused is True
    assert audit_events == [{
        "surface": "copilot_search",
        "model_id": "model-1",
        "tool_name": "bedrock.converse",
        "safety_decision": "provider_unavailable",
        "confirmation_status": "not_required",
    }]
