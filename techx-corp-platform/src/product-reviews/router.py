#!/usr/bin/python

"""Dynamic per-turn intent classification, allow-list enforcement, and routing module."""

from __future__ import annotations

import difflib
import json
import logging
import os
import uuid
from typing import Any, Callable

import demo_pb2
from bedrock_adapter import (
    IntentLabel,
    TOOL_ALLOW_LIST,
    ToolNotAllowedError,
    call_tool,
    _map_search_type_to_intent,
    _is_fastpath_chitchat,
    _is_review_query,
    resolve_referenced_product,
)
from safety import MAX_QUESTION_CHARS, contains_pii, is_attack, normalize_text
from session_store import session_store

logger = logging.getLogger(__name__)

INTENT_CONFIDENCE_THRESHOLD = float(os.environ.get("INTENT_CONFIDENCE_THRESHOLD", "0.6"))
HISTORY_WINDOW_N = int(os.environ.get("HISTORY_WINDOW_N", "5"))

STOP_WORDS = {
    "có", "những", "loại", "nào", "gì", "cho", "tôi", "em", "bạn", "nhé", "không", "muốn", "tìm", "xem", "các", "mẫu",
    "show", "me", "all", "the", "what", "are", "is", "a", "an", "of", "for", "with", "in", "on", "can", "you", "please", "tell"
}


def _calculate_search_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * float(os.environ.get("BEDROCK_INPUT_USD_PER_MILLION", "1"))
        + output_tokens * float(os.environ.get("BEDROCK_OUTPUT_USD_PER_MILLION", "5"))
    ) / 1_000_000


def _make_refused_trace(parsed_intent="", filter_applied="", before=0, after=0, input_tokens=0, output_tokens=0):
    cost = _calculate_search_cost(input_tokens, output_tokens)
    return demo_pb2.SearchEvidenceTrace(
        parsed_intent=parsed_intent,
        filter_applied=filter_applied,
        candidate_count_before=before,
        candidate_count_after=after,
        refused=True,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
    )


def _refused_search_response(parsed_intent="", filter_applied="", before=0, after=0, input_tokens=0, output_tokens=0):
    return demo_pb2.SearchProductsAIAssistantResponse(
        results=[],
        trace=_make_refused_trace(parsed_intent, filter_applied, before, after, input_tokens, output_tokens),
    )


def _fuzzy_match_token(keyword_token: str, product_text: str) -> bool:
    clean_text = "".join(c if c.isalnum() or c.isspace() else " " for c in product_text.lower())
    product_tokens = clean_text.split()
    kw_len = len(keyword_token)
    if kw_len <= 3:
        threshold = 1.0
    elif 4 <= kw_len <= 6:
        threshold = 0.60
    else:
        threshold = 0.75
    for p_token in product_tokens:
        ratio = difflib.SequenceMatcher(None, keyword_token, p_token).ratio()
        if ratio >= threshold or keyword_token in p_token:
            return True
    return False


def _fuzzy_match_keywords(keywords_query: str, name: str, description: str) -> bool:
    raw_tokens = [tok for tok in keywords_query.lower().split() if tok not in STOP_WORDS]
    if not raw_tokens:
        return True
    for kw_tok in raw_tokens:
        if not (_fuzzy_match_token(kw_tok, name) or _fuzzy_match_token(kw_tok, description)):
            return False
    return True


def _fuzzy_match_product_by_name(query_name: str, products: list) -> list:
    if not query_name or not query_name.strip():
        return []
    target_tokens = [t.lower() for t in query_name.strip().split() if len(t) > 1 and t.lower() not in STOP_WORDS]
    if not target_tokens:
        return []
    scored_products = []
    for p in products:
        p_name_lower = p.name.lower()
        match_count = sum(1 for t_tok in target_tokens if _fuzzy_match_token(t_tok, p_name_lower))
        if match_count > 0:
            scored_products.append((match_count, p))
    scored_products.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored_products]


def route_search_products_ai(
    query: str,
    session_id: str,
    assistant: Any,
    product_catalog_stub: Any,
    tracer: Any,
    record_metrics_fn: Callable,
    user_id: str = "guest",
) -> demo_pb2.SearchProductsAIAssistantResponse:
    """Orchestrate per-turn dynamic intent classification and tool allow-list routing."""
    with tracer.start_as_current_span("search_products_ai") as span:
        span.set_attribute("app.caller.feature", "copilot_search")
        # --- 1. Input validation ---
        if not query or not query.strip():
            span.set_attribute("app.search.outcome", "empty_query")
            return _refused_search_response()

        # Normalize and bound input before safety check and provider call to prevent
        # long-prefix attacks that push attack markers outside the scanned window.
        query = normalize_text(query, MAX_QUESTION_CHARS)

        # --- 2. Guardrail Check (TF4AIO-26) runs FIRST ---
        if is_attack(query) or contains_pii(query):
            span.set_attribute("app.search.outcome", "blocked")
            return _refused_search_response()

        try:
            # --- 3. Fetch & sanitize multi-turn conversation history ---
            raw_history = session_store.get_history(user_id, session_id) if session_id else []
            sanitized_history = []
            for turn in raw_history[-HISTORY_WINDOW_N:]:
                r = turn.get("role", "user")
                c = turn.get("content", "")
                if is_attack(c) or contains_pii(c):
                    continue  # sanitize history context
                sanitized_history.append({"role": r, "content": c})

            # --- 4. Fast-path chitchat check vs. LLM per-turn intent classification ---
            if _is_fastpath_chitchat(query):
                intent = {
                    "search_type": "chitchat",
                    "confidence_score": 1.0,
                    "response_message": "Xin chào! Tôi có thể giúp gì cho bạn hôm nay?",
                }
            elif _is_review_query(query):
                intent = {
                    "search_type": "reviews",
                    "confidence_score": 1.0,
                    "keywords": "",
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

            # Enforce confidence threshold for unclear fallback
            if confidence_score < INTENT_CONFIDENCE_THRESHOLD and intent_label != IntentLabel.CHITCHAT:
                intent_label = IntentLabel.UNCLEAR
                intent["search_type"] = "unclear"
                intent["clarify_question"] = "Tôi chưa hiểu rõ ý định của bạn. Bạn muốn tìm sản phẩm, xem đánh giá/review hay thêm sản phẩm vào giỏ hàng?"

            parsed_intent_json = json.dumps({k: v for k, v in intent.items() if k != "_metadata"}, ensure_ascii=False)
            span.set_attribute("app.search.search_type", intent.get("search_type", ""))
            span.set_attribute("app.search.intent_label", intent_label.value)
            span.set_attribute("app.search.confidence_score", confidence_score)

            # Audit Logging for AI Mandate #6 compliance
            logger.info(
                "intent_classified",
                extra={
                    "session_id": session_id,
                    "query": query,
                    "search_type": raw_search_type,
                    "intent_label": intent_label.value,
                    "confidence_score": confidence_score,
                    "turn_count": len(sanitized_history) // 2 + 1,
                },
            )

            # Record telemetry metrics
            if record_metrics_fn:
                record_metrics_fn(
                    model_id=assistant.provider.model_id,
                    guardrail_version=assistant.provider.guardrail_version,
                    outcome="success",
                    error_class=None,
                    latency_ms=_lat_ms,
                    input_tokens=_in_tok,
                    output_tokens=_out_tok,
                )

            # --- 5. Routing by IntentLabel with Runtime Allow-List Enforcement ---

            # A. CHITCHAT Intent -> No tools allowed
            if intent_label == IntentLabel.CHITCHAT:
                span.set_attribute("app.search.outcome", "chitchat")
                msg = intent.get("response_message") or "Xin chào! Tôi có thể giúp gì cho bạn hôm nay?"
                if session_id:
                    session_store.append_turn(user_id, session_id, "user", query)
                    session_store.append_turn(user_id, session_id, "assistant", msg)
                return _refused_search_response(
                    parsed_intent=parsed_intent_json,
                    input_tokens=_in_tok,
                    output_tokens=_out_tok,
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
                    trace=demo_pb2.SearchEvidenceTrace(
                        parsed_intent=parsed_intent_json,
                        filter_applied=json.dumps({"clarify_question": clarify_q}, ensure_ascii=False),
                        candidate_count_before=0,
                        candidate_count_after=0,
                        refused=True,
                        input_tokens=_in_tok,
                        output_tokens=_out_tok,
                        estimated_cost_usd=_calculate_search_cost(_in_tok, _out_tok),
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

            # C. PURCHASE (Cart Action) Intent -> Allowed tool: "cart_action"
            if intent_label == IntentLabel.PURCHASE:
                span.set_attribute("app.search.outcome", "cart_action")
                target_kw = intent.get("keywords") or intent.get("category") or query
                target = resolve_referenced_product(sanitized_history, all_products, target_kw, query=query, session_id=session_id)
                try:
                    raw_qty = intent.get("quantity", 1)
                    qty = max(1, min(int(raw_qty), 10))
                except (ValueError, TypeError):
                    qty = 1

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

            # D. REVIEW_QA Intent -> Allowed tools: "get_product_reviews", "bedrock_converse"
            if intent_label == IntentLabel.REVIEW_QA:
                span.set_attribute("app.search.outcome", "reviews_qa")
                target_kw = intent.get("keywords") or ""
                target_product = resolve_referenced_product(sanitized_history, all_products, target_kw, query=query, session_id=session_id)

                if target_product:
                    review_outcome = call_tool(
                        IntentLabel.REVIEW_QA,
                        "bedrock_converse",
                        lambda: assistant.answer(target_product.id, query, session_id),
                    )
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

            # E. PRODUCT_SEARCH Intent -> Allowed tool: "catalog_search"
            valid_ids = {p.id for p in all_products}
            filtered = list(all_products)
            filters_applied = {}

            # Category filter
            category = intent.get("category", "").strip().lower()
            if not category and sanitized_history:
                for turn in reversed(sanitized_history):
                    content = turn.get("content", "").lower()
                    if "kính thiên văn" in content or "telescope" in content:
                        category = "telescopes"
                        break
                    elif "ống nhòm" in content or "binocular" in content:
                        category = "binoculars"
                        break
                    elif "sách" in content or "book" in content or "truyện" in content:
                        category = "books"
                        break

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
                    filtered = [p for p in filtered if any(category in c.lower() for c in p.categories)]

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
            if sort_by == "price_asc" or "rẻ" in query.lower():
                filters_applied["sort_by"] = "price_asc"
                filtered.sort(key=lambda p: (0 if (p.price_usd.units + p.price_usd.nanos / 1e9) > 0 else 1, p.price_usd.units + p.price_usd.nanos / 1e9))
                if sanitized_history and "nhất" in query.lower():
                    filtered = filtered[:1]
            elif sort_by == "price_desc" or "đắt" in query.lower():
                filters_applied["sort_by"] = "price_desc"
                filtered.sort(key=lambda p: (0 if (p.price_usd.units + p.price_usd.nanos / 1e9) > 0 else 1, p.price_usd.units + p.price_usd.nanos / 1e9), reverse=True)
                if sanitized_history and "nhất" in query.lower():
                    filtered = filtered[:1]

            # Compare target filtering
            if intent.get("search_type") == "compare":
                comparison_targets = intent.get("comparison_targets", [])
                filters_applied["comparison_targets"] = comparison_targets
                comparison_matched_products = []
                for target_name in comparison_targets:
                    matched = _fuzzy_match_product_by_name(target_name, all_products)
                    if matched:
                        comparison_matched_products.append(matched[0])

                if not comparison_matched_products:
                    return _refused_search_response(
                        parsed_intent=parsed_intent_json,
                        filter_applied=json.dumps(filters_applied, ensure_ascii=False),
                        before=candidate_count_before,
                        after=0,
                        input_tokens=_in_tok,
                        output_tokens=_out_tok,
                    )

                compare_matched_ids = {p.id for p in comparison_matched_products}
                filtered = [p for p in filtered if p.id in compare_matched_ids]

            # Grounding shield
            filtered = [p for p in filtered if p.id in valid_ids]

            filter_applied_json = json.dumps(filters_applied, ensure_ascii=False)
            candidate_count_after = len(filtered)

            span.set_attribute("app.search.candidate_count_before", candidate_count_before)
            span.set_attribute("app.search.candidate_count_after", candidate_count_after)
            span.set_attribute("app.search.outcome", "success")

            cost = _calculate_search_cost(_in_tok, _out_tok)
            trace_msg = demo_pb2.SearchEvidenceTrace(
                parsed_intent=parsed_intent_json,
                filter_applied=filter_applied_json,
                candidate_count_before=candidate_count_before,
                candidate_count_after=candidate_count_after,
                refused=False,
                input_tokens=_in_tok,
                output_tokens=_out_tok,
                estimated_cost_usd=cost,
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
                summary_text = intent.get("response_message") or f"Found {len(filtered)} products."
                p_names = ", ".join(p.name for p in filtered[:3]) if filtered else ""
                if p_names and p_names.lower() not in summary_text.lower():
                    summary_text += f" (Sản phẩm: {p_names})"
                session_store.append_turn(user_id, session_id, "user", query)
                session_store.append_turn(user_id, session_id, "assistant", summary_text)

            return demo_pb2.SearchProductsAIAssistantResponse(
                results=filtered,
                trace=trace_msg,
            )
        except Exception as exc:
            span.set_attribute("app.search.outcome", "error")
            span.set_attribute("error.class", type(exc).__name__.lower()[:64])
            logger.error("search_products_ai_failed", exc_info=exc)
            return _refused_search_response()
