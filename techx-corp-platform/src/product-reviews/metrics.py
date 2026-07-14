#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

def init_metrics(meter):

    # Product reviews counter
    app_product_review_counter = meter.create_counter(
        'app_product_review_counter', unit='reviews', description="Counts the total number of returned product reviews"
    )

    # AI Assistant counter
    app_ai_assistant_counter = meter.create_counter(
        'app_ai_assistant_counter', unit='summaries', description="Counts the total number of AI Assistant requests"
    )

    # ── AI-specific telemetry metrics (TF4AIO-52 / TF4AIO-30) ──

    # Token usage counters — used by Prometheus alert rules for cost tracking
    app_llm_prompt_tokens_counter = meter.create_counter(
        'app_llm_prompt_tokens_total', unit='tokens',
        description="Cumulative number of prompt tokens sent to the LLM"
    )
    app_llm_completion_tokens_counter = meter.create_counter(
        'app_llm_completion_tokens_total', unit='tokens',
        description="Cumulative number of completion tokens received from the LLM"
    )

    # Estimated cost counter — primary metric for Prometheus budget guard alerts
    app_llm_estimated_cost_counter = meter.create_counter(
        'app_llm_estimated_cost_usd_total', unit='USD',
        description="Cumulative estimated cost of LLM API calls in USD (approximated from token counts)"
    )

    # LLM call latency histogram — enables p50/p95/p99 alerting
    app_llm_latency_histogram = meter.create_histogram(
        'app_llm_latency_seconds', unit='s',
        description="End-to-end latency of a single LLM API call in seconds"
    )

    # LLM error counter — for error-rate alert rules
    app_llm_error_counter = meter.create_counter(
        'app_llm_errors_total', unit='errors',
        description="Cumulative number of LLM API call errors (timeouts, 4xx, 5xx)"
    )

    product_review_svc_metrics = {
        "app_product_review_counter": app_product_review_counter,
        "app_ai_assistant_counter": app_ai_assistant_counter,
        # AI-specific
        "app_llm_prompt_tokens_counter": app_llm_prompt_tokens_counter,
        "app_llm_completion_tokens_counter": app_llm_completion_tokens_counter,
        "app_llm_estimated_cost_counter": app_llm_estimated_cost_counter,
        "app_llm_latency_histogram": app_llm_latency_histogram,
        "app_llm_error_counter": app_llm_error_counter,
    }

    return product_review_svc_metrics
