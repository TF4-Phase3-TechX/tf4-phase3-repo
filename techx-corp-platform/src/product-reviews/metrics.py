#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


def llm_metric_identity(service_name, operation="ask_product_ai_assistant"):
    """Low-cardinality labels required for per-caller AIOps attribution."""

    return {
        "service.name": service_name,
        "llm.operation": operation,
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

    product_review_svc_metrics = {
        "app_product_review_counter": app_product_review_counter,
        "app_ai_assistant_counter": app_ai_assistant_counter,
        "app_ai_fallback_counter": app_ai_fallback_counter,
        "app_llm_prompt_tokens_counter": app_llm_prompt_tokens_counter,
        "app_llm_completion_tokens_counter": app_llm_completion_tokens_counter,
        "app_llm_latency_histogram": app_llm_latency_histogram,
        "app_llm_estimated_cost_counter": app_llm_estimated_cost_counter,
        "app_llm_error_counter": app_llm_error_counter,
        "app_llm_call_counter": app_llm_call_counter,
    }

    return product_review_svc_metrics
