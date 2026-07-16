#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Product review gRPC service with an application-owned Bedrock safety path."""

from concurrent import futures
import json
import logging
import os
import random

import grpc
from google.protobuf.json_format import MessageToDict
from grpc_health.v1 import health_pb2, health_pb2_grpc
from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from ai_assistant import AssistantOutcome, GroundedAssistant
from bedrock_adapter import BedrockAdapter
from bedrock_adapter import ProviderFailure
from database import fetch_avg_product_review_score_from_db, fetch_product_reviews_from_db
import demo_pb2
import demo_pb2_grpc
from metrics import init_metrics
from safety import INSUFFICIENT_RESPONSE, UNAVAILABLE_RESPONSE, contains_pii, is_attack_or_action


logger = logging.getLogger("main")
tracer = trace.get_tracer("product-reviews")
product_review_svc_metrics = None
product_catalog_stub = None
assistant = None

SEARCH_UNAVAILABLE_RESPONSE = "I can only help you search for products in our catalog."


def must_map_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"{key} environment variable must be set")
    return value


def check_feature_flag(flag_name: str) -> bool:
    return api.get_client().get_boolean_value(flag_name, False)


class ProductReviewService(demo_pb2_grpc.ProductReviewServiceServicer):
    def GetProductReviews(self, request, context):
        logger.info("product_reviews_request", extra={"product_id": request.product_id})
        return get_product_reviews(request.product_id)

    def GetAverageProductReviewScore(self, request, context):
        logger.info("product_review_score_request", extra={"product_id": request.product_id})
        return get_average_product_review_score(request.product_id)

    def AskProductAIAssistant(self, request, context):
        # Question content is intentionally absent from logs and trace attributes.
        logger.info("ai_assistant_request", extra={"product_id": request.product_id})
        return get_ai_assistant_response(request.product_id, request.question)

    def SearchProductsAIAssistant(self, request, context):
        logger.info("nl_search_request")
        return search_products_ai(request.query)

    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(status=health_pb2.HealthCheckResponse.SERVING)

    def Watch(self, request, context):
        return health_pb2.HealthCheckResponse(status=health_pb2.HealthCheckResponse.UNIMPLEMENTED)


def get_product_reviews(request_product_id: str):
    with tracer.start_as_current_span("get_product_reviews") as span:
        span.set_attribute("app.product.id", request_product_id)
        response = demo_pb2.GetProductReviewsResponse()
        records = fetch_product_reviews_from_db(request_product_id)
        for _, username, description, score in records:
            response.product_reviews.add(username=username, description=description, score=str(score))
        span.set_attribute("app.product_reviews.count", len(response.product_reviews))
        product_review_svc_metrics["app_product_review_counter"].add(
            len(response.product_reviews), {"product.id": request_product_id}
        )
        return response


def get_average_product_review_score(request_product_id: str):
    with tracer.start_as_current_span("get_average_product_review_score") as span:
        span.set_attribute("app.product.id", request_product_id)
        response = demo_pb2.GetAverageProductReviewScoreResponse()
        response.average_score = fetch_avg_product_review_score_from_db(request_product_id)
        return response


def fetch_product_info(product_id: str) -> dict:
    product = product_catalog_stub.GetProduct(demo_pb2.GetProductRequest(id=product_id), timeout=1.0)
    # The caller further allow-lists fields before the provider boundary.
    return MessageToDict(product, preserving_proto_field_name=True)


def get_ai_assistant_response(request_product_id: str, question: str):
    with tracer.start_as_current_span("get_ai_assistant_response") as span:
        span.set_attribute("app.product.id", request_product_id)
        # Preserve the BTC-owned incident flags at the application boundary.
        # They exercise safe degradation and output blocking without selecting
        # a mock provider or allowing intentionally inaccurate content through.
        inject_rate_limit = check_feature_flag("llmRateLimitError") and random.random() < 0.5
        if inject_rate_limit:
            outcome = AssistantOutcome(
                response=UNAVAILABLE_RESPONSE,
                outcome="unavailable",
                error_class="injected_rate_limit",
            )
        else:
            outcome = assistant.answer(request_product_id, question)
            if check_feature_flag("llmInaccurateResponse") and request_product_id == "L9ECAV7KIM":
                outcome = AssistantOutcome(
                    response=INSUFFICIENT_RESPONSE,
                    outcome="insufficient",
                    latency_ms=outcome.latency_ms,
                    input_tokens=outcome.input_tokens,
                    output_tokens=outcome.output_tokens,
                    error_class="injected_inaccurate_response_blocked",
                    quarantined_reviews=outcome.quarantined_reviews,
                )
        attributes = {
            "llm.model": assistant.provider.model_id,
            "llm.call": "converse",
            "llm.outcome": outcome.outcome,
            "guardrail.version": assistant.provider.guardrail_version,
            "error.class": outcome.error_class or "none",
            "response.stop_reason": outcome.provider_stop_reason,
            "response.contract_stage": outcome.response_contract_stage,
        }
        span.set_attribute("gen_ai.request.model", assistant.provider.model_id)
        span.set_attribute("app.ai.outcome", outcome.outcome)
        span.set_attribute("app.ai.guardrail.version", assistant.provider.guardrail_version)
        product_review_svc_metrics["app_ai_assistant_counter"].add(1, attributes)
        provider_attempted = outcome.outcome != "blocked" or bool(outcome.error_class)
        if provider_attempted:
            product_review_svc_metrics["app_llm_call_counter"].add(1, attributes)
            product_review_svc_metrics["app_llm_latency_histogram"].record(outcome.latency_ms / 1_000, attributes)
        product_review_svc_metrics["app_llm_prompt_tokens_counter"].add(outcome.input_tokens, attributes)
        product_review_svc_metrics["app_llm_completion_tokens_counter"].add(outcome.output_tokens, attributes)
        estimated_cost = (
            outcome.input_tokens * float(os.environ.get("BEDROCK_INPUT_USD_PER_MILLION", "1"))
            + outcome.output_tokens * float(os.environ.get("BEDROCK_OUTPUT_USD_PER_MILLION", "5"))
        ) / 1_000_000
        product_review_svc_metrics["app_llm_estimated_cost_counter"].add(estimated_cost, attributes)
        if outcome.outcome in ("unavailable", "blocked"):
            product_review_svc_metrics["app_ai_fallback_counter"].add(1, attributes)
        if outcome.outcome == "unavailable":
            product_review_svc_metrics["app_llm_error_counter"].add(1, attributes)
        logger.info(
            "ai_assistant_completed",
            extra={
                "model_id": assistant.provider.model_id,
                "guardrail_version": assistant.provider.guardrail_version,
                "outcome": outcome.outcome,
                "latency_ms": round(outcome.latency_ms, 1),
                "input_tokens": outcome.input_tokens,
                "output_tokens": outcome.output_tokens,
                "estimated_cost_usd": round(estimated_cost, 8),
                "error_class": outcome.error_class or "none",
                "provider_stop_reason": outcome.provider_stop_reason,
                "response_contract_stage": outcome.response_contract_stage,
                "quarantined_reviews": outcome.quarantined_reviews,
            },
        )
        return demo_pb2.AskProductAIAssistantResponse(response=outcome.response)


def _make_refused_trace(parsed_intent="", filter_applied="", before=0, after=0):
    return demo_pb2.SearchEvidenceTrace(
        parsed_intent=parsed_intent,
        filter_applied=filter_applied,
        candidate_count_before=before,
        candidate_count_after=after,
        refused=True,
    )


def _refused_search_response(parsed_intent="", filter_applied="", before=0, after=0):
    return demo_pb2.SearchProductsAIAssistantResponse(
        results=[],
        trace=_make_refused_trace(parsed_intent, filter_applied, before, after),
    )


import difflib

def _fuzzy_match_token(keyword_token: str, product_text: str) -> bool:
    clean_text = "".join(c if c.isalnum() or c.isspace() else " " for c in product_text.lower())
    product_tokens = clean_text.split()
    kw_len = len(keyword_token)
    if kw_len <= 4:
        threshold = 1.0
    elif 5 <= kw_len <= 6:
        threshold = 0.60
    else:
        threshold = 0.75
    for p_token in product_tokens:
        ratio = difflib.SequenceMatcher(None, keyword_token, p_token).ratio()
        if ratio >= threshold:
            return True
    return False

def _fuzzy_match_keywords(keywords_query: str, name: str, description: str) -> bool:
    kw_tokens = keywords_query.lower().split()
    if not kw_tokens:
        return True
    for kw_tok in kw_tokens:
        if not (_fuzzy_match_token(kw_tok, name) or _fuzzy_match_token(kw_tok, description)):
            return False
    return True

def _match_comparison_target(target_name: str, products: list) -> list:
    matched_products = []
    target_tokens = target_name.lower().split()
    for p in products:
        p_name_lower = p.name.lower()
        match_all = True
        for t_tok in target_tokens:
            if not _fuzzy_match_token(t_tok, p_name_lower):
                match_all = False
                break
        if match_all:
            matched_products.append(p)
    return matched_products

def search_products_ai(query: str):
    with tracer.start_as_current_span("search_products_ai") as span:
        # --- Input validation ---
        if not query or not query.strip():
            span.set_attribute("app.search.outcome", "empty_query")
            return _refused_search_response()

        if is_attack_or_action(query) or contains_pii(query):
            span.set_attribute("app.search.outcome", "blocked")
            return _refused_search_response()

        try:
            # --- Parse intent via LLM ---
            intent = assistant.provider.parse_search_intent(query)
            parsed_intent_json = json.dumps(intent, ensure_ascii=False)
            span.set_attribute("app.search.search_type", intent.get("search_type", ""))

            if intent.get("search_type") == "out_of_scope":
                span.set_attribute("app.search.outcome", "out_of_scope")
                return _refused_search_response(parsed_intent=parsed_intent_json)

            # --- Fetch full catalog ---
            catalog_response = product_catalog_stub.ListProducts(demo_pb2.Empty(), timeout=2.0)
            all_products = list(catalog_response.products)
            candidate_count_before = len(all_products)
            valid_ids = {p.id for p in all_products}

            # --- Apply filters ---
            filtered = list(all_products)
            filters_applied = {}

            # Category filter
            category = intent.get("category", "").strip().lower()
            if category:
                filters_applied["category"] = category
                filtered = [
                    p for p in filtered
                    if any(category in c.lower() for c in p.categories)
                ]

            # Price filter
            price_min = intent.get("price_min")
            price_max = intent.get("price_max")
            if price_min is not None or price_max is not None:
                def _price(product):
                    return product.price_usd.units + product.price_usd.nanos / 1_000_000_000

                if price_min is not None:
                    filters_applied["price_min"] = price_min
                    filtered = [p for p in filtered if _price(p) >= price_min]
                if price_max is not None:
                    filters_applied["price_max"] = price_max
                    filtered = [p for p in filtered if _price(p) <= price_max]

            # Keywords filter (with fuzzy matching)
            keywords = intent.get("keywords", "").strip().lower()
            if keywords:
                filters_applied["keywords"] = keywords
                filtered = [
                    p for p in filtered
                    if _fuzzy_match_keywords(keywords, p.name, p.description)
                ]

            # Compare filter (with fail-closed logic and trace logging)
            if intent.get("search_type") == "compare":
                targets = intent.get("comparison_targets", [])
                if targets:
                    filters_applied["comparison_targets"] = targets
                    unmatched_targets = []
                    comparison_matched_products = []
                    seen_matched_ids = set()

                    for target in targets:
                        matched = _match_comparison_target(target, all_products)
                        if not matched:
                            unmatched_targets.append(target)
                        else:
                            for p in matched:
                                if p.id not in seen_matched_ids:
                                    comparison_matched_products.append(p)
                                    seen_matched_ids.add(p.id)

                    if unmatched_targets:
                        # Fail-closed: refuse entirely if any target fails to match
                        filters_applied["refuse_reason"] = "comparison_target_not_found"
                        filters_applied["unmatched_targets"] = unmatched_targets
                        filter_applied_json = json.dumps(filters_applied, ensure_ascii=False)
                        span.set_attribute("app.search.outcome", "compare_refusal")
                        return _refused_search_response(
                            parsed_intent=parsed_intent_json,
                            filter_applied=filter_applied_json,
                            before=candidate_count_before,
                            after=0
                        )

                    # Intersect current filtered list with comparison matched products
                    compare_matched_ids = {p.id for p in comparison_matched_products}
                    filtered = [p for p in filtered if p.id in compare_matched_ids]

            # --- Grounding shield: verify all result IDs exist in original catalog ---
            filtered = [p for p in filtered if p.id in valid_ids]

            filter_applied_json = json.dumps(filters_applied, ensure_ascii=False)
            candidate_count_after = len(filtered)

            span.set_attribute("app.search.candidate_count_before", candidate_count_before)
            span.set_attribute("app.search.candidate_count_after", candidate_count_after)
            span.set_attribute("app.search.outcome", "success")

            trace_msg = demo_pb2.SearchEvidenceTrace(
                parsed_intent=parsed_intent_json,
                filter_applied=filter_applied_json,
                candidate_count_before=candidate_count_before,
                candidate_count_after=candidate_count_after,
                refused=False,
            )

            logger.info(
                "nl_search_completed",
                extra={
                    "search_type": intent.get("search_type"),
                    "candidate_count_before": candidate_count_before,
                    "candidate_count_after": candidate_count_after,
                },
            )

            return demo_pb2.SearchProductsAIAssistantResponse(
                results=filtered,
                trace=trace_msg,
            )

        except ProviderFailure as exc:
            span.set_attribute("app.search.outcome", "provider_failure")
            span.set_attribute("app.search.error_class", exc.error_class)
            logger.info("nl_search_provider_failure", extra={"error_class": exc.error_class})
            return _refused_search_response(parsed_intent=exc.error_class)

        except Exception as exc:
            span.set_attribute("app.search.outcome", "unexpected_error")
            logger.info("nl_search_unexpected_error", extra={"error": str(exc)[:200]})
            return _refused_search_response()



def configure_logging(service_name: str) -> None:
    provider = LoggerProvider(resource=Resource.create({"service.name": service_name}))
    set_logger_provider(provider)
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(insecure=True)))
    logger.addHandler(LoggingHandler(level=logging.NOTSET, logger_provider=provider))


def main() -> None:
    global tracer, product_review_svc_metrics, product_catalog_stub, assistant
    service_name = must_map_env("OTEL_SERVICE_NAME")
    api.set_provider(
        FlagdProvider(host=os.environ.get("FLAGD_HOST", "flagd"), port=int(os.environ.get("FLAGD_PORT", "8013")))
    )
    tracer = trace.get_tracer_provider().get_tracer(service_name)
    product_review_svc_metrics = init_metrics(metrics.get_meter_provider().get_meter(service_name))
    configure_logging(service_name)

    product_catalog_stub = demo_pb2_grpc.ProductCatalogServiceStub(
        grpc.insecure_channel(must_map_env("PRODUCT_CATALOG_ADDR"))
    )
    system_canary = os.environ.get("BEDROCK_SYSTEM_CANARY", "")
    provider = BedrockAdapter(
        model_id=must_map_env("BEDROCK_MODEL_ID"),
        guardrail_id=must_map_env("BEDROCK_GUARDRAIL_ID"),
        guardrail_version=must_map_env("BEDROCK_GUARDRAIL_VERSION"),
        region=os.environ.get("AWS_REGION", "us-east-1"),
        output_mode=os.environ.get("BEDROCK_OUTPUT_MODE", "json_schema"),
        deadline_seconds=float(os.environ.get("BEDROCK_DEADLINE_SECONDS", "4.5")),
        system_canary=system_canary,
    )
    assistant = GroundedAssistant(
        provider=provider,
        fetch_product=fetch_product_info,
        fetch_reviews=fetch_product_reviews_from_db,
        system_canary=system_canary,
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    service = ProductReviewService()
    demo_pb2_grpc.add_ProductReviewServiceServicer_to_server(service, server)
    health_pb2_grpc.add_HealthServicer_to_server(service, server)
    port = must_map_env("PRODUCT_REVIEWS_PORT")
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("product_reviews_service_started", extra={"port": port})
    server.wait_for_termination()


if __name__ == "__main__":
    main()
