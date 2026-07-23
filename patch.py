import re

with open("techx-corp-platform/src/product-reviews/product_reviews_server.py", "r") as f:
    content = f.read()

# 1. Add _log_ai_tool_audit before configure_logging
helper_code = """
def _log_ai_tool_audit(
    surface: str,
    model_id: str,
    tool_name: str,
    safety_decision: str,
    confirmation_status: str = "not_required",
    **extra_kwargs
):
    ctx = trace.get_current_span().get_span_context()
    trace_id = format(ctx.trace_id, '032x') if ctx.is_valid else ""
    extra = {
        "log_type": "ai_tool_audit",
        "trace_id": trace_id,
        "surface": surface,
        "model_id": model_id,
        "tool_name": tool_name,
        "tool_input_redacted": {"redacted": True, "content_logged": False},
        "safety_decision": safety_decision,
        "confirmation_status": confirmation_status,
    }
    extra.update(extra_kwargs)
    logger.info("ai_tool_audit", extra=extra)


def configure_logging(service_name: str) -> None:"""

content = content.replace("def configure_logging(service_name: str) -> None:", helper_code)

# 2. Replace ai_assistant_completed
old_ai_assistant = """        logger.info(
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
        )"""

new_ai_assistant = """        safety_decision = "allow"
        if outcome.outcome == "blocked":
            safety_decision = "block"
        elif outcome.outcome == "insufficient":
            safety_decision = "refuse"
        elif outcome.outcome == "unavailable":
            safety_decision = "provider_unavailable"

        _log_ai_tool_audit(
            surface="product_qa",
            model_id=assistant.provider.model_id,
            tool_name="bedrock.converse",
            safety_decision=safety_decision,
            confirmation_status="not_required",
            guardrail_version=assistant.provider.guardrail_version,
            latency_ms=round(outcome.latency_ms, 1),
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            estimated_cost_usd=round(estimated_cost, 8),
            error_class=outcome.error_class or "none",
            provider_stop_reason=outcome.provider_stop_reason,
            response_contract_stage=outcome.response_contract_stage,
            quarantined_reviews=outcome.quarantined_reviews,
        )"""

content = content.replace(old_ai_assistant, new_ai_assistant)

# 3. Replace nl_search_completed
old_nl_search = """            logger.info(
                "nl_search_completed",
                extra={
                    "search_type": intent.get("search_type"),
                    "candidate_count_before": candidate_count_before,
                    "candidate_count_after": candidate_count_after,
                    "input_tokens": _in_tok,
                    "output_tokens": _out_tok,
                    "estimated_cost_usd": round(cost, 8),
                },
            )"""

new_nl_search = """            _log_ai_tool_audit(
                surface="copilot_search",
                model_id=assistant.provider.model_id,
                tool_name="bedrock.converse",
                safety_decision="allow",
                confirmation_status="not_required",
                search_type=intent.get("search_type"),
                candidate_count_before=candidate_count_before,
                candidate_count_after=candidate_count_after,
                input_tokens=_in_tok,
                output_tokens=_out_tok,
                estimated_cost_usd=round(cost, 8),
            )"""

content = content.replace(old_nl_search, new_nl_search)

# 4. Replace nl_search_provider_failure
old_nl_fail = """            logger.info("nl_search_provider_failure", extra={"error_class": exc.error_class})"""
new_nl_fail = """            _log_ai_tool_audit(
                surface="copilot_search",
                model_id=assistant.provider.model_id,
                tool_name="bedrock.converse",
                safety_decision="provider_unavailable",
                confirmation_status="not_required",
                error_class=exc.error_class,
            )"""

content = content.replace(old_nl_fail, new_nl_fail)

# 5. Replace nl_search_unexpected_error
old_nl_err = """            logger.info("nl_search_unexpected_error", extra={"error": str(exc)[:200]})"""
new_nl_err = """            _log_ai_tool_audit(
                surface="copilot_search",
                model_id=assistant.provider.model_id,
                tool_name="bedrock.converse",
                safety_decision="provider_unavailable",
                confirmation_status="not_required",
                error=str(exc)[:200],
            )"""

content = content.replace(old_nl_err, new_nl_err)

# 6. Replace ConfirmCartAction logs
old_confirm = """        if not proposal:
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
        return demo_pb2.ConfirmCartActionResponse(applied=True, outcome="applied")"""

new_confirm = """        if not proposal:
            span.set_attribute("app.cart.confirmation.outcome", "invalid_or_expired")
            _log_ai_tool_audit(
                surface="copilot_search",
                model_id="N/A",
                tool_name="modify_cart",
                safety_decision="allow",
                confirmation_status="rejected",
                outcome="invalid_or_expired"
            )
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
            _log_ai_tool_audit(
                surface="copilot_search",
                model_id="N/A",
                tool_name="modify_cart",
                safety_decision="provider_unavailable",
                confirmation_status="rejected",
                grpc_code=str(exc.code())
            )
            return demo_pb2.ConfirmCartActionResponse(applied=False, outcome="downstream_failed")

        span.set_attribute("app.cart.confirmation.outcome", "applied")
        span.set_attribute("app.cart.product_id", proposal["product_id"])
        _log_ai_tool_audit(
            surface="copilot_search",
            model_id="N/A",
            tool_name="modify_cart",
            safety_decision="allow",
            confirmation_status="confirmed",
            product_id=proposal["product_id"]
        )
        return demo_pb2.ConfirmCartActionResponse(applied=True, outcome="applied")"""

content = content.replace(old_confirm, new_confirm)

with open("techx-corp-platform/src/product-reviews/product_reviews_server.py", "w") as f:
    f.write(content)
