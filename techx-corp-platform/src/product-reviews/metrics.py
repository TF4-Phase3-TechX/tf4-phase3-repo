#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


def llm_metric_identity(service_name, operation="ask_product_ai_assistant"):
    """Low-cardinality labels required for per-caller AIOps attribution."""

    return {
        "service.name": service_name,
        "llm.operation": operation,
    }


def canonical_quality_outcome(outcome):
    """Collapse unbounded route outcomes into a drift-safe label set."""

    normalized = str(outcome or "").strip().lower()
    if normalized in {
        "answered",
        "success",
        "action_confirmation_required",
        "applied",
    }:
        return "answered"
    if normalized in {
        "abstained",
        "clarification_required",
        "insufficient",
        "insufficient_evidence",
        "no_match",
    }:
        return "abstained"
    if normalized in {
        "error",
        "fallback",
        "provider_unavailable",
        "transport_error",
        "unavailable",
    }:
        return "fallback"
    if normalized in {"blocked", "guardrail_blocked", "out_of_scope", "refused"}:
        return "blocked"
    return "other"


def quality_metric_attributes(surface, outcome):
    """Return the only labels accepted by the online quality-drift metric."""

    if surface not in {"review_summary", "copilot"}:
        raise ValueError(f"unsupported quality surface: {surface}")
    return {
        "ai.surface": surface,
        "quality.outcome": canonical_quality_outcome(outcome),
    }


def init_metrics(meter):

    # Product reviews counter
    app_product_review_counter = meter.create_counter(
        'app_product_review_counter', unit='reviews', description="Counts the total number of returned product reviews"
    )

    # AI Assistant counter
    app_ai_assistant_counter = meter.create_counter(
        'app_ai_assistant_counter', unit='summaries', description="Counts the total number of AI Assistant requests"
    )

    app_ai_fallback_counter = meter.create_counter(
        'app_ai_fallback_counter', unit='fallbacks', description="Counts safe blocked and unavailable responses"
    )
    app_ai_quality_event_counter = meter.create_counter(
        'app_ai_quality_events_total',
        unit='events',
        description="Content-free AI request outcomes for model-quality drift detection",
    )
    # Keep the metric contract introduced by PR #131 so existing PromQL and
    # dashboards continue to work after the provider moves to Bedrock.
    app_llm_prompt_tokens_counter = meter.create_counter(
        'app_llm_prompt_tokens_total', unit='tokens', description="Cumulative Bedrock input tokens"
    )
    app_llm_completion_tokens_counter = meter.create_counter(
        'app_llm_completion_tokens_total', unit='tokens', description="Cumulative Bedrock output tokens"
    )
    app_llm_latency_histogram = meter.create_histogram(
        'app_llm_latency_seconds', unit='s', description="End-to-end Bedrock call latency"
    )
    app_llm_estimated_cost_counter = meter.create_counter(
        'app_llm_estimated_cost_usd_total', unit='USD',
        description="Estimated Bedrock token cost using the deployed price snapshot"
    )
    app_llm_error_counter = meter.create_counter(
        'app_llm_errors_total', unit='errors', description="Bedrock provider failures returning safe fallback"
    )
    app_llm_call_counter = meter.create_counter(
        'app_llm_calls_total', unit='calls', description="Bedrock calls partitioned by outcome"
    )
    app_ai_cache_request_counter = meter.create_counter(
        'app_ai_cache_requests_total',
        unit='requests',
        description="AI response-cache hit/miss requests by surface and bounded reason",
    )
    app_ai_cache_lookup_latency_histogram = meter.create_histogram(
        'app_ai_cache_lookup_latency_seconds',
        unit='s',
        description="AI response-cache lookup latency",
    )
    app_ai_cache_saved_model_calls_counter = meter.create_counter(
        'app_ai_cache_saved_model_calls_total',
        unit='calls',
        description="Provider calls avoided by exact-cache hits",
    )
    app_ai_cache_saved_tokens_counter = meter.create_counter(
        'app_ai_cache_saved_tokens_total',
        unit='tokens',
        description="Provider input/output tokens avoided by exact-cache hits",
    )
    app_ai_cache_saved_cost_counter = meter.create_counter(
        'app_ai_cache_saved_cost_usd_total',
        unit='USD',
        description="Estimated provider cost avoided by exact-cache hits",
    )
    app_ai_cache_event_counter = meter.create_counter(
        'app_ai_cache_events_total',
        unit='events',
        description="AI cache writes, rejections and errors",
    )
    app_ai_profile_operation_counter = meter.create_counter(
        'app_ai_profile_operations_total',
        unit='operations',
        description="Allow-listed profile reads, writes, deletes and errors",
    )

    product_review_svc_metrics = {
        "app_product_review_counter": app_product_review_counter,
        "app_ai_assistant_counter": app_ai_assistant_counter,
        "app_ai_fallback_counter": app_ai_fallback_counter,
        "app_ai_quality_event_counter": app_ai_quality_event_counter,
        "app_llm_prompt_tokens_counter": app_llm_prompt_tokens_counter,
        "app_llm_completion_tokens_counter": app_llm_completion_tokens_counter,
        "app_llm_latency_histogram": app_llm_latency_histogram,
        "app_llm_estimated_cost_counter": app_llm_estimated_cost_counter,
        "app_llm_error_counter": app_llm_error_counter,
        "app_llm_call_counter": app_llm_call_counter,
        "app_ai_cache_request_counter": app_ai_cache_request_counter,
        "app_ai_cache_lookup_latency_histogram": app_ai_cache_lookup_latency_histogram,
        "app_ai_cache_saved_model_calls_counter": app_ai_cache_saved_model_calls_counter,
        "app_ai_cache_saved_tokens_counter": app_ai_cache_saved_tokens_counter,
        "app_ai_cache_saved_cost_counter": app_ai_cache_saved_cost_counter,
        "app_ai_cache_event_counter": app_ai_cache_event_counter,
        "app_ai_profile_operation_counter": app_ai_profile_operation_counter,
    }

    return product_review_svc_metrics
