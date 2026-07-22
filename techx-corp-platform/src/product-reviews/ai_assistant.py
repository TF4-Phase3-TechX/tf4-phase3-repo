#!/usr/bin/python

"""Application-owned orchestration for grounded product Q&A."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import copy
import logging
import time

logger = logging.getLogger(__name__)

import re
import uuid
from bedrock_adapter import BedrockAdapter, ProviderFailure
import demo_pb2
from safety import (
    BLOCKED_RESPONSE,
    INSUFFICIENT_RESPONSE,
    UNAVAILABLE_RESPONSE,
    UnsafeModelOutput,
    is_attack,
    is_action_intent,
    is_attack_or_action,
    prepare_context,
    validate_grounded_output,
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


class GroundedAssistant:
    def __init__(
        self,
        provider: BedrockAdapter,
        fetch_product: Callable[[str], dict[str, Any]],
        fetch_reviews: Callable[[str], list[tuple[Any, ...]]],
        system_canary: str = "",
    ):
        self.provider = provider
        self.fetch_product = fetch_product
        self.fetch_reviews = fetch_reviews
        self.system_canary = system_canary

    def answer(self, product_id: str, question: str, session_id: str = "") -> AssistantOutcome:
        quarantined_reviews = 0
        if not question or is_attack(question):
            return AssistantOutcome(response=BLOCKED_RESPONSE, outcome="blocked")
        elif is_action_intent(question):
            try:
                product = self.fetch_product(product_id)
                prod_name = product.get("name", "Product") if isinstance(product, dict) else "Product"
                qty_match = re.search(r"(?:thêm|add)\s+(\d{1,2})", question.lower())
                qty = max(1, min(int(qty_match.group(1)), 10)) if qty_match else 1
                proposal = demo_pb2.CartActionProposal(
                    action_type="ADD_TO_CART",
                    product_id=product_id,
                    product_name=prod_name,
                    quantity=qty,
                    confirmation_required=True,
                    idempotency_key=str(uuid.uuid4()),
                )
                if session_id:
                    session_store.append_turn("guest", session_id, "user", question)
                    session_store.append_turn("guest", session_id, "assistant", f"I can help add '{prod_name}' to your cart.")
                return AssistantOutcome(
                    response=f"I can help add '{prod_name}' to your cart. Please confirm below.",
                    outcome="answered",
                    action_proposal=proposal,
                )
            except Exception:
                pass
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
                )
            result = self.provider.converse(prepared.question, prepared.product, prepared.reviews)
            validated = validate_grounded_output(result.payload, prepared.reviews, self.system_canary)
            if session_id and validated.get("answer"):
                session_store.append_turn("guest", session_id, "user", question)
                session_store.append_turn("guest", session_id, "assistant", validated["answer"])
            return AssistantOutcome(
                response=validated["answer"],
                outcome=validated["decision"],
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                quarantined_reviews=prepared.quarantined_review_count,
                provider_stop_reason=result.stop_reason,
                response_contract_stage=result.contract_stage,
            )
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
            )
        except UnsafeModelOutput as exc:
            return AssistantOutcome(
                response=INSUFFICIENT_RESPONSE,
                outcome="insufficient",
                error_class=str(exc),
                quarantined_reviews=quarantined_reviews,
            )
        except Exception as exc:
            # Fail closed without returning or logging provider/database details.
            return AssistantOutcome(
                response=UNAVAILABLE_RESPONSE,
                outcome="unavailable",
                error_class=type(exc).__name__.lower()[:64],
                quarantined_reviews=quarantined_reviews,
            )


def log_tool_audit(tool_name: str, args: dict, trace_id: str):
    sanitized_args = copy.deepcopy(args)
    sensitive_keys = ('password', 'secret', 'token', 'key', 'email', 'phone')
    for k in list(sanitized_args.keys()):
        if any(sensitive in k.lower() for sensitive in sensitive_keys):
            sanitized_args[k] = "[REDACTED_SECRET]"
            
    logger.info(
        "agent_tool_call",
        extra={
            "event": "agent_tool_call",
            "trace_id": trace_id,
            "tool_name": tool_name,
            "sanitized_args": sanitized_args
        }
    )

def run_copilot_loop(user_query: str):
    MAX_ITERATIONS = 25
    LATENCY_BUDGET_SEC = 4.5
    start_time = time.monotonic()
    
    for iteration in range(MAX_ITERATIONS):
        # a. [Pre-flight Check]
        elapsed_time = time.monotonic() - start_time
        if elapsed_time >= LATENCY_BUDGET_SEC:
            logger.warning("Latency budget exhausted")
            break
            
        # b. [Mock Action]
        mock_tool_name = "search_products"
        mock_args = {"query": user_query, "api_key": "sk-12345"}
        
        # c. [Audit]
        log_tool_audit(tool_name=mock_tool_name, args=mock_args, trace_id="mock_trace_123")
        
        # d. [Safety Net]
        if iteration == MAX_ITERATIONS - 1:
            logger.warning("Max iterations reached")
            break
            
    return "Tôi đang xử lý quá nhiều thông tin, vui lòng thử lại với câu hỏi ngắn gọn hơn."
