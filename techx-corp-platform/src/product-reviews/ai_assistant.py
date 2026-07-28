#!/usr/bin/python

"""Application-owned orchestration for grounded product Q&A."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import re
from bedrock_adapter import BedrockAdapter, ProviderFailure
import demo_pb2
from response_cache import (
    PRODUCT_QA_PROMPT_VERSION,
    RESPONSE_SCHEMA_VERSION,
    ResponseCache,
    source_fingerprint,
)
from safety import (
    BLOCKED_RESPONSE,
    INSUFFICIENT_RESPONSE,
    UNAVAILABLE_RESPONSE,
    UnsafeModelOutput,
    is_attack,
    is_action_intent,
    is_attack_or_action,
    prepare_context,
    validate_grounded_comparison,
    validate_grounded_output,
    contains_pii,
)
from session_store import session_store


@dataclass(frozen=True)
class AssistantOutcome:
    response: str
    outcome: str
    latency_ms: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error_class: str = ""
    quarantined_reviews: int = 0
    provider_stop_reason: str = "not_applicable"
    response_contract_stage: str = "not_applicable"
    action_proposal: Any = None
    provider_attempted: bool = False
    citations: tuple[dict[str, Any], ...] = ()
    cache_status: str = "miss"
    cache_eligible: bool = False
    cache_reason: str = "not_eligible"
    model_calls: int = 0
    memory_status: str = "not_applicable"
    cache_lookup_latency_ms: float = 0
    saved_model_calls: int = 0
    saved_input_tokens: int = 0
    saved_output_tokens: int = 0


class GroundedAssistant:
    def __init__(
        self,
        provider: BedrockAdapter,
        fetch_product: Callable[[str], dict[str, Any]],
        fetch_reviews: Callable[[str], list[tuple[Any, ...]]],
        system_canary: str = "",
        response_cache: ResponseCache | None = None,
    ):
        self.provider = provider
        self.fetch_product = fetch_product
        self.fetch_reviews = fetch_reviews
        self.system_canary = system_canary
        self.response_cache = response_cache or ResponseCache(
            getattr(session_store, "_valkey_client", None)
        )

    @staticmethod
    def _product_dict(product: Any) -> dict[str, Any]:
        if isinstance(product, dict):
            return dict(product)
        price = getattr(product, "price_usd", None)
        price_value = 0.0
        if price is not None:
            price_value = float(getattr(price, "units", 0) or 0) + float(getattr(price, "nanos", 0) or 0) / 1e9
        return {
            "id": str(getattr(product, "id", "")),
            "name": str(getattr(product, "name", "")),
            "description": str(getattr(product, "description", "")),
            "categories": list(getattr(product, "categories", [])),
            "price_usd": price_value,
        }

    @staticmethod
    def _comparison_fallback(products: list[dict[str, Any]], question: str) -> str:
        first, second = products[:2]
        first_price = float(first.get("price_usd", 0) or 0)
        second_price = float(second.get("price_usd", 0) or 0)
        difference = abs(first_price - second_price)
        vi = bool(re.search(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", question.lower()))
        if vi:
            return (
                f"**{first['name']}** có giá ${first_price:.2f}, còn **{second['name']}** có giá "
                f"${second_price:.2f}; chênh lệch ${difference:.2f}. Hiện phần tổng hợp đánh giá chuyên sâu "
                "đang tạm thời không khả dụng, vì vậy tôi chưa thể đưa ra khuyến nghị có căn cứ."
            )
        return (
            f"**{first['name']}** costs ${first_price:.2f}, while **{second['name']}** costs "
            f"${second_price:.2f}, a difference of ${difference:.2f}. The grounded review synthesis "
            "is temporarily unavailable, so I cannot provide an evidence-based recommendation yet."
        )

    def compare_products(
        self,
        products: list[Any],
        question: str,
        session_id: str = "",
        user_id: str = "guest",
    ) -> AssistantOutcome:
        """Compare resolved catalog products using bounded, citation-checked evidence."""
        if len(products) != 2:
            return AssistantOutcome(response=INSUFFICIENT_RESPONSE, outcome="insufficient")

        sources: dict[str, str] = {}
        evidence_products: list[dict[str, Any]] = []
        quarantined_reviews = 0
        for raw_product in products:
            product = self._product_dict(raw_product)
            prepared = prepare_context(question, product, self.fetch_reviews(product["id"]))
            quarantined_reviews += prepared.quarantined_review_count
            price_text = f"${float(product.get('price_usd', 0) or 0):.2f}"
            source_rows = [
                (f"product:{product['id']}:name", prepared.product.get("name", "")),
                (f"product:{product['id']}:description", prepared.product.get("description", "")),
                (f"product:{product['id']}:categories", ", ".join(prepared.product.get("categories", []))),
                (f"product:{product['id']}:price", price_text),
            ]
            for source_id, text in source_rows:
                if text:
                    sources[source_id] = str(text)
            reviews = []
            for review in prepared.reviews:
                source_id = f"review:{product['id']}:{review['review_id']}"
                sources[source_id] = review["description"]
                reviews.append({
                    "source_id": source_id,
                    "score": review["score"],
                    "text": review["description"],
                })
            evidence_products.append({
                "id": product["id"],
                "name": prepared.product.get("name", ""),
                "description": prepared.product.get("description", ""),
                "categories": prepared.product.get("categories", []),
                "price": price_text,
                "reviews": reviews,
            })

        try:
            result = self.provider.compare_products(
                question,
                {"products": evidence_products, "sources": sources},
            )
            validated = validate_grounded_comparison(result.payload, sources, self.system_canary)
            return AssistantOutcome(
                response=validated["answer"],
                outcome=validated["decision"],
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                quarantined_reviews=quarantined_reviews,
                provider_stop_reason=result.stop_reason,
                response_contract_stage=result.contract_stage,
                provider_attempted=True,
                model_calls=1,
                citations=tuple(validated["citations"]),
            )
        except ProviderFailure as exc:
            fallback = self._comparison_fallback(
                [self._product_dict(product) for product in products],
                question,
            )
            return AssistantOutcome(
                response=fallback,
                outcome="degraded",
                error_class=getattr(exc, "error_class", type(exc).__name__.lower())[:64],
                quarantined_reviews=quarantined_reviews,
                latency_ms=exc.latency_ms,
                input_tokens=exc.input_tokens,
                output_tokens=exc.output_tokens,
                provider_stop_reason=exc.stop_reason,
                response_contract_stage=exc.contract_stage,
                provider_attempted=True,
            )
        except UnsafeModelOutput as exc:
            # The provider call succeeded before grounding validation rejected
            # its payload. Retain the billable usage from that successful call.
            fallback = self._comparison_fallback(
                [self._product_dict(product) for product in products],
                question,
            )
            if session_id:
                session_store.append_turn(user_id, session_id, "user", question)
                session_store.append_turn(user_id, session_id, "assistant", fallback)
            return AssistantOutcome(
                response=fallback,
                outcome="degraded",
                error_class=type(exc).__name__.lower()[:64],
                quarantined_reviews=quarantined_reviews,
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                provider_stop_reason=result.stop_reason,
                response_contract_stage=result.contract_stage,
                provider_attempted=True,
                model_calls=1,
            )

    def answer(self, product_id: str, question: str, session_id: str = "", user_id: str = "guest") -> AssistantOutcome:
        quarantined_reviews = 0
        provider_attempted = False
        if not question or is_attack(question) or contains_pii(question):
            return AssistantOutcome(
                response=BLOCKED_RESPONSE,
                outcome="blocked",
                cache_reason="guardrail_blocked",
            )
        elif is_action_intent(question):
            try:
                if not session_id:
                    return AssistantOutcome(response=BLOCKED_RESPONSE, outcome="blocked")
                product = self.fetch_product(product_id)
                prod_name = product.get("name", "Product") if isinstance(product, dict) else "Product"
                qty_match = re.search(r"(?:thêm|add)\s+(\d{1,2})", question.lower())
                qty = max(1, min(int(qty_match.group(1)), 10)) if qty_match else 1
                confirmation_token = session_store.create_cart_proposal(
                    user_id, session_id, product_id, prod_name, qty
                )
                proposal = demo_pb2.CartActionProposal(
                    action_type="ADD_TO_CART",
                    product_id=product_id,
                    product_name=prod_name,
                    quantity=qty,
                    confirmation_required=True,
                    idempotency_key=confirmation_token,
                )
                return AssistantOutcome(
                    response=f"I can help add '{prod_name}' to your cart. Please confirm below.",
                    outcome="answered",
                    action_proposal=proposal,
                    cache_reason="action_proposal",
                )
            except Exception:
                return AssistantOutcome(
                    response=UNAVAILABLE_RESPONSE,
                    outcome="unavailable",
                    cache_reason="action_proposal_error",
                )
        cache_identity = None
        cache_reason = "cold"
        cache_lookup_latency_ms = 0.0
        cache_lock = None
        try:
            product = self.fetch_product(product_id)
            review_rows = self.fetch_reviews(product_id)
            prepared = prepare_context(question, product, review_rows)
            quarantined_reviews = prepared.quarantined_review_count
            if not prepared.reviews:
                return AssistantOutcome(
                    response=INSUFFICIENT_RESPONSE,
                    outcome="insufficient",
                    quarantined_reviews=prepared.quarantined_review_count,
                    cache_eligible=True,
                    cache_reason="insufficient_source",
                )
            if not user_id or user_id == "guest":
                provider_attempted = True
                result = self.provider.converse(
                    prepared.question,
                    prepared.product,
                    prepared.reviews,
                )
                validated = validate_grounded_output(
                    result.payload,
                    prepared.reviews,
                    self.system_canary,
                )
                return AssistantOutcome(
                    response=validated["answer"],
                    outcome=validated["decision"],
                    latency_ms=result.latency_ms,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    quarantined_reviews=prepared.quarantined_review_count,
                    provider_stop_reason=result.stop_reason,
                    response_contract_stage=result.contract_stage,
                    provider_attempted=True,
                    cache_eligible=False,
                    cache_reason="missing_user_identity",
                    model_calls=1,
                    citations=tuple(validated["citations"]),
                )
            fingerprint = source_fingerprint(prepared.product, prepared.reviews)
            cache_identity = self.response_cache.identity(
                surface="product_qa",
                user_id=user_id,
                product_id=product_id,
                request=prepared.question,
                dependency_class="explicit_product_qa_v1",
                model_id=self.provider.model_id,
                prompt_version=PRODUCT_QA_PROMPT_VERSION,
                guardrail_version=(
                    f"{getattr(self.provider, 'guardrail_id', '')}:"
                    f"{self.provider.guardrail_version}"
                ),
                response_schema_version=RESPONSE_SCHEMA_VERSION,
                fingerprint=fingerprint,
            )
            lookup = self.response_cache.lookup(cache_identity)
            cache_reason = lookup.reason
            cache_lookup_latency_ms = lookup.lookup_latency_ms
            if lookup.status == "hit" and lookup.value:
                cached = lookup.value
                return AssistantOutcome(
                    response=str(cached["response"]),
                    outcome=str(cached["outcome"]),
                    quarantined_reviews=prepared.quarantined_review_count,
                    citations=tuple(cached.get("citations") or ()),
                    cache_status="hit",
                    cache_eligible=True,
                    cache_reason="hit",
                    model_calls=0,
                    cache_lookup_latency_ms=lookup.lookup_latency_ms,
                    saved_model_calls=1,
                    saved_input_tokens=int(cached.get("input_tokens", 0)),
                    saved_output_tokens=int(cached.get("output_tokens", 0)),
                )

            cache_lock = self.response_cache.acquire_lock(cache_identity)
            if cache_lock is None and cache_reason != "cache_error":
                waited = self.response_cache.wait_for_fill(cache_identity)
                cache_lookup_latency_ms += waited.lookup_latency_ms
                if waited.status == "hit" and waited.value:
                    cached = waited.value
                    return AssistantOutcome(
                        response=str(cached["response"]),
                        outcome=str(cached["outcome"]),
                        quarantined_reviews=prepared.quarantined_review_count,
                        citations=tuple(cached.get("citations") or ()),
                        cache_status="hit",
                        cache_eligible=True,
                        cache_reason="hit_after_wait",
                        model_calls=0,
                        cache_lookup_latency_ms=cache_lookup_latency_ms,
                        saved_model_calls=1,
                        saved_input_tokens=int(cached.get("input_tokens", 0)),
                        saved_output_tokens=int(cached.get("output_tokens", 0)),
                    )
                if waited.reason == "cache_error":
                    cache_reason = "cache_error"
                elif waited.reason == "lock_timeout":
                    return AssistantOutcome(
                        response=UNAVAILABLE_RESPONSE,
                        outcome="unavailable",
                        error_class="cache_fill_in_progress",
                        quarantined_reviews=prepared.quarantined_review_count,
                        provider_attempted=False,
                        cache_eligible=True,
                        cache_reason="lock_timeout",
                        model_calls=0,
                        cache_lookup_latency_ms=cache_lookup_latency_ms,
                    )

            provider_attempted = True
            result = self.provider.converse(prepared.question, prepared.product, prepared.reviews)
            validated = validate_grounded_output(result.payload, prepared.reviews, self.system_canary)
            outcome = AssistantOutcome(
                response=validated["answer"],
                outcome=validated["decision"],
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                quarantined_reviews=prepared.quarantined_review_count,
                provider_stop_reason=result.stop_reason,
                response_contract_stage=result.contract_stage,
                provider_attempted=True,
                cache_eligible=True,
                cache_reason=cache_reason,
                model_calls=1,
                cache_lookup_latency_ms=cache_lookup_latency_ms,
                citations=tuple(validated["citations"]),
            )
            if validated["decision"] == "answered" and cache_identity is not None:
                wrote = self.response_cache.write(
                    cache_identity,
                    {
                        "response": outcome.response,
                        "outcome": outcome.outcome,
                        "citations": list(outcome.citations),
                        "input_tokens": outcome.input_tokens,
                        "output_tokens": outcome.output_tokens,
                    },
                )
                if not wrote and outcome.cache_reason != "cache_error":
                    outcome = AssistantOutcome(
                        **{
                            **outcome.__dict__,
                            "cache_reason": "cache_error",
                        }
                    )
            return outcome
        except ProviderFailure as exc:
            outcome = "blocked" if exc.error_class == "guardrail_intervened" else "unavailable"
            response = BLOCKED_RESPONSE if outcome == "blocked" else UNAVAILABLE_RESPONSE
            return AssistantOutcome(
                response=response,
                outcome=outcome,
                error_class=exc.error_class,
                quarantined_reviews=quarantined_reviews,
                latency_ms=exc.latency_ms,
                input_tokens=exc.input_tokens,
                output_tokens=exc.output_tokens,
                provider_stop_reason=exc.stop_reason,
                response_contract_stage=exc.contract_stage,
                provider_attempted=True,
                cache_eligible=True,
                cache_reason=cache_reason,
                model_calls=1,
                cache_lookup_latency_ms=cache_lookup_latency_ms,
            )
        except UnsafeModelOutput as exc:
            return AssistantOutcome(
                response=INSUFFICIENT_RESPONSE,
                outcome="insufficient",
                error_class=str(exc),
                quarantined_reviews=quarantined_reviews,
                provider_attempted=True,
                cache_eligible=True,
                cache_reason="invalid_response",
                model_calls=1,
                cache_lookup_latency_ms=cache_lookup_latency_ms,
            )
        except Exception as exc:
            # Fail closed without returning or logging provider/database details.
            return AssistantOutcome(
                response=UNAVAILABLE_RESPONSE,
                outcome="unavailable",
                error_class=type(exc).__name__.lower()[:64],
                quarantined_reviews=quarantined_reviews,
                provider_attempted=provider_attempted,
                cache_eligible=cache_identity is not None,
                cache_reason=cache_reason,
                model_calls=1 if provider_attempted else 0,
                cache_lookup_latency_ms=cache_lookup_latency_ms,
            )
        finally:
            if cache_identity is not None:
                self.response_cache.release_lock(cache_identity, cache_lock)
