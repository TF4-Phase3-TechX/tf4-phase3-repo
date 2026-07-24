#!/usr/bin/python

"""Dynamic per-turn intent classification, allow-list enforcement, and routing module."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

import demo_pb2
from bedrock_adapter import (
    IntentLabel,
    ProviderFailure,
    call_tool,
    _map_search_type_to_intent,
    _is_fastpath_chitchat,
    resolve_referenced_product,
    _fuzzy_match_token,
    STOP_WORDS,
)
from copilot_review_summary import summarize_copilot_reviews
from safety import MAX_QUESTION_CHARS, contains_pii, is_attack, normalize_text
from session_store import session_store

logger = logging.getLogger(__name__)

INTENT_CONFIDENCE_THRESHOLD = float(os.environ.get("INTENT_CONFIDENCE_THRESHOLD", "0.6"))
HISTORY_WINDOW_N = int(os.environ.get("HISTORY_WINDOW_N", "5"))


def _calculate_search_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * float(os.environ.get("BEDROCK_INPUT_USD_PER_MILLION", "1"))
        + output_tokens * float(os.environ.get("BEDROCK_OUTPUT_USD_PER_MILLION", "5"))
    ) / 1_000_000


def _make_refused_trace(parsed_intent="", filter_applied="", before=0, after=0, input_tokens=0, output_tokens=0, refusal_reason=""):
    cost = _calculate_search_cost(input_tokens, output_tokens)
    if refusal_reason:
        try:
            d = json.loads(filter_applied) if isinstance(filter_applied, str) and filter_applied.startswith("{") else {}
            d["refusal_reason"] = refusal_reason
            filter_applied = json.dumps(d, ensure_ascii=False)
        except Exception:
            filter_applied = json.dumps({"refusal_reason": refusal_reason}, ensure_ascii=False)

    trace = demo_pb2.SearchEvidenceTrace(
        parsed_intent=parsed_intent,
        filter_applied=filter_applied,
        candidate_count_before=before,
        candidate_count_after=after,
        refused=True,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
    )
    if hasattr(trace, "refusal_reason"):
        try:
            setattr(trace, "refusal_reason", refusal_reason)
        except Exception:
            pass
    return trace


def _refused_search_response(
    parsed_intent="",
    filter_applied="",
    before=0,
    after=0,
    input_tokens=0,
    output_tokens=0,
    refusal_reason="",
    response="",
    outcome="refused",
):
    return demo_pb2.SearchProductsAIAssistantResponse(
        results=[],
        trace=_make_refused_trace(parsed_intent, filter_applied, before, after, input_tokens, output_tokens, refusal_reason=refusal_reason),
        response=response,
        outcome=outcome,
    )


def _fuzzy_match_keywords(keywords_query: str, name: str, description: str = "") -> bool:
    """Resolve catalog entity names only; descriptions are not intent routers."""
    raw_tokens = [tok for tok in keywords_query.lower().split() if tok not in STOP_WORDS]
    if not raw_tokens:
        return True
    for kw_tok in raw_tokens:
        if not _fuzzy_match_token(kw_tok, name):
            return False
    return True


def _is_vietnamese(query: str) -> bool:
    lowered = query.lower()
    return any(char in lowered for char in "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")


def _message(query: str, vi: str, en: str) -> str:
    return vi if _is_vietnamese(query) else en


def _product_price(product: Any) -> float:
    price = getattr(product, "price_usd", None)
    if price is None:
        return 0.0
    return float(getattr(price, "units", 0) or 0) + float(getattr(price, "nanos", 0) or 0) / 1e9


def _comparison_category_candidates(products: list[Any], category: str) -> list[Any]:
    category = (category or "").strip().lower()
    if not category:
        return list(products)
    candidates = [p for p in products if any(category == c.lower() for c in getattr(p, "categories", []))]
    if category == "telescopes":
        candidates = [p for p in candidates if not any("accessories" in c.lower() for c in getattr(p, "categories", []))]
    return candidates


def _last_search_candidates(products: list[Any], session_id: str, user_id: str) -> list[Any]:
    stored = session_store.get_last_search_products(user_id, session_id) if session_id else []
    stored_ids = {
        row.get("id") if isinstance(row, dict) else getattr(row, "id", None)
        for row in stored
    }
    return [product for product in products if product.id in stored_ids]


def _explicit_catalog_scope(query: str) -> bool:
    normalized = query.lower()
    return any(marker in normalized for marker in ("toàn bộ catalog", "toàn catalog", "entire catalog", "whole catalog"))


def _comparison_candidates(
    intent: dict[str, Any], products: list[Any], session_id: str, user_id: str, query: str
) -> tuple[list[Any], str]:
    """Choose a trusted candidate scope before resolving comparison selectors."""
    targets = intent.get("comparison_targets") or []
    if len(targets) >= 2:
        return list(products), "explicit_targets"
    if _explicit_catalog_scope(query):
        return list(products), "catalog"
    category = str(intent.get("category") or "").strip()
    if category:
        return _comparison_category_candidates(products, category), "explicit_category"
    last_search = _last_search_candidates(products, session_id, user_id)
    if len(last_search) >= 2:
        return last_search, "last_search"
    return [], "none"


def _resolve_relative_comparison(
    intent: dict[str, Any], products: list[Any], session_id: str, user_id: str
) -> tuple[list[Any], str]:
    """Resolve an anchor plus a strictly cheaper/more-expensive counterpart."""
    relation = intent.get("comparison_relation")
    targets = intent.get("comparison_targets") or []
    last_search = _last_search_candidates(products, session_id, user_id)
    anchor = resolve_referenced_product([], products, keywords=targets[0]) if len(targets) == 1 else None
    if anchor is None and len(last_search) == 1:
        anchor = last_search[0]
    if anchor is None:
        return [], "none"

    counterpart_pool = [product for product in last_search if product.id != anchor.id]
    scope = "last_search"
    if not counterpart_pool:
        categories = list(getattr(anchor, "categories", []))
        category = "telescopes" if "telescopes" in categories else (categories[0] if categories else "")
        counterpart_pool = [product for product in _comparison_category_candidates(products, category) if product.id != anchor.id]
        scope = "anchor_category"

    if relation == "cheaper":
        candidates = [product for product in counterpart_pool if _product_price(product) < _product_price(anchor)]
        counterpart = max(candidates, key=_product_price) if candidates else None
    else:
        candidates = [product for product in counterpart_pool if _product_price(product) > _product_price(anchor)]
        counterpart = min(candidates, key=_product_price) if candidates else None
    return ([anchor, counterpart], scope) if counterpart else ([], scope)


def _resolve_comparison_products(intent: dict[str, Any], products: list[Any]) -> list[Any]:
    """Resolve explicit names/selectors to exactly two grounded catalog records."""
    candidates = list(products)
    category = str(intent.get("category") or "").strip()
    if category:
        candidates = _comparison_category_candidates(candidates, category)
    resolved: list[Any] = []
    for target_name in intent.get("comparison_targets") or []:
        match = resolve_referenced_product([], candidates, keywords=target_name)
        if match is None:
            return []
        resolved.append(match)

    priced = [p for p in candidates if _product_price(p) > 0]
    for selector in intent.get("comparison_selectors") or []:
        if not priced:
            return []
        if selector == "cheapest":
            resolved.append(min(priced, key=_product_price))
        elif selector == "most_expensive":
            resolved.append(max(priced, key=_product_price))

    unique: list[Any] = []
    seen: set[str] = set()
    for product in resolved:
        if product.id not in seen:
            unique.append(product)
            seen.add(product.id)
    return unique if len(unique) == 2 else []


def route_search_products_ai(
    query: str,
    session_id: str,
    assistant: Any,
    product_catalog_stub: Any,
    tracer: Any,
    record_metrics_fn: Callable,
    user_id: str = "guest",
    fetch_reviews: Callable[[str], list[tuple[Any, ...]]] | None = None,
) -> demo_pb2.SearchProductsAIAssistantResponse:
    """Orchestrate per-turn dynamic intent classification and tool allow-list routing."""
    with tracer.start_as_current_span("search_products_ai") as span:
        span.set_attribute("app.caller.feature", "copilot_search")
        # --- 1. Input validation ---
        if not query or not query.strip():
            span.set_attribute("app.search.outcome", "empty_query")
            return _refused_search_response(
                refusal_reason="guardrail_blocked",
                response="Vui lòng nhập câu hỏi hoặc yêu cầu tìm kiếm.",
                outcome="blocked",
            )

        query = normalize_text(query, MAX_QUESTION_CHARS)

        # --- 2. Guardrail Check (TF4AIO-26) runs FIRST ---
        if is_attack(query) or contains_pii(query):
            span.set_attribute("app.search.outcome", "blocked")
            return _refused_search_response(
                refusal_reason="guardrail_blocked",
                response=_message(
                    query,
                    "Tôi không thể xử lý yêu cầu này. Bạn có thể hỏi về sản phẩm trong danh mục.",
                    "I cannot process that request. You can ask about products in the catalog.",
                ),
                outcome="blocked",
            )

        try:
            # --- 3. Fetch & sanitize multi-turn conversation history ---
            raw_history = session_store.get_history(user_id, session_id) if session_id else []
            sanitized_history = []
            for turn in raw_history[-HISTORY_WINDOW_N:]:
                r = turn.get("role", "user")
                c = turn.get("content", "")
                if is_attack(c) or contains_pii(c):
                    continue
                sanitized_history.append({"role": r, "content": c})

            # --- 4. Fast-path chitchat check vs. LLM per-turn intent classification ---
            if _is_fastpath_chitchat(query):
                intent = {
                    "search_type": "chitchat",
                    "confidence_score": 1.0,
                }
            else:
                intent = assistant.provider.parse_search_intent(query, history=sanitized_history)

            _metadata = intent.get("_metadata") or {}
            _in_tok = _metadata.get("input_tokens", 0)
            _out_tok = _metadata.get("output_tokens", 0)
            _lat_ms = _metadata.get("latency_ms", 0.0)

            confidence_score = float(intent.get("confidence_score", 0.95))
            raw_search_type = intent.get("search_type", "")
            intent_label = _map_search_type_to_intent(raw_search_type)

            # Rescue queries containing specific catalog product names (e.g. "Comet Book") from being wrongly refused as OUT_OF_SCOPE/UNCLEAR
            if raw_search_type == "out_of_scope" or intent_label == IntentLabel.UNCLEAR:
                try:
                    catalog_resp = product_catalog_stub.ListProducts(demo_pb2.Empty(), timeout=2.0)
                    matched_product = resolve_referenced_product(
                        [],
                        list(catalog_resp.products),
                        keywords=query,
                    )
                    if matched_product:
                        raw_search_type = "search"
                        intent["search_type"] = "search"
                        intent["keywords"] = matched_product.name
                        intent_label = IntentLabel.PRODUCT_SEARCH
                except Exception as e:
                    logger.warning(f"Failed to check catalog for out_of_scope rescue: {e}")

            # Enforce confidence threshold for unclear fallback
            if confidence_score < INTENT_CONFIDENCE_THRESHOLD and intent_label != IntentLabel.CHITCHAT:
                intent_label = IntentLabel.UNCLEAR
                intent["search_type"] = "unclear"
                intent["clarify_question"] = "Tôi chưa hiểu rõ ý định của bạn. Bạn muốn tìm sản phẩm, xem đánh giá/review hay thêm sản phẩm vào giỏ hàng?"

            parsed_intent_json = json.dumps({k: v for k, v in intent.items() if k != "_metadata"}, ensure_ascii=False)
            span.set_attribute("app.search.search_type", intent.get("search_type", ""))
            span.set_attribute("app.search.intent_label", intent_label.value)
            span.set_attribute("app.search.confidence_score", confidence_score)

            # Bug #14 fix: Remove query and session_id from extra to prevent PII logging
            logger.info(
                "intent_classified",
                extra={
                    "search_type": raw_search_type,
                    "intent_label": intent_label.value,
                    "confidence_score": confidence_score,
                    "turn_count": len(sanitized_history) // 2 + 1,
                },
            )

            # Record Stage-1 intent classification telemetry metrics
            if record_metrics_fn:
                record_metrics_fn(
                    model_id=assistant.provider.model_id,
                    guardrail_version=assistant.provider.guardrail_version,
                    operation="parse_search_intent",
                    outcome="success",
                    error_class=None,
                    latency_ms=_lat_ms,
                    input_tokens=_in_tok,
                    output_tokens=_out_tok,
                )

            # --- 5. Routing by IntentLabel with Runtime Allow-List Enforcement ---

            # A. CHITCHAT Intent -> No tools allowed
            if intent_label == IntentLabel.CHITCHAT or raw_search_type == "out_of_scope":
                span.set_attribute("app.search.outcome", "chitchat")
                if raw_search_type == "out_of_scope":
                    msg = _message(
                        query,
                        "Tôi là trợ lý mua sắm cho sản phẩm trong danh mục. Bạn muốn tìm, so sánh hay xem đánh giá sản phẩm nào?",
                        "I am a shopping assistant for catalog products. What would you like to find, compare, or review?",
                    )
                    outcome = "out_of_scope"
                else:
                    msg = _message(
                        query,
                        "Xin chào! Tôi có thể giúp bạn tìm, so sánh hoặc xem đánh giá sản phẩm.",
                        "Hello! I can help you find, compare, or review products.",
                    )
                    outcome = "chitchat"
                if session_id:
                    session_store.append_turn(user_id, session_id, "user", query)
                    session_store.append_turn(user_id, session_id, "assistant", msg)
                return _refused_search_response(
                    parsed_intent=parsed_intent_json,
                    input_tokens=_in_tok,
                    output_tokens=_out_tok,
                    refusal_reason="llm_classified_out_of_scope",
                    response=msg,
                    outcome=outcome,
                )

            # B. UNCLEAR Intent -> No tools allowed, ask for clarification
            if intent_label == IntentLabel.UNCLEAR:
                span.set_attribute("app.search.outcome", "unclear")
                clarify_q = intent.get("clarify_question") or "Tôi chưa hiểu rõ ý định của bạn. Bạn muốn tìm kiếm sản phẩm hay xem đánh giá/review?"
                if session_id:
                    session_store.append_turn(user_id, session_id, "user", query)
                    session_store.append_turn(user_id, session_id, "assistant", clarify_q)
                return demo_pb2.SearchProductsAIAssistantResponse(
                    results=[],
                    response=clarify_q,
                    outcome="clarification_required",
                    trace=_make_refused_trace(
                        parsed_intent=parsed_intent_json,
                        filter_applied=json.dumps({"clarify_question": clarify_q}, ensure_ascii=False),
                        before=0,
                        after=0,
                        input_tokens=_in_tok,
                        output_tokens=_out_tok,
                        refusal_reason="llm_classified_out_of_scope",
                    ),
                )

            # Fetch catalog products (via catalog_search tool)
            catalog_response = call_tool(
                intent_label,
                "catalog_search",
                lambda: product_catalog_stub.ListProducts(demo_pb2.Empty(), timeout=2.0),
            )
            all_products = list(catalog_response.products)
            candidate_count_before = len(all_products)

            # C. COMPARE -> resolve catalog operands first, then synthesize a
            # grounded comparison from product fields and review evidence.
            if intent_label == IntentLabel.COMPARE:
                span.set_attribute("app.search.outcome", "compare")
                if intent.get("comparison_relation"):
                    compared, comparison_scope = _resolve_relative_comparison(
                        intent, all_products, session_id, user_id
                    )
                else:
                    candidates, comparison_scope = _comparison_candidates(
                        intent, all_products, session_id, user_id, query
                    )
                    compared = _resolve_comparison_products(intent, candidates)
                if len(compared) != 2:
                    clarify_q = _message(
                        query,
                        "Tôi chưa xác định được chính xác hai sản phẩm cần so sánh. Bạn có thể nêu hai tên sản phẩm hoặc phạm vi danh mục không?",
                        "I could not resolve exactly two products to compare. Please provide two product names or a catalog category.",
                    )
                    intent["search_type"] = "unclear"
                    intent["clarify_question"] = clarify_q
                    parsed_intent_json = json.dumps(intent, ensure_ascii=False)
                    return _refused_search_response(
                        parsed_intent=parsed_intent_json,
                        filter_applied=json.dumps({
                            "comparison_targets": intent.get("comparison_targets", []),
                            "comparison_selectors": intent.get("comparison_selectors", []),
                            "comparison_scope": comparison_scope,
                        }, ensure_ascii=False),
                        before=candidate_count_before,
                        after=0,
                        input_tokens=_in_tok,
                        output_tokens=_out_tok,
                        refusal_reason="comparison_resolution_failed",
                        response=clarify_q,
                        outcome="clarification_required",
                    )

                comparison_outcome = call_tool(
                    IntentLabel.COMPARE,
                    "bedrock_compare",
                    lambda: assistant.compare_products(compared, query, session_id, user_id),
                )
                answer_text = comparison_outcome.response
                intent["response_message"] = answer_text  # compatibility for older clients
                parsed_intent_json = json.dumps(intent, ensure_ascii=False)
                total_input = _in_tok + comparison_outcome.input_tokens
                total_output = _out_tok + comparison_outcome.output_tokens
                if record_metrics_fn:
                    record_metrics_fn(
                        model_id=assistant.provider.model_id,
                        guardrail_version=assistant.provider.guardrail_version,
                        operation="compare_products",
                        outcome=comparison_outcome.outcome,
                        error_class=comparison_outcome.error_class or None,
                        latency_ms=comparison_outcome.latency_ms,
                        input_tokens=comparison_outcome.input_tokens,
                        output_tokens=comparison_outcome.output_tokens,
                    )
                if session_id:
                    session_store.set_last_search_products(
                        user_id,
                        session_id,
                        [{"id": p.id, "name": p.name, "description": p.description, "categories": list(p.categories)} for p in compared],
                    )
                return demo_pb2.SearchProductsAIAssistantResponse(
                    results=compared,
                    response=answer_text,
                    outcome=comparison_outcome.outcome,
                    trace=demo_pb2.SearchEvidenceTrace(
                        parsed_intent=parsed_intent_json,
                        filter_applied=json.dumps({
                            "comparison_product_ids": [p.id for p in compared],
                            "comparison_scope": comparison_scope,
                            "comparison_criteria": intent.get("comparison_criteria") or [
                                "price", "features", "customer_feedback", "best_for"
                            ],
                        }, ensure_ascii=False),
                        candidate_count_before=candidate_count_before,
                        candidate_count_after=2,
                        refused=False,
                        input_tokens=total_input,
                        output_tokens=total_output,
                        estimated_cost_usd=_calculate_search_cost(total_input, total_output),
                    ),
                )

            # D. PURCHASE (Cart Action) Intent -> Allowed tool: "cart_action"
            if intent_label == IntentLabel.PURCHASE:
                span.set_attribute("app.search.outcome", "cart_action")
                target_kw = intent.get("keywords") or ""
                target = resolve_referenced_product(
                    sanitized_history,
                    all_products,
                    target_kw,
                    query=query,
                    session_id=session_id,
                    user_id=user_id,
                    category=intent.get("category") or "",
                    price_selector={
                        "price_asc": "cheapest",
                        "price_desc": "most_expensive",
                    }.get(intent.get("sort_by"), ""),
                )
                try:
                    raw_qty = intent.get("quantity", 1)
                    qty = int(raw_qty)
                except (ValueError, TypeError):
                    qty = 1

                if qty > 10:
                    limit_msg = _message(
                        query,
                        "Mỗi lần chỉ có thể thêm tối đa 10 sản phẩm vào giỏ hàng. Bạn muốn thêm 10 sản phẩm chứ?",
                        "You can add at most 10 items to the cart at a time. Would you like to add 10 items?",
                    )
                    return _refused_search_response(
                        parsed_intent=json.dumps(intent, ensure_ascii=False),
                        filter_applied=json.dumps({"quantity": qty, "maximum_quantity": 10}, ensure_ascii=False),
                        before=candidate_count_before,
                        after=0,
                        input_tokens=_in_tok,
                        output_tokens=_out_tok,
                        refusal_reason="quantity_limit_exceeded",
                        response=limit_msg,
                        outcome="quantity_limit_exceeded",
                    )
                qty = max(1, qty)

                if target:
                    confirmation_token = session_store.create_cart_proposal(
                        user_id, session_id, target.id, target.name, qty
                    )
                    proposal = call_tool(
                        IntentLabel.PURCHASE,
                        "cart_action",
                        lambda: demo_pb2.CartActionProposal(
                            action_type="ADD_TO_CART",
                            product_id=target.id,
                            product_name=target.name,
                            quantity=qty,
                            confirmation_required=True,
                            idempotency_key=confirmation_token,
                        ),
                    )
                    confirmation_msg = f"Tôi tìm thấy sản phẩm **{target.name}**. Bạn muốn thêm {qty} sản phẩm này vào giỏ hàng chứ?"
                    intent["response_message"] = confirmation_msg
                    parsed_intent_json = json.dumps(intent, ensure_ascii=False)
                    if session_id:
                        session_store.append_turn(user_id, session_id, "user", query)
                        session_store.append_turn(user_id, session_id, "assistant", confirmation_msg)
                    return demo_pb2.SearchProductsAIAssistantResponse(
                        results=[target],
                        response=confirmation_msg,
                        outcome="action_confirmation_required",
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
                    # Bug #20 fix: Include clarify_question for PURCHASE miss
                    clarify_q = "Tôi chưa tìm thấy sản phẩm bạn muốn thêm vào giỏ hàng. Bạn có thể cho biết tên sản phẩm cụ thể không?"
                    intent["search_type"] = "unclear"
                    intent["clarify_question"] = clarify_q
                    intent["response_message"] = clarify_q
                    parsed_intent_json = json.dumps(intent, ensure_ascii=False)
                    if session_id:
                        session_store.append_turn(user_id, session_id, "user", query)
                        session_store.append_turn(user_id, session_id, "assistant", clarify_q)
                    return demo_pb2.SearchProductsAIAssistantResponse(
                        results=[],
                        response=clarify_q,
                        outcome="clarification_required",
                        trace=_make_refused_trace(
                            parsed_intent=parsed_intent_json,
                            filter_applied=json.dumps({"clarify_question": clarify_q}, ensure_ascii=False),
                            before=candidate_count_before,
                            after=0,
                            input_tokens=_in_tok,
                            output_tokens=_out_tok,
                            refusal_reason="no_match_after_filter",
                        ),
                    )

            # E. REVIEW_QA Intent -> Allowed tool: "get_product_reviews".
            # Copilot deliberately does not invoke the model-backed review Q&A.
            if intent_label == IntentLabel.REVIEW_QA:
                span.set_attribute("app.search.outcome", "reviews_qa")
                target_kw = intent.get("keywords") or ""
                target_product = resolve_referenced_product(
                    sanitized_history,
                    all_products,
                    target_kw,
                    query=query,
                    session_id=session_id,
                    user_id=user_id,
                    category=intent.get("category") or "",
                    price_selector={
                        "price_asc": "cheapest",
                        "price_desc": "most_expensive",
                    }.get(intent.get("sort_by"), ""),
                )

                if target_product:
                    # Copilot review summaries are deterministic and separate
                    # from the model-backed product detail Q&A path.
                    review_rows = call_tool(
                        IntentLabel.REVIEW_QA,
                        "get_product_reviews",
                        lambda: fetch_reviews(target_product.id) if fetch_reviews else [],
                    )
                    answer_text, review_outcome, _quarantined_reviews = summarize_copilot_reviews(
                        query, target_product, review_rows
                    )
                    intent["response_message"] = answer_text
                    parsed_intent_json = json.dumps(intent, ensure_ascii=False)
                    if session_id:
                        session_store.append_turn(user_id, session_id, "user", query)
                        session_store.append_turn(user_id, session_id, "assistant", answer_text)

                    return demo_pb2.SearchProductsAIAssistantResponse(
                        results=[target_product],
                        response=answer_text,
                        outcome=review_outcome,
                        trace=demo_pb2.SearchEvidenceTrace(
                            parsed_intent=parsed_intent_json,
                            filter_applied=json.dumps({"review_qa_product_id": target_product.id}, ensure_ascii=False),
                            candidate_count_before=candidate_count_before,
                            candidate_count_after=1,
                            refused=False,
                            input_tokens=_in_tok,
                            output_tokens=_out_tok,
                            estimated_cost_usd=_calculate_search_cost(_in_tok, _out_tok),
                        ),
                    )
                else:
                    clarify_q = "Bạn muốn xem đánh giá của sản phẩm nào? Bạn có thể cho biết tên sản phẩm cụ thể không?"
                    intent["search_type"] = "unclear"
                    intent["clarify_question"] = clarify_q
                    intent["response_message"] = clarify_q
                    parsed_intent_json = json.dumps(intent, ensure_ascii=False)
                    if session_id:
                        session_store.append_turn(user_id, session_id, "user", query)
                        session_store.append_turn(user_id, session_id, "assistant", clarify_q)
                    return demo_pb2.SearchProductsAIAssistantResponse(
                        results=[],
                        response=clarify_q,
                        outcome="clarification_required",
                        trace=_make_refused_trace(
                            parsed_intent=parsed_intent_json,
                            filter_applied=json.dumps({"clarify_question": clarify_q}, ensure_ascii=False),
                            before=candidate_count_before,
                            after=0,
                            input_tokens=_in_tok,
                            output_tokens=_out_tok,
                            refusal_reason="no_match_after_filter",
                        ),
                    )

            # F. PRODUCT_SEARCH Intent -> Allowed tool: "catalog_search"
            valid_ids = {p.id for p in all_products}
            filtered = list(all_products)
            filters_applied = {}

            # Category filter
            category = intent.get("category", "").strip().lower()
            category_aliases = {"flashlight": "flashlights", "telescope": "telescopes", "binocular": "binoculars", "book": "books", "accessory": "accessories"}
            category = category_aliases.get(category, category)
            if category:
                filters_applied["category"] = category
                filtered = [p for p in filtered if any(category in c.lower() for c in p.categories)]
                if category == "telescopes":
                    filtered = [p for p in filtered if not any("accessories" in c.lower() for c in p.categories)]

            # Price filters
            price_min = intent.get("price_min")
            if price_min is not None:
                filters_applied["price_min"] = price_min
                filtered = [p for p in filtered if (p.price_usd.units + p.price_usd.nanos / 1e9) >= price_min]

            price_max = intent.get("price_max")
            if price_max is not None:
                filters_applied["price_max"] = price_max
                filtered = [p for p in filtered if (p.price_usd.units + p.price_usd.nanos / 1e9) <= price_max]

            # Keyword fuzzy filter
            keywords = intent.get("keywords", "").strip()
            if keywords:
                filters_applied["keywords"] = keywords
                filtered = [p for p in filtered if _fuzzy_match_keywords(keywords, p.name, p.description)]

            # Sort filter
            sort_by = intent.get("sort_by")
            if sort_by == "price_asc":
                filters_applied["sort_by"] = "price_asc"
                filtered.sort(key=lambda p: (0 if (p.price_usd.units + p.price_usd.nanos / 1e9) > 0 else 1, p.price_usd.units + p.price_usd.nanos / 1e9))
            elif sort_by == "price_desc":
                filters_applied["sort_by"] = "price_desc"
                filtered.sort(key=lambda p: (0 if (p.price_usd.units + p.price_usd.nanos / 1e9) > 0 else 1, p.price_usd.units + p.price_usd.nanos / 1e9), reverse=True)
            result_limit = intent.get("result_limit")
            if isinstance(result_limit, int):
                filters_applied["result_limit"] = result_limit
                filtered = filtered[:result_limit]

            # Grounding shield
            filtered = [p for p in filtered if p.id in valid_ids]

            filter_applied_json = json.dumps(filters_applied, ensure_ascii=False)
            candidate_count_after = len(filtered)

            route_outcome = "success" if candidate_count_after > 0 else "refused"
            span.set_attribute("app.search.candidate_count_before", candidate_count_before)
            span.set_attribute("app.search.candidate_count_after", candidate_count_after)
            span.set_attribute("app.search.outcome", route_outcome)

            if candidate_count_after == 0:
                try:
                    d = json.loads(filter_applied_json) if isinstance(filter_applied_json, str) and filter_applied_json.startswith("{") else {}
                    d["refusal_reason"] = "no_match_after_filter"
                    filter_applied_json = json.dumps(d, ensure_ascii=False)
                except Exception:
                    filter_applied_json = json.dumps({"refusal_reason": "no_match_after_filter"}, ensure_ascii=False)

            trace_msg = demo_pb2.SearchEvidenceTrace(
                parsed_intent=parsed_intent_json,
                filter_applied=filter_applied_json,
                candidate_count_before=candidate_count_before,
                candidate_count_after=candidate_count_after,
                refused=(candidate_count_after == 0),
                input_tokens=_in_tok,
                output_tokens=_out_tok,
                estimated_cost_usd=_calculate_search_cost(_in_tok, _out_tok),
            )
            if candidate_count_after == 0 and hasattr(trace_msg, "refusal_reason"):
                try:
                    setattr(trace_msg, "refusal_reason", "no_match_after_filter")
                except Exception:
                    pass

            if filtered:
                p_names = ", ".join(p.name for p in filtered[:3])
                summary_text = _message(
                    query,
                    f"Tìm thấy {len(filtered)} sản phẩm phù hợp. Nổi bật: {p_names}.",
                    f"Found {len(filtered)} matching products. Top results: {p_names}.",
                )
            else:
                summary_text = _message(
                    query,
                    "Tôi chưa tìm thấy sản phẩm phù hợp. Bạn có thể thử tên sản phẩm, danh mục hoặc khoảng giá khác.",
                    "I could not find a matching product. Try another product name, category, or price range.",
                )

            if session_id:
                if filtered:
                    prod_dicts = [
                        {
                            "id": p.id,
                            "name": p.name,
                            "description": getattr(p, "description", ""),
                            "categories": list(getattr(p, "categories", [])),
                        }
                        for p in filtered
                    ]
                    session_store.set_last_search_products(user_id, session_id, prod_dicts)
                session_store.append_turn(user_id, session_id, "user", query)
                session_store.append_turn(user_id, session_id, "assistant", summary_text)

            return demo_pb2.SearchProductsAIAssistantResponse(
                results=filtered,
                response=summary_text,
                outcome="success" if filtered else "no_match",
                trace=trace_msg,
            )
        except ProviderFailure as exc:
            span.set_attribute("app.search.outcome", "provider_failure")
            span.set_attribute("error.class", exc.error_class)
            logger.warning("parse_search_intent_provider_failure: %s", exc)
            if record_metrics_fn:
                record_metrics_fn(
                    model_id=getattr(assistant.provider, "model_id", "unknown"),
                    guardrail_version=getattr(assistant.provider, "guardrail_version", "disabled"),
                    operation="parse_search_intent",
                    outcome="fallback" if exc.error_class == "guardrail_intervened" else "error",
                    error_class=exc.error_class,
                    latency_ms=getattr(exc, "latency_ms", 0.0),
                    input_tokens=getattr(exc, "input_tokens", 0),
                    output_tokens=getattr(exc, "output_tokens", 0),
                )
            ref_reason = "schema_validation_failed" if exc.error_class == "invalid_response" else (
                "guardrail_blocked" if exc.error_class == "guardrail_intervened" else "provider_failure"
            )
            return _refused_search_response(
                input_tokens=getattr(exc, "input_tokens", 0),
                output_tokens=getattr(exc, "output_tokens", 0),
                refusal_reason=ref_reason,
                response=_message(
                    query,
                    "Copilot hiện tạm thời không khả dụng. Vui lòng thử lại sau.",
                    "Copilot is temporarily unavailable. Please try again later.",
                ),
                outcome="provider_unavailable",
            )
        except Exception as exc:
            span.set_attribute("app.search.outcome", "error")
            span.set_attribute("error.class", type(exc).__name__.lower()[:64])
            logger.error("search_products_ai_failed", exc_info=exc)
            return _refused_search_response(
                refusal_reason="provider_failure",
                response=_message(
                    query,
                    "Copilot hiện tạm thời không khả dụng. Vui lòng thử lại sau.",
                    "Copilot is temporarily unavailable. Please try again later.",
                ),
                outcome="provider_unavailable",
            )
