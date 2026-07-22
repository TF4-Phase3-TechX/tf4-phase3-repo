#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Product review gRPC service with an application-owned Bedrock safety path."""

from concurrent import futures
import json
import logging
import os
import random
import time

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
from metrics import init_metrics, llm_metric_identity
from safety import INSUFFICIENT_RESPONSE, UNAVAILABLE_RESPONSE, contains_pii, is_attack, is_action_intent, is_attack_or_action, normalize_text, MAX_QUESTION_CHARS
from session_store import session_store


logger = logging.getLogger("main")
tracer = trace.get_tracer("product-reviews")
product_review_svc_metrics = None
product_catalog_stub = None
cart_stub = None
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
        session_id = getattr(request, "session_id", "")
        user_id = getattr(request, "user_id", "guest") or "guest"
        return get_ai_assistant_response(request.product_id, request.question, session_id, user_id)

    def SearchProductsAIAssistant(self, request, context):
        logger.info("nl_search_request")
        session_id = getattr(request, "session_id", "")
        user_id = getattr(request, "user_id", "guest") or "guest"
        return search_products_ai(request.query, session_id, user_id)

    def ConfirmCartAction(self, request, context):
        return confirm_cart_action(request.user_id, request.session_id, request.confirmation_token)

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


def get_ai_assistant_response(request_product_id: str, question: str, session_id: str = "", user_id: str = "guest"):
    with tracer.start_as_current_span("get_ai_assistant_response") as span:
        span.set_attribute("app.product.id", request_product_id)
        span.set_attribute("app.caller.feature", "product_qa")
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
            outcome = assistant.answer(request_product_id, question, session_id, user_id)
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
        attributes = llm_metric_identity(
            os.environ.get("OTEL_SERVICE_NAME", "product-reviews")
        ) | {
            # Explicit attribution is part of the app_llm_* metric contract.
            # Prometheus normalizes these keys to service_name and
            # llm_operation, allowing AIOps to route incidents per caller.
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
        return demo_pb2.AskProductAIAssistantResponse(
            response=outcome.response,
            action_proposal=outcome.action_proposal,
        )


from router import route_search_products_ai


def search_products_ai(query: str, session_id: str = "", user_id: str = "guest"):
    return route_search_products_ai(
        query=query,
        session_id=session_id,
        assistant=assistant,
        product_catalog_stub=product_catalog_stub,
        tracer=tracer,
        record_metrics_fn=_record_search_metrics,
            # --- Fetch multi-turn conversation history ---
            history = session_store.get_history(user_id, session_id) if session_id else []

            # --- Parse intent via LLM with multi-turn history ---
            intent = assistant.provider.parse_search_intent(query, history=history)
            _metadata = intent.get("_metadata") or {}
            _in_tok = _metadata.get("input_tokens", 0)
            _out_tok = _metadata.get("output_tokens", 0)
            _lat_ms = _metadata.get("latency_ms", 0.0)

            parsed_intent_json = json.dumps({k: v for k, v in intent.items() if k != "_metadata"}, ensure_ascii=False)
            span.set_attribute("app.search.search_type", intent.get("search_type", ""))

            # Record telemetry immediately after provider call for ALL outcomes
            _record_search_metrics(
                model_id=assistant.provider.model_id,
                guardrail_version=assistant.provider.guardrail_version,
                outcome="success",
                error_class=None,
                latency_ms=_lat_ms,
                input_tokens=_in_tok,
                output_tokens=_out_tok,
            )

            if intent.get("search_type") == "out_of_scope":
                span.set_attribute("app.search.outcome", "out_of_scope")
                return _refused_search_response(
                    parsed_intent=parsed_intent_json,
                    input_tokens=_in_tok,
                    output_tokens=_out_tok,
                )

            # --- Fetch full catalog ---
            catalog_response = product_catalog_stub.ListProducts(demo_pb2.Empty(), timeout=2.0)
            all_products = list(catalog_response.products)
            candidate_count_before = len(all_products)

            # Handle clarify search type (when LLM asks for multi-turn clarification)
            if intent.get("search_type") == "clarify":
                clarify_q = intent.get("clarify_question") or "Bạn có thể cho biết rõ hơn loại sản phẩm bạn đang tìm kiếm không?"
                if session_id:
                    session_store.append_turn(user_id, session_id, "user", query)
                    session_store.append_turn(user_id, session_id, "assistant", clarify_q)
                span.set_attribute("app.search.outcome", "clarify")
                return demo_pb2.SearchProductsAIAssistantResponse(
                    results=[],
                    trace=demo_pb2.SearchEvidenceTrace(
                        parsed_intent=parsed_intent_json,
                        filter_applied=json.dumps({"clarify_question": clarify_q}, ensure_ascii=False),
                        candidate_count_before=candidate_count_before,
                        candidate_count_after=0,
                        refused=True,
                        input_tokens=_in_tok,
                        output_tokens=_out_tok,
                        estimated_cost_usd=_calculate_search_cost(_in_tok, _out_tok),
                    ),
                )

            # Handle cart_action search type
            if intent.get("search_type") == "cart_action":
                span.set_attribute("app.search.outcome", "cart_action")
                target_kw = intent.get("keywords") or intent.get("category") or query
                matched = _fuzzy_match_product_by_name(target_kw, all_products)
                try:
                    raw_qty = intent.get("quantity", 1)
                    qty = max(1, min(int(raw_qty), 10))
                except (ValueError, TypeError):
                    qty = 1

                if matched:
                    if not session_id:
                        return _refused_search_response(
                            parsed_intent=parsed_intent_json,
                            filter_applied="cart_confirmation_session_required",
                            before=candidate_count_before,
                            after=0,
                            input_tokens=_in_tok,
                            output_tokens=_out_tok,
                        )
                    target = matched[0]
                    confirmation_token = session_store.create_cart_proposal(
                        user_id, session_id, target.id, target.name, qty
                    )
                    proposal = demo_pb2.CartActionProposal(
                        action_type="ADD_TO_CART",
                        product_id=target.id,
                        product_name=target.name,
                        quantity=qty,
                        confirmation_required=True,
                        idempotency_key=confirmation_token,
                    )
                    if session_id:
                        session_store.append_turn(user_id, session_id, "user", query)
                        session_store.append_turn(user_id, session_id, "assistant", f"I can help add '{target.name}' to your cart.")
                    return demo_pb2.SearchProductsAIAssistantResponse(
                        results=[target],
                        trace=demo_pb2.SearchEvidenceTrace(
                            parsed_intent=parsed_intent_json,
                            filter_applied="cart_action",
                            candidate_count_before=candidate_count_before,
                            candidate_count_after=1,
                            refused=False,
                            input_tokens=_in_tok,
                            output_tokens=_out_tok,
                            estimated_cost_usd=_calculate_search_cost(_in_tok, _out_tok),
                        ),
                        action_proposal=proposal,
                    )
                else:
                    return _refused_search_response(
                        parsed_intent=parsed_intent_json,
                        filter_applied="no_cart_match",
                        before=candidate_count_before,
                        after=0,
                        input_tokens=_in_tok,
                        output_tokens=_out_tok,
                    )

            # Handle review Q&A search type ("reviews")
            if intent.get("search_type") == "reviews":
                span.set_attribute("app.search.outcome", "reviews_qa")
                target_kw = intent.get("keywords") or ""
                matched = _fuzzy_match_product_by_name(target_kw, all_products) if target_kw else []

                target_product = None
                if matched:
                    target_product = matched[0]
                else:
                    for turn in reversed(history):
                        content = turn.get("content", "")
                        for p in all_products:
                            if p.name.lower() in content.lower():
                                target_product = p
                                break
                        if target_product:
                            break

                if not target_product and all_products:
                    target_product = all_products[0]

                if target_product:
                    review_outcome = assistant.answer(target_product.id, query, session_id, user_id)
                    answer_text = review_outcome.response
                    intent["response_message"] = answer_text
                    parsed_intent_json = json.dumps(intent, ensure_ascii=False)

                    if session_id:
                        session_store.append_turn(user_id, session_id, "user", query)
                        session_store.append_turn(user_id, session_id, "assistant", answer_text)

                    return demo_pb2.SearchProductsAIAssistantResponse(
                        results=[target_product],
                        trace=demo_pb2.SearchEvidenceTrace(
                            parsed_intent=parsed_intent_json,
                            filter_applied=json.dumps({"review_qa_product_id": target_product.id}, ensure_ascii=False),
                            candidate_count_before=candidate_count_before,
                            candidate_count_after=1,
                            refused=False,
                            input_tokens=_in_tok + review_outcome.input_tokens,
                            output_tokens=_out_tok + review_outcome.output_tokens,
                            estimated_cost_usd=_calculate_search_cost(_in_tok + review_outcome.input_tokens, _out_tok + review_outcome.output_tokens),
                        ),
                    )

            valid_ids = {p.id for p in all_products}

            # --- Apply filters ---
            filtered = list(all_products)
            filters_applied = {}

            # Category filter
            category = intent.get("category", "").strip().lower()
            category_aliases = {"flashlight": "flashlights", "telescope": "telescopes", "binocular": "binoculars", "book": "books", "accessory": "accessories"}
            category = category_aliases.get(category, category)
            if category:
                filters_applied["category"] = category
                if category == "telescopes":
                    filtered = [
                        p for p in filtered
                        if any("telescopes" in c.lower() for c in p.categories)
                        and not any("accessories" in c.lower() for c in p.categories)
                    ]
                else:
                    filtered = [
                        p for p in filtered
                        if any(category in c.lower() for c in p.categories)
                    ]
from router import route_search_products_ai
       return _refused_search_response()


def search_products_ai(query: str, session_id: str = "", user_id: str = "guest"):
    return route_search_products_ai(
        query=query,
        session_id=session_id,
        user_id=user_id,
        assistant=assistant,
        product_catalog_stub=product_catalog_stub,
        record_metrics_fn=_record_search_metrics,
    )


def confirm_cart_action(user_id: str, session_id: str, confirmation_token: str):
    """Atomically consume a proposal, then perform the only Copilot cart write."""
    with tracer.start_as_current_span("confirm_cart_action") as span:
        try:
            proposal = session_store.consume_cart_proposal(user_id, session_id, confirmation_token)
        except (ValueError, RuntimeError):
            proposal = None
        if not proposal:
            span.set_attribute("app.cart.confirmation.outcome", "invalid_or_expired")
            return demo_pb2.ConfirmCartActionResponse(applied=False, outcome="invalid_or_expired")

        try:
            cart_stub.AddItem(
                demo_pb2.AddItemRequest(
                    user_id=proposal["user_id"],
                    item=demo_pb2.CartItem(
                        product_id=proposal["product_id"],
                        quantity=proposal["quantity"],
                    ),
                ),
                timeout=2.0,
            )
        except grpc.RpcError as exc:
            # The token is intentionally already consumed: retrying below the
            # confirmation boundary could duplicate a write. The user must ask
            # for a fresh proposal after a downstream failure.
            logger.warning("copilot_cart_confirmation_failed", extra={"grpc_code": str(exc.code())})
            span.set_attribute("app.cart.confirmation.outcome", "downstream_failed")
            return demo_pb2.ConfirmCartActionResponse(applied=False, outcome="downstream_failed")

        span.set_attribute("app.cart.confirmation.outcome", "applied")
        span.set_attribute("app.cart.product_id", proposal["product_id"])
        return demo_pb2.ConfirmCartActionResponse(applied=True, outcome="applied")


def _record_search_metrics(
    *,
    model_id: str,
    guardrail_version: str,
    outcome: str,
    error_class: str | None,
    latency_ms: float,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Update all Prometheus/OTel metrics for a search Bedrock call.

    Mirrors the telemetry block in get_ai_assistant_response() so that search
    traffic is visible to the same budget-cap alerts (daily/hourly token cost,
    error rate, latency p95) established for the Q&A path.
    """
    attributes = {
        "llm.model": model_id,
        "llm.call": "parse_search_intent",
        "llm.outcome": outcome,
        "guardrail.version": guardrail_version,
        "error.class": error_class or "none",
    }
    product_review_svc_metrics["app_ai_assistant_counter"].add(1, attributes)
    # Always count the Bedrock call and record latency/tokens — even on failure —
    # so cost accounting remains accurate.
    product_review_svc_metrics["app_llm_call_counter"].add(1, attributes)
    if latency_ms > 0:
        product_review_svc_metrics["app_llm_latency_histogram"].record(latency_ms / 1_000, attributes)
    product_review_svc_metrics["app_llm_prompt_tokens_counter"].add(input_tokens, attributes)
    product_review_svc_metrics["app_llm_completion_tokens_counter"].add(output_tokens, attributes)
    estimated_cost = (
        input_tokens * float(os.environ.get("BEDROCK_INPUT_USD_PER_MILLION", "1"))
        + output_tokens * float(os.environ.get("BEDROCK_OUTPUT_USD_PER_MILLION", "5"))
    ) / 1_000_000
    product_review_svc_metrics["app_llm_estimated_cost_counter"].add(estimated_cost, attributes)
    if outcome == "unavailable":
        product_review_svc_metrics["app_ai_fallback_counter"].add(1, attributes)
        product_review_svc_metrics["app_llm_error_counter"].add(1, attributes)



def configure_logging(service_name: str) -> None:
    provider = LoggerProvider(resource=Resource.create({"service.name": service_name}))
    set_logger_provider(provider)
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(insecure=True)))
    logger.addHandler(LoggingHandler(level=logging.NOTSET, logger_provider=provider))


def main() -> None:
    global tracer, product_review_svc_metrics, product_catalog_stub, cart_stub, assistant
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
    cart_stub = demo_pb2_grpc.CartServiceStub(
        grpc.insecure_channel(must_map_env("CART_ADDR"))
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
