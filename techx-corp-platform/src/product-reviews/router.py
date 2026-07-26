#!/usr/bin/python

"""Dynamic per-turn intent classification, allow-list enforcement, and routing module."""

from __future__ import annotations

import json
import logging
import os
import re
import time
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
from profile_store import ProfileStore, parse_memory_command
from response_cache import (
    COPILOT_REVIEW_PROMPT_VERSION,
    RESPONSE_SCHEMA_VERSION,
    ResponseCache,
    normalize_exact_request,
    source_fingerprint,
)
from safety import (
    MAX_QUESTION_CHARS,
    contains_pii,
    is_attack,
    normalize_text,
    prepare_context,
)
from session_store import MAX_HISTORY_MESSAGES, session_store

logger = logging.getLogger(__name__)

INTENT_CONFIDENCE_THRESHOLD = float(os.environ.get("INTENT_CONFIDENCE_THRESHOLD", "0.6"))
HISTORY_WINDOW_N = int(os.environ.get("HISTORY_WINDOW_N", str(MAX_HISTORY_MESSAGES)))

copilot_response_cache = ResponseCache(getattr(session_store, "_valkey_client", None))
profile_store = ProfileStore(getattr(session_store, "_valkey_client", None))

_REVIEW_MARKERS = (
    "review",
    "reviews",
    "rating",
    "ratings",
    "feedback",
    "pros and cons",
    "đánh giá",
    "nhận xét",
    "ưu điểm",
    "nhược điểm",
)
_CONTEXT_DEPENDENT_MARKERS = (
    "compare",
    "comparison",
    "cheapest",
    "most expensive",
    "first",
    "second",
    "another product",
    "similar",
    "previous",
    "that one",
    "this one",
    "rẻ nhất",
    "đắt nhất",
    "sản phẩm khác",
    "tương tự",
    "cái trước",
    "cái đó",
    "trong nhóm",
    "trong số",
    "so sánh",
)


def _has_review_marker(query: str) -> bool:
    lowered = normalize_exact_request(query)
    return any(marker in lowered for marker in _REVIEW_MARKERS)


def _strict_explicit_product(query: str, products: list[Any]) -> Any | None:
    """Resolve only a full canonical name or an exact catalog ID; never fuzzy."""
    normalized = normalize_exact_request(query)
    matches: dict[str, Any] = {}
    for product in products:
        product_id = str(getattr(product, "id", "") or "")
        name = normalize_exact_request(getattr(product, "name", ""))
        if product_id and re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(product_id.casefold())}(?![A-Za-z0-9_-])",
            normalized,
        ):
            matches[product_id] = product
        if name and re.search(
            rf"(?<!\w){re.escape(name)}(?!\w)",
            normalized,
        ):
            matches[product_id] = product
    return next(iter(matches.values())) if len(matches) == 1 else None


def _copilot_cache_candidate(
    query: str,
    products: list[Any],
    history: list[dict[str, str]],
) -> tuple[Any | None, str]:
    if not _has_review_marker(query):
        return None, "not_review_qa"
    lowered = normalize_exact_request(query)
    if any(marker in lowered for marker in _CONTEXT_DEPENDENT_MARKERS):
        return None, "context_dependent"
    explicit_target = _strict_explicit_product(query, products)
    if explicit_target is None:
        return None, "no_unique_product"
    empty_target = resolve_referenced_product(
        [],
        products,
        keywords=explicit_target.name,
        query=query,
    )
    current_target = resolve_referenced_product(
        history,
        products,
        keywords=explicit_target.name,
        query=query,
    )
    if (
        empty_target is None
        or current_target is None
        or empty_target.id != current_target.id
    ):
        return None, "no_unique_product"
    return empty_target, "cold"


def _memory_response(
    *,
    response: str,
    outcome: str,
    status: str,
) -> demo_pb2.SearchProductsAIAssistantResponse:
    return demo_pb2.SearchProductsAIAssistantResponse(
        response=response,
        outcome=outcome,
        trace=demo_pb2.SearchEvidenceTrace(
            parsed_intent=json.dumps({"search_type": "memory"}, ensure_ascii=False),
            filter_applied=json.dumps({"profile_fields": sorted(("preferred_category", "max_budget_usd_cents"))}),
            refused=status in {"rejected", "error"},
        ),
        cache_status="miss",
        cache_eligible=False,
        cache_reason="profile_dependent",
        model_calls=0,
        memory_status=status,
    )


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
    return [
        p
        for p in products
        if any(category == c.lower() for c in getattr(p, "categories", []))
    ]


_CATALOG_CATEGORY_TERMS = {
    "telescopes": ("telescope", "telescopes", "kính thiên văn"),
    "accessories": ("accessory", "accessories", "phụ kiện"),
    "binoculars": ("binocular", "binoculars", "ống nhòm"),
    "flashlights": ("flashlight", "flashlights", "đèn pin"),
    "assembly": ("optical tube assembly", "ống quang"),
    "books": ("catalog book", "product book", "sách thiên văn"),
    "travel": ("travel", "travel telescope", "travel scope", "kính du lịch"),
}

_GENERIC_DISCOVERY_KEYWORDS = {
    "advice",
    "beginner",
    "beginners",
    "good",
    "help",
    "new",
    "phù",
    "recommend",
    "recommendation",
    "sao",
    "telescope",
    "telescopes",
    "tư",
    "vấn",
    "xem",
}


def _explicit_catalog_category(query: str) -> str:
    """Return a category only when the current turn names it explicitly."""
    normalized = " ".join(
        "".join(char if char.isalnum() else " " for char in query.lower()).split()
    )
    padded = f" {normalized} "
    for category, terms in _CATALOG_CATEGORY_TERMS.items():
        if any(f" {term} " in padded for term in terms):
            return category
    return ""


def _keywords_are_generic_discovery_terms(keywords: str, category: str) -> bool:
    """Detect model-emitted audience/advisory words that must not filter names."""
    normalized = " ".join(
        "".join(char if char.isalnum() else " " for char in keywords.lower()).split()
    )
    if not normalized:
        return True
    category_terms = {
        token
        for term in _CATALOG_CATEGORY_TERMS.get(category, ())
        for token in term.split()
    }
    return set(normalized.split()).issubset(
        _GENERIC_DISCOVERY_KEYWORDS | category_terms
    )


_PRICE_VALUE_PATTERN = r"\$?\s*(\d+(?:\.\d+)?)"
_EXACT_PRICE_REFERENCE_MARKERS = (
    "cái",
    "món",
    "sản phẩm",
    "item",
    "one",
    "product",
)
_PRODUCT_PURPOSE_MARKERS = (
    "dùng để làm gì",
    "để làm gì",
    "công dụng",
    "chức năng",
    "what is it for",
    "what's it for",
    "what does it do",
    "used for",
)
_RELATIVE_PRICE_MARKERS = (
    "under",
    "below",
    "less than",
    "at most",
    "over",
    "above",
    "more than",
    "at least",
    "between",
    "dưới",
    "trên",
    "từ",
)


def _deterministic_category_price_intent(query: str) -> dict[str, Any] | None:
    """Parse bounded literal category+price filters without an LLM call."""
    category = _explicit_catalog_category(query)
    if not category:
        return None

    normalized = query.lower()
    between = re.search(
        rf"(?:between|từ)\s*{_PRICE_VALUE_PATTERN}\s*"
        rf"(?:and|to|đến|-)\s*{_PRICE_VALUE_PATTERN}",
        normalized,
    )
    if between:
        lower, upper = (float(value) for value in between.groups())
        if lower > upper:
            return None
        return {
            "search_type": "search",
            "confidence_score": 1.0,
            "category": category,
            "price_min": lower,
            "price_max": upper,
        }

    under = re.search(
        rf"(?:under|below|less\s+than|dưới)\s*{_PRICE_VALUE_PATTERN}",
        normalized,
    )
    if under:
        return {
            "search_type": "search",
            "confidence_score": 1.0,
            "category": category,
            "price_max": float(under.group(1)),
        }

    over = re.search(
        rf"(?:over|above|more\s+than|trên)\s*{_PRICE_VALUE_PATTERN}",
        normalized,
    )
    if over:
        return {
            "search_type": "search",
            "confidence_score": 1.0,
            "category": category,
            "price_min": float(over.group(1)),
        }
    return None


def _exact_referenced_price(query: str) -> float | None:
    """Extract a currency-qualified price only from a deictic product reference."""
    normalized = query.lower()
    if any(
        re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", normalized)
        for marker in _RELATIVE_PRICE_MARKERS
    ):
        return None
    if not any(
        re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", normalized)
        for marker in _EXACT_PRICE_REFERENCE_MARKERS
    ):
        return None
    match = re.search(
        r"(?:\$\s*(\d+(?:[.,]\d{1,2})?)"
        r"|(\d+(?:[.,]\d{1,2})?)\s*(?:usd|dollars?|đô(?:\s+la)?))",
        normalized,
    )
    if not match:
        return None
    raw_value = next(value for value in match.groups() if value is not None)
    try:
        return float(raw_value.replace(",", "."))
    except ValueError:
        return None


def _is_product_purpose_query(query: str) -> bool:
    normalized = normalize_exact_request(query)
    return any(marker in normalized for marker in _PRODUCT_PURPOSE_MARKERS)


def _last_search_candidates(products: list[Any], session_id: str, user_id: str) -> list[Any]:
    stored = session_store.get_last_search_products(user_id, session_id) if session_id else []
    stored_ids = {
        row.get("id") if isinstance(row, dict) else getattr(row, "id", None)
        for row in stored
    }
    return [product for product in products if product.id in stored_ids]


def _resolve_exact_price_reference(
    query: str,
    products: list[Any],
    session_id: str,
    user_id: str,
) -> tuple[Any | None, float | None]:
    """Resolve an exact price against the previous result set, never the whole catalog."""
    referenced_price = _exact_referenced_price(query)
    if referenced_price is None or not session_id:
        return None, referenced_price
    matches = [
        product
        for product in _last_search_candidates(products, session_id, user_id)
        if abs(_product_price(product) - referenced_price) < 0.005
    ]
    return (matches[0] if len(matches) == 1 else None), referenced_price


def _resolve_product_purpose_target(
    query: str,
    products: list[Any],
    session_id: str,
    user_id: str,
) -> Any | None:
    explicit = _strict_explicit_product(query, products)
    if explicit is not None:
        return explicit
    remembered = _last_search_candidates(products, session_id, user_id)
    return remembered[0] if len(remembered) == 1 else None


def _explicit_catalog_scope(query: str) -> bool:
    normalized = query.lower()
    return any(marker in normalized for marker in ("toàn bộ catalog", "toàn catalog", "entire catalog", "whole catalog"))


def _references_previous_result_scope(query: str) -> bool:
    normalized = query.lower()
    return any(
        marker in normalized
        for marker in (
            "trong số đó",
            "trong danh sách đó",
            "trong các sản phẩm này",
            "among those",
            "from those",
            "in that list",
        )
    )


def _has_explicit_product_reference(query: str, products: list[Any]) -> bool:
    """Return true only when the current turn itself names a catalog entity."""
    normalized = normalize_text(query, MAX_QUESTION_CHARS).lower()
    normalized_tokens = set(
        token
        for token in "".join(
            char if char.isalnum() else " " for char in normalized
        ).split()
        if len(token) >= 5
    )
    generic_tokens = {
        "product",
        "products",
        "sản phẩm",
        "telescope",
        "telescopes",
        "refractor",
        "binoculars",
    }
    for product in products:
        name = str(getattr(product, "name", "") or "").lower()
        if name and name in normalized:
            return True
        name_tokens = {
            token
            for token in "".join(
                char if char.isalnum() else " " for char in name
            ).split()
            if len(token) >= 5 and token not in generic_tokens
        }
        if normalized_tokens & name_tokens:
            return True
    return False


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
    audit_callback: Callable[..., None] | None = None,
) -> demo_pb2.SearchProductsAIAssistantResponse:
    """Orchestrate per-turn dynamic intent classification and tool allow-list routing."""
    request_started = time.monotonic()
    model_calls = 0
    default_cache_reason = "not_review_qa"
    request_memory_status = "not_applicable"

    def finalize(
        response: demo_pb2.SearchProductsAIAssistantResponse,
        *,
        persist_history: bool = True,
    ) -> demo_pb2.SearchProductsAIAssistantResponse:
        if not response.cache_status:
            response.cache_status = "miss"
        if not response.cache_reason:
            response.cache_reason = default_cache_reason
        if not response.memory_status:
            response.memory_status = request_memory_status
        if response.model_calls == 0:
            response.model_calls = model_calls
        if response.HasField("trace"):
            if response.input_tokens == 0:
                response.input_tokens = response.trace.input_tokens
            if response.output_tokens == 0:
                response.output_tokens = response.trace.output_tokens
            if response.estimated_cost_usd == 0:
                response.estimated_cost_usd = response.trace.estimated_cost_usd
        response.latency_ms = (time.monotonic() - request_started) * 1_000
        if (
            persist_history
            and session_id
            and query
            and response.response
            and not is_attack(query)
            and not contains_pii(query)
        ):
            try:
                session_store.append_exchange(
                    user_id,
                    session_id,
                    query,
                    response.response,
                )
            except Exception as exc:
                logger.warning(
                    "copilot_history_append_failed",
                    extra={"error_class": type(exc).__name__.lower()[:64]},
                )
        return response

    with tracer.start_as_current_span("search_products_ai") as span:
        span.set_attribute("app.caller.feature", "copilot_search")
        # --- 1. Input validation ---
        if not query or not query.strip():
            span.set_attribute("app.search.outcome", "empty_query")
            return finalize(_refused_search_response(
                refusal_reason="guardrail_blocked",
                response="Vui lòng nhập câu hỏi hoặc yêu cầu tìm kiếm.",
                outcome="blocked",
            ), persist_history=False)

        query = normalize_text(query, MAX_QUESTION_CHARS)

        # --- 2. Guardrail Check (TF4AIO-26) runs FIRST ---
        if is_attack(query) or contains_pii(query):
            span.set_attribute("app.search.outcome", "blocked")
            return finalize(_refused_search_response(
                refusal_reason="guardrail_blocked",
                response=_message(
                    query,
                    "Tôi không thể xử lý yêu cầu này. Bạn có thể hỏi về sản phẩm trong danh mục.",
                    "I cannot process that request. You can ask about products in the catalog.",
                ),
                outcome="blocked",
            ), persist_history=False)

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

            prefetched_catalog = None
            applied_profile: dict[str, Any] | None = None
            memory_command = parse_memory_command(query)
            if memory_command is not None:
                default_cache_reason = "profile_dependent"
                if not user_id or user_id == "guest":
                    return finalize(
                        _memory_response(
                            response=_message(
                                query,
                                "Bạn cần đăng nhập để lưu hoặc đọc sở thích xuyên phiên.",
                                "You must sign in to store or read cross-session preferences.",
                            ),
                            outcome="memory_rejected",
                            status="rejected",
                        )
                    )
                if memory_command.action == "reject":
                    return finalize(
                        _memory_response(
                            response=_message(
                                query,
                                "Tôi chỉ có thể lưu danh mục yêu thích hoặc ngân sách tối đa khi bạn yêu cầu rõ ràng; dữ liệu PII và trường tùy ý sẽ không được lưu.",
                                "I can only store an explicitly requested preferred category or maximum budget; PII and arbitrary fields are not stored.",
                            ),
                            outcome="memory_rejected",
                            status="rejected",
                        )
                    )
                if memory_command.action == "forget":
                    forgotten = profile_store.forget(user_id)
                    message = (
                        _message(
                            query,
                            "Tôi đã xóa các sở thích đã lưu của bạn.",
                            "I deleted your stored preferences.",
                        )
                        if forgotten.status == "forgotten"
                        else _message(
                            query,
                            "Tôi chưa thể xóa sở thích lúc này. Vui lòng thử lại.",
                            "I could not delete your preferences. Please try again.",
                        )
                    )
                    return finalize(
                        _memory_response(
                            response=message,
                            outcome=(
                                "memory_forgotten"
                                if forgotten.status == "forgotten"
                                else "memory_error"
                            ),
                            status=forgotten.status,
                        )
                    )
                if memory_command.action == "show":
                    recalled = profile_store.read(user_id)
                    if recalled.status == "recalled" and recalled.profile:
                        pieces = []
                        if recalled.profile.get("preferred_category"):
                            pieces.append(
                                f"preferred_category={recalled.profile['preferred_category']}"
                            )
                        if recalled.profile.get("max_budget_usd_cents"):
                            pieces.append(
                                "max_budget_usd="
                                f"{recalled.profile['max_budget_usd_cents'] / 100:.2f}"
                            )
                        message = _message(
                            query,
                            f"Sở thích đã lưu: {', '.join(pieces)}.",
                            f"Stored preferences: {', '.join(pieces)}.",
                        )
                    elif recalled.status == "not_found":
                        message = _message(
                            query,
                            "Tôi chưa lưu sở thích nào cho bạn.",
                            "I do not have any stored preferences for you.",
                        )
                    else:
                        message = _message(
                            query,
                            "Tôi chưa thể đọc sở thích lúc này; yêu cầu sẽ tiếp tục mà không cá nhân hóa.",
                            "I could not read preferences; the request will continue without personalization.",
                        )
                    return finalize(
                        _memory_response(
                            response=message,
                            outcome=(
                                "memory_recalled"
                                if recalled.status == "recalled"
                                else "memory_not_found"
                                if recalled.status == "not_found"
                                else "memory_error"
                            ),
                            status=recalled.status,
                        )
                    )
                if memory_command.action == "remember":
                    values = dict(memory_command.values)
                    category = values.get("preferred_category")
                    if category:
                        prefetched_catalog = product_catalog_stub.ListProducts(
                            demo_pb2.Empty(), timeout=2.0
                        )
                        categories = {
                            str(value).casefold()
                            for product in prefetched_catalog.products
                            for value in product.categories
                        }
                        if category not in categories:
                            return finalize(
                                _memory_response(
                                    response=_message(
                                        query,
                                        "Danh mục đó không có trong catalog nên tôi chưa lưu.",
                                        "That category is not in the catalog, so I did not store it.",
                                    ),
                                    outcome="memory_rejected",
                                    status="rejected",
                                )
                            )
                    stored = profile_store.write(user_id, values)
                    message = (
                        _message(
                            query,
                            "Tôi đã lưu sở thích bạn vừa yêu cầu.",
                            "I stored the preference you explicitly requested.",
                        )
                        if stored.status == "stored"
                        else _message(
                            query,
                            "Tôi chưa thể lưu sở thích lúc này. Vui lòng thử lại.",
                            "I could not store that preference. Please try again.",
                        )
                    )
                    return finalize(
                        _memory_response(
                            response=message,
                            outcome=(
                                "memory_stored"
                                if stored.status == "stored"
                                else "memory_error"
                            ),
                            status=stored.status,
                        )
                    )
                if memory_command.action == "apply":
                    recalled = profile_store.read(user_id)
                    if recalled.status == "recalled" and recalled.profile:
                        applied_profile = recalled.profile
                        request_memory_status = "applied"
                    else:
                        return finalize(
                            _memory_response(
                                response=_message(
                                    query,
                                    "Tôi chưa có sở thích đã lưu để áp dụng.",
                                    "I do not have stored preferences to apply.",
                                ),
                                outcome=(
                                    "memory_not_found"
                                    if recalled.status == "not_found"
                                    else "memory_error"
                                ),
                                status=recalled.status,
                            )
                        )

            # Session-relative price references and product-purpose questions are
            # grounded by the catalog and do not need probabilistic classification.
            referenced_price = _exact_referenced_price(query)
            purpose_query = _is_product_purpose_query(query)
            if referenced_price is not None or purpose_query:
                if prefetched_catalog is None:
                    prefetched_catalog = product_catalog_stub.ListProducts(
                        demo_pb2.Empty(), timeout=2.0
                    )
                contextual_products = list(prefetched_catalog.products)
                default_cache_reason = "context_dependent"

                if referenced_price is not None:
                    target_product, _ = _resolve_exact_price_reference(
                        query,
                        contextual_products,
                        session_id,
                        user_id,
                    )
                    if target_product is not None:
                        if session_id:
                            session_store.set_last_search_products(
                                user_id,
                                session_id,
                                [
                                    {
                                        "id": target_product.id,
                                        "name": target_product.name,
                                        "description": getattr(
                                            target_product, "description", ""
                                        ),
                                        "categories": list(
                                            getattr(target_product, "categories", [])
                                        ),
                                    }
                                ],
                            )
                        span.set_attribute(
                            "app.search.outcome", "session_price_reference"
                        )
                        return finalize(
                            demo_pb2.SearchProductsAIAssistantResponse(
                                results=[target_product],
                                response=_message(
                                    query,
                                    f"Sản phẩm có giá ${_product_price(target_product):.2f} là {target_product.name}.",
                                    f"The ${_product_price(target_product):.2f} product is {target_product.name}.",
                                ),
                                outcome="success",
                                trace=demo_pb2.SearchEvidenceTrace(
                                    parsed_intent=json.dumps(
                                        {
                                            "search_type": "search",
                                            "resolution": "session_exact_price",
                                        }
                                    ),
                                    filter_applied=json.dumps(
                                        {
                                            "scope": "last_search",
                                            "price_usd": referenced_price,
                                        }
                                    ),
                                    candidate_count_before=len(
                                        contextual_products
                                    ),
                                    candidate_count_after=1,
                                ),
                                cache_eligible=False,
                                model_calls=0,
                            )
                        )

                if purpose_query:
                    target_product = _resolve_product_purpose_target(
                        query,
                        contextual_products,
                        session_id,
                        user_id,
                    )
                    if target_product is not None:
                        description = str(
                            getattr(target_product, "description", "") or ""
                        ).strip()
                        answer = _message(
                            query,
                            f"Công dụng của {target_product.name}: {description}",
                            f"Purpose of {target_product.name}: {description}",
                        )
                        if session_id:
                            session_store.set_last_search_products(
                                user_id,
                                session_id,
                                [
                                    {
                                        "id": target_product.id,
                                        "name": target_product.name,
                                        "description": description,
                                        "categories": list(
                                            getattr(target_product, "categories", [])
                                        ),
                                    }
                                ],
                            )
                        span.set_attribute(
                            "app.search.outcome", "catalog_product_purpose"
                        )
                        return finalize(
                            demo_pb2.SearchProductsAIAssistantResponse(
                                results=[target_product],
                                response=answer,
                                outcome="answered",
                                trace=demo_pb2.SearchEvidenceTrace(
                                    parsed_intent=json.dumps(
                                        {
                                            "search_type": "product_info",
                                            "resolution": "catalog_description",
                                        }
                                    ),
                                    filter_applied=json.dumps(
                                        {
                                            "product_id": target_product.id,
                                            "scope": "last_search_or_explicit",
                                        }
                                    ),
                                    candidate_count_before=len(
                                        contextual_products
                                    ),
                                    candidate_count_after=1,
                                ),
                                cache_eligible=False,
                                model_calls=0,
                            )
                        )
                    clarify_q = _message(
                        query,
                        "Bạn muốn hỏi công dụng của sản phẩm nào? Vui lòng chọn hoặc nêu tên một sản phẩm.",
                        "Which product's purpose would you like to know? Please select or name one product.",
                    )
                    return finalize(
                        _refused_search_response(
                            parsed_intent=json.dumps(
                                {
                                    "search_type": "unclear",
                                    "resolution": "catalog_description",
                                }
                            ),
                            filter_applied=json.dumps(
                                {"scope": "last_search_or_explicit"}
                            ),
                            before=len(contextual_products),
                            after=0,
                            refusal_reason="no_unique_product",
                            response=clarify_q,
                            outcome="clarification_required",
                        )
                    )

            if (
                applied_profile is None
                and _has_review_marker(query)
                and user_id
                and user_id != "guest"
            ):
                if prefetched_catalog is None:
                    prefetched_catalog = product_catalog_stub.ListProducts(
                        demo_pb2.Empty(), timeout=2.0
                    )
                early_product, default_cache_reason = _copilot_cache_candidate(
                    query,
                    list(prefetched_catalog.products),
                    sanitized_history,
                )
                if early_product is not None:
                    review_rows = fetch_reviews(early_product.id) if fetch_reviews else []
                    prepared = prepare_context(
                        query,
                        {
                            "id": early_product.id,
                            "name": early_product.name,
                            "description": early_product.description,
                            "categories": list(early_product.categories),
                        },
                        review_rows,
                    )
                    fingerprint = source_fingerprint(
                        prepared.product,
                        prepared.reviews,
                    )
                    identity = copilot_response_cache.identity(
                        surface="copilot_review",
                        user_id=user_id,
                        product_id=early_product.id,
                        request=prepared.question,
                        dependency_class="explicit_product_review_v1",
                        model_id="deterministic",
                        prompt_version=COPILOT_REVIEW_PROMPT_VERSION,
                        guardrail_version="application-safety-v1",
                        response_schema_version=RESPONSE_SCHEMA_VERSION,
                        fingerprint=fingerprint,
                    )
                    lookup = copilot_response_cache.lookup(identity)
                    if lookup.status == "hit" and lookup.value:
                        cached = lookup.value
                        return finalize(
                            demo_pb2.SearchProductsAIAssistantResponse(
                                results=[early_product],
                                response=str(cached["response"]),
                                outcome=str(cached["outcome"]),
                                trace=demo_pb2.SearchEvidenceTrace(
                                    parsed_intent=json.dumps(
                                        {
                                            "search_type": "reviews",
                                            "dependency_class": "explicit_product_review_v1",
                                        }
                                    ),
                                    filter_applied=json.dumps(
                                        {"review_qa_product_id": early_product.id}
                                    ),
                                    candidate_count_before=len(
                                        prefetched_catalog.products
                                    ),
                                    candidate_count_after=1,
                                ),
                                cache_status="hit",
                                cache_eligible=True,
                                cache_reason="hit",
                                model_calls=0,
                                memory_status="not_applicable",
                            )
                        )

                    cache_lock = copilot_response_cache.acquire_lock(identity)
                    try:
                        if cache_lock is None and lookup.reason != "cache_error":
                            waited = copilot_response_cache.wait_for_fill(identity)
                            if waited.status == "hit" and waited.value:
                                return finalize(
                                    demo_pb2.SearchProductsAIAssistantResponse(
                                        results=[early_product],
                                        response=str(waited.value["response"]),
                                        outcome=str(waited.value["outcome"]),
                                        trace=demo_pb2.SearchEvidenceTrace(
                                            parsed_intent=json.dumps(
                                                {
                                                    "search_type": "reviews",
                                                    "dependency_class": "explicit_product_review_v1",
                                                }
                                            ),
                                            filter_applied=json.dumps(
                                                {
                                                    "review_qa_product_id": early_product.id
                                                }
                                            ),
                                            candidate_count_before=len(
                                                prefetched_catalog.products
                                            ),
                                            candidate_count_after=1,
                                        ),
                                        cache_status="hit",
                                        cache_eligible=True,
                                        cache_reason="hit_after_wait",
                                        model_calls=0,
                                    )
                                )
                            if waited.reason == "cache_error":
                                default_cache_reason = "cache_error"
                            else:
                                default_cache_reason = "lock_timeout"
                        else:
                            default_cache_reason = lookup.reason

                        answer_text, review_outcome, _ = summarize_copilot_reviews(
                            query,
                            early_product,
                            review_rows,
                        )
                        if review_outcome == "answered":
                            if not copilot_response_cache.write(
                                identity,
                                {
                                    "response": answer_text,
                                    "outcome": review_outcome,
                                },
                            ):
                                default_cache_reason = "cache_error"
                        if session_id:
                            session_store.set_last_search_products(
                                user_id,
                                session_id,
                                [
                                    {
                                        "id": early_product.id,
                                        "name": early_product.name,
                                        "description": early_product.description,
                                        "categories": list(early_product.categories),
                                    }
                                ],
                            )
                        return finalize(
                            demo_pb2.SearchProductsAIAssistantResponse(
                                results=[early_product],
                                response=answer_text,
                                outcome=review_outcome,
                                trace=demo_pb2.SearchEvidenceTrace(
                                    parsed_intent=json.dumps(
                                        {
                                            "search_type": "reviews",
                                            "dependency_class": "explicit_product_review_v1",
                                        }
                                    ),
                                    filter_applied=json.dumps(
                                        {"review_qa_product_id": early_product.id}
                                    ),
                                    candidate_count_before=len(
                                        prefetched_catalog.products
                                    ),
                                    candidate_count_after=1,
                                ),
                                cache_status="miss",
                                cache_eligible=True,
                                cache_reason=default_cache_reason,
                                model_calls=0,
                            )
                        )
                    finally:
                        copilot_response_cache.release_lock(identity, cache_lock)
            elif _has_review_marker(query) and (not user_id or user_id == "guest"):
                default_cache_reason = "missing_user_identity"

            # --- 4. Fast-path chitchat check vs. LLM per-turn intent classification ---
            provider_attempted = False
            if applied_profile is not None:
                intent = {
                    "search_type": "search",
                    "confidence_score": 1.0,
                }
                if applied_profile.get("preferred_category"):
                    intent["category"] = applied_profile["preferred_category"]
                if applied_profile.get("max_budget_usd_cents"):
                    intent["price_max"] = (
                        int(applied_profile["max_budget_usd_cents"]) / 100
                    )
            elif _is_fastpath_chitchat(query):
                intent = {
                    "search_type": "chitchat",
                    "confidence_score": 1.0,
                }
            elif deterministic_intent := _deterministic_category_price_intent(query):
                intent = deterministic_intent
            else:
                provider_attempted = True
                model_calls += 1
                intent = assistant.provider.parse_search_intent(query, history=sanitized_history)

            _metadata = intent.get("_metadata") or {}
            _in_tok = _metadata.get("input_tokens", 0)
            _out_tok = _metadata.get("output_tokens", 0)
            _lat_ms = _metadata.get("latency_ms", 0.0)

            confidence_score = float(intent.get("confidence_score", 0.95))
            raw_search_type = intent.get("search_type", "")
            intent_label = _map_search_type_to_intent(raw_search_type)
            explicit_category = _explicit_catalog_category(query)

            if (
                raw_search_type == "search"
                and explicit_category
                and _keywords_are_generic_discovery_terms(
                    str(intent.get("keywords") or ""), explicit_category
                )
            ):
                intent["category"] = explicit_category
                intent.pop("keywords", None)

            # Rescue queries containing specific catalog product names (e.g. "Comet Book") from being wrongly refused as OUT_OF_SCOPE/UNCLEAR
            if raw_search_type == "out_of_scope" or intent_label == IntentLabel.UNCLEAR:
                matched_product = None
                try:
                    catalog_resp = product_catalog_stub.ListProducts(demo_pb2.Empty(), timeout=2.0)
                    matched_product = resolve_referenced_product(
                        [],
                        list(catalog_resp.products),
                        keywords=query,
                    )
                except Exception as e:
                    logger.warning(f"Failed to check catalog for out_of_scope rescue: {e}")
                if matched_product:
                    raw_search_type = "search"
                    intent["search_type"] = "search"
                    intent["keywords"] = matched_product.name
                    intent_label = IntentLabel.PRODUCT_SEARCH
                elif explicit_category:
                    # Safety/PII checks already ran. A literal catalog category
                    # is sufficient evidence that this is product discovery,
                    # even when the model false-blocks advisory phrasing.
                    raw_search_type = "search"
                    intent["search_type"] = "search"
                    intent["category"] = explicit_category
                    intent.pop("keywords", None)
                    intent.pop("clarify_question", None)
                    confidence_score = max(confidence_score, 0.9)
                    intent["confidence_score"] = confidence_score
                    intent_label = IntentLabel.PRODUCT_SEARCH

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
            if record_metrics_fn and provider_attempted:
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
            if provider_attempted and audit_callback:
                audit_callback(
                    surface="copilot_search",
                    model_id=assistant.provider.model_id,
                    tool_name="bedrock.converse",
                    safety_decision=(
                        "refuse" if raw_search_type in {"out_of_scope", "unclear"} else "allow"
                    ),
                    confirmation_status="not_required",
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
                return finalize(_refused_search_response(
                    parsed_intent=parsed_intent_json,
                    input_tokens=_in_tok,
                    output_tokens=_out_tok,
                    refusal_reason="llm_classified_out_of_scope",
                    response=msg,
                    outcome=outcome,
                ))

            # B. UNCLEAR Intent -> No tools allowed, ask for clarification
            if intent_label == IntentLabel.UNCLEAR:
                span.set_attribute("app.search.outcome", "unclear")
                clarify_q = intent.get("clarify_question") or "Tôi chưa hiểu rõ ý định của bạn. Bạn muốn tìm kiếm sản phẩm hay xem đánh giá/review?"
                return finalize(demo_pb2.SearchProductsAIAssistantResponse(
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
                ))

            # Fetch catalog products (via catalog_search tool)
            catalog_response = prefetched_catalog or call_tool(
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
                    return finalize(_refused_search_response(
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
                    ))

                comparison_outcome = call_tool(
                    IntentLabel.COMPARE,
                    "bedrock_compare",
                    lambda: assistant.compare_products(compared, query, session_id, user_id),
                )
                model_calls += comparison_outcome.model_calls
                if comparison_outcome.provider_attempted and audit_callback:
                    audit_callback(
                        surface="copilot_search",
                        model_id=assistant.provider.model_id,
                        tool_name="bedrock.converse",
                        safety_decision=(
                            "provider_unavailable"
                            if comparison_outcome.outcome == "unavailable"
                            or comparison_outcome.error_class
                            else "allow"
                        ),
                        confirmation_status="not_required",
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
                return finalize(demo_pb2.SearchProductsAIAssistantResponse(
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
                ))

            # D. PURCHASE (Cart Action) Intent -> Allowed tool: "cart_action"
            if intent_label == IntentLabel.PURCHASE:
                span.set_attribute("app.search.outcome", "cart_action")
                target_kw = (
                    intent.get("keywords") or ""
                    if _has_explicit_product_reference(query, all_products)
                    else ""
                )
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
                    return finalize(_refused_search_response(
                        parsed_intent=json.dumps(intent, ensure_ascii=False),
                        filter_applied=json.dumps({"quantity": qty, "maximum_quantity": 10}, ensure_ascii=False),
                        before=candidate_count_before,
                        after=0,
                        input_tokens=_in_tok,
                        output_tokens=_out_tok,
                        refusal_reason="quantity_limit_exceeded",
                        response=limit_msg,
                        outcome="quantity_limit_exceeded",
                    ))
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
                    return finalize(demo_pb2.SearchProductsAIAssistantResponse(
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
                    ))
                else:
                    # Bug #20 fix: Include clarify_question for PURCHASE miss
                    clarify_q = "Tôi chưa tìm thấy sản phẩm bạn muốn thêm vào giỏ hàng. Bạn có thể cho biết tên sản phẩm cụ thể không?"
                    intent["search_type"] = "unclear"
                    intent["clarify_question"] = clarify_q
                    intent["response_message"] = clarify_q
                    parsed_intent_json = json.dumps(intent, ensure_ascii=False)
                    return finalize(demo_pb2.SearchProductsAIAssistantResponse(
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
                    ))

            # E. REVIEW_QA Intent -> Allowed tool: "get_product_reviews".
            # Copilot deliberately does not invoke the model-backed review Q&A.
            if intent_label == IntentLabel.REVIEW_QA:
                span.set_attribute("app.search.outcome", "reviews_qa")
                remembered_products = (
                    session_store.get_last_search_products(user_id, session_id)
                    if session_id
                    else []
                )
                target_kw = intent.get("keywords") or ""
                if (
                    len(remembered_products) == 1
                    and not _has_explicit_product_reference(query, all_products)
                ):
                    target_kw = ""
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
                        session_store.set_last_search_products(
                            user_id,
                            session_id,
                            [
                                {
                                    "id": target_product.id,
                                    "name": target_product.name,
                                    "description": getattr(target_product, "description", ""),
                                    "categories": list(getattr(target_product, "categories", [])),
                                }
                            ],
                        )
                    return finalize(demo_pb2.SearchProductsAIAssistantResponse(
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
                    ))
                else:
                    clarify_q = "Bạn muốn xem đánh giá của sản phẩm nào? Bạn có thể cho biết tên sản phẩm cụ thể không?"
                    intent["search_type"] = "unclear"
                    intent["clarify_question"] = clarify_q
                    intent["response_message"] = clarify_q
                    parsed_intent_json = json.dumps(intent, ensure_ascii=False)
                    return finalize(demo_pb2.SearchProductsAIAssistantResponse(
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
                    ))

            # F. PRODUCT_SEARCH Intent -> Allowed tool: "catalog_search"
            valid_ids = {p.id for p in all_products}
            filtered = list(all_products)
            filters_applied = {}
            if session_id and _references_previous_result_scope(query):
                scoped_products = _last_search_candidates(all_products, session_id, user_id)
                if scoped_products:
                    filtered = scoped_products
                    filters_applied["scope"] = "last_search"

            # Category filter
            category = intent.get("category", "").strip().lower()
            category_aliases = {"flashlight": "flashlights", "telescope": "telescopes", "binocular": "binoculars", "book": "books", "accessory": "accessories"}
            category = category_aliases.get(category, category)
            if category:
                filters_applied["category"] = category
                filtered = [
                    p
                    for p in filtered
                    if any(category == c.lower() for c in p.categories)
                ]

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

            route_outcome = "success" if candidate_count_after > 0 else "no_match"
            span.set_attribute("app.search.candidate_count_before", candidate_count_before)
            span.set_attribute("app.search.candidate_count_after", candidate_count_after)
            span.set_attribute("app.search.outcome", route_outcome)

            trace_msg = demo_pb2.SearchEvidenceTrace(
                parsed_intent=parsed_intent_json,
                filter_applied=filter_applied_json,
                candidate_count_before=candidate_count_before,
                candidate_count_after=candidate_count_after,
                refused=False,
                input_tokens=_in_tok,
                output_tokens=_out_tok,
                estimated_cost_usd=_calculate_search_cost(_in_tok, _out_tok),
            )

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
            return finalize(demo_pb2.SearchProductsAIAssistantResponse(
                results=filtered,
                response=summary_text,
                outcome="success" if filtered else "no_match",
                trace=trace_msg,
            ))
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
            if audit_callback:
                audit_callback(
                    surface="copilot_search",
                    model_id=getattr(assistant.provider, "model_id", "unknown"),
                    tool_name="bedrock.converse",
                    safety_decision=(
                        "block"
                        if exc.error_class == "guardrail_intervened"
                        else "provider_unavailable"
                    ),
                    confirmation_status="not_required",
                )
            ref_reason = "schema_validation_failed" if exc.error_class == "invalid_response" else (
                "guardrail_blocked" if exc.error_class == "guardrail_intervened" else "provider_failure"
            )
            invalid_response = exc.error_class == "invalid_response"
            return finalize(_refused_search_response(
                input_tokens=getattr(exc, "input_tokens", 0),
                output_tokens=getattr(exc, "output_tokens", 0),
                refusal_reason=ref_reason,
                response=_message(
                    query,
                    (
                        "Tôi chưa xử lý được cách diễn đạt này. Bạn có thể nói rõ tên sản phẩm hoặc yêu cầu không?"
                        if invalid_response
                        else "Copilot hiện tạm thời không khả dụng. Vui lòng thử lại sau."
                    ),
                    (
                        "I could not process that wording. Could you name the product or clarify the request?"
                        if invalid_response
                        else "Copilot is temporarily unavailable. Please try again later."
                    ),
                ),
                outcome=(
                    "clarification_required"
                    if invalid_response
                    else "provider_unavailable"
                ),
            ))
        except Exception as exc:
            span.set_attribute("app.search.outcome", "error")
            span.set_attribute("error.class", type(exc).__name__.lower()[:64])
            logger.error("search_products_ai_failed", exc_info=exc)
            return finalize(_refused_search_response(
                refusal_reason="provider_failure",
                response=_message(
                    query,
                    "Copilot hiện tạm thời không khả dụng. Vui lòng thử lại sau.",
                    "Copilot is temporarily unavailable. Please try again later.",
                ),
                outcome="provider_unavailable",
            ))
