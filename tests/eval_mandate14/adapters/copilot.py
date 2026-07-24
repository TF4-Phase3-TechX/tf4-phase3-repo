"""Run supplied Copilot turns through the production gRPC boundary."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

import grpc

try:
    import demo_pb2
    import demo_pb2_grpc
except ImportError:  # Loaded by the standalone harness.
    import sys
    from pathlib import Path

    product_reviews_dir = (
        Path(__file__).resolve().parents[3]
        / "techx-corp-platform"
        / "src"
        / "product-reviews"
    )
    sys.path.insert(0, str(product_reviews_dir))
    import demo_pb2  # type: ignore[no-redef]
    import demo_pb2_grpc  # type: ignore[no-redef]


def _sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _price(product: Any) -> float:
    money = getattr(product, "price_usd", None)
    return float(getattr(money, "units", 0)) + float(getattr(money, "nanos", 0)) / 1e9


def _catalog_evidence(products: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    sources: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    rendered: list[str] = []
    for product in products:
        categories = ", ".join(sorted(str(value) for value in product.categories))
        text = (
            f"{product.name}. {product.description}. "
            f"Price ${_price(product):.2f}. Categories: {categories}."
        )
        source_id = f"catalog:{product.id}"
        sources.append({
            "source_id": source_id,
            "source_type": "catalog",
            "text": text,
        })
        claims.append({
            "text": text,
            "claim_type": "fact",
            "source_ids": [source_id],
        })
        rendered.append(text)
    return sources, claims, "\n".join(rendered)


class CopilotAdapter:
    def __init__(self, search_stub: Any, cart_stub: Any | None = None):
        self.search_stub = search_stub
        self.cart_stub = cart_stub

    @classmethod
    def from_targets(
        cls,
        product_reviews_target: str,
        cart_target: str | None,
    ) -> "CopilotAdapter":
        search_channel = grpc.insecure_channel(product_reviews_target)
        cart_stub = None
        if cart_target:
            cart_channel = grpc.insecure_channel(cart_target)
            cart_stub = demo_pb2_grpc.CartServiceStub(cart_channel)
        return cls(
            demo_pb2_grpc.ProductReviewServiceStub(search_channel),
            cart_stub,
        )

    def _cart_state(self, user_id: str) -> dict[str, Any] | None:
        if self.cart_stub is None:
            return None
        cart = self.cart_stub.GetCart(
            demo_pb2.GetCartRequest(user_id=user_id),
            timeout=5.0,
        )
        return {
            "user_id": user_id,
            "items": sorted(
                (
                    {
                        "product_id": str(item.product_id),
                        "quantity": int(item.quantity),
                    }
                    for item in cart.items
                ),
                key=lambda item: (item["product_id"], item["quantity"]),
            ),
        }

    def run(self, case: dict[str, Any]) -> dict[str, Any]:
        payload = case["input"]
        expected = case["expected"]
        user_id = str(payload.get("user_id") or f"m14-{case['case_id']}")
        session_id = str(
            payload.get("session_id")
            or f"m14-{case['case_id']}-{uuid.uuid4().hex[:10]}"
        )
        write_requested = bool(expected.get("write_requested", False))
        if write_requested and self.cart_stub is None:
            raise ValueError(
                f"{case['case_id']}: --cart-target is required for write-state observation"
            )

        state_before = self._cart_state(user_id)
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        model_requests = 0
        final_response = None
        started = time.perf_counter()
        queries = [str(value) for value in payload.get("turns", [])]
        queries.append(str(payload["query"]))
        for query in queries:
            response = self.search_stub.SearchProductsAIAssistant(
                demo_pb2.SearchProductsAIAssistantRequest(
                    query=query,
                    session_id=session_id,
                    user_id=user_id,
                ),
                timeout=float(payload.get("timeout_seconds", 30)),
            )
            trace = response.trace
            total_input_tokens += int(trace.input_tokens)
            total_output_tokens += int(trace.output_tokens)
            total_cost += float(trace.estimated_cost_usd)
            model_requests += int(trace.input_tokens > 0 or trace.output_tokens > 0)
            final_response = response

        assert final_response is not None
        products = list(final_response.results)
        sources, claims, rendered_products = _catalog_evidence(products)
        response_text = str(final_response.response or "")
        if rendered_products:
            response_text = "\n".join(
                value for value in (response_text, rendered_products) if value
            )

        proposal = final_response.action_proposal
        action_proposed = bool(proposal and proposal.product_id)
        confirmation_received = False
        confirmation_token_valid = False
        confirmation_binding_match = False
        write_attempted = False
        write_applied = False
        tool_calls: list[dict[str, Any]] = []
        actual_outcome = str(final_response.outcome or "")
        if bool(payload.get("confirm", False)):
            if not bool(expected.get("write_authorized", False)):
                raise ValueError(
                    f"{case['case_id']}: confirm=true requires expected.write_authorized=true"
                )
            if not action_proposed:
                raise ValueError(f"{case['case_id']}: no confirmation proposal was returned")
            confirmation_received = True
            confirmation_binding_match = True
            write_attempted = True
            tool_calls.append({
                "name": "modify_cart",
                "side_effect": True,
                "arguments": {
                    "product_id": str(proposal.product_id),
                    "quantity": int(proposal.quantity),
                    "token_redacted": True,
                },
            })
            confirmed = self.search_stub.ConfirmCartAction(
                demo_pb2.ConfirmCartActionRequest(
                    user_id=user_id,
                    session_id=session_id,
                    confirmation_token=str(proposal.idempotency_key),
                ),
                timeout=10.0,
            )
            confirmation_token_valid = confirmed.outcome != "invalid_or_expired"
            write_applied = bool(confirmed.applied)
            actual_outcome = str(confirmed.outcome)

        state_after = self._cart_state(user_id)
        latency_ms = (time.perf_counter() - started) * 1_000
        blocked = bool(
            final_response.trace.refused
            or actual_outcome in {"blocked", "guardrail_blocked", "out_of_scope"}
        )
        return {
            "_sources": sources,
            "outcome": actual_outcome,
            "response_text": response_text,
            "output_fields": {
                "products": [
                    {
                        "id": str(product.id),
                        "name": str(product.name),
                        "price_usd": _price(product),
                    }
                    for product in products
                ],
                "action_proposal": (
                    {
                        "action_type": str(proposal.action_type),
                        "product_id": str(proposal.product_id),
                        "quantity": int(proposal.quantity),
                        "confirmation_required": bool(proposal.confirmation_required),
                        "token_redacted": True,
                    }
                    if action_proposed
                    else {}
                ),
            },
            "claims": claims,
            "blocked": blocked,
            "refused": bool(final_response.trace.refused),
            "action_proposed": action_proposed,
            "confirmation_required": bool(
                action_proposed and proposal.confirmation_required
            ),
            "confirmation_received": confirmation_received,
            "confirmation_token_valid": confirmation_token_valid,
            "confirmation_binding_match": confirmation_binding_match,
            "write_attempted": write_attempted,
            "write_applied": write_applied,
            "tool_calls": tool_calls,
            "state_before": state_before,
            "state_after": state_after,
            "state_before_sha256": _sha256(state_before),
            "state_after_sha256": _sha256(state_after),
            "latency_ms": latency_ms,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "model_requests": model_requests,
            "estimated_cost_usd": total_cost,
        }
