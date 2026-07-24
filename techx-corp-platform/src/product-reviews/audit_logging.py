"""Canonical, content-free audit events for AI and business-tool boundaries."""

from __future__ import annotations

import logging

from opentelemetry import trace


SAFETY_DECISIONS = {"allow", "block", "refuse", "provider_unavailable"}
CONFIRMATION_STATUSES = {"not_required", "confirmed", "rejected"}
REDACTED_TOOL_INPUT = {"redacted": True, "content_logged": False}


def safety_decision_for_outcome(outcome: str) -> str:
    """Map application outcomes to the bounded cross-pillar audit vocabulary."""
    if outcome == "blocked":
        return "block"
    if outcome in {"insufficient", "out_of_scope", "refused"}:
        return "refuse"
    if outcome in {"unavailable", "provider_failure"}:
        return "provider_unavailable"
    return "allow"


def current_trace_id() -> str:
    """Return the current W3C trace identifier without logging request content."""
    context = trace.get_current_span().get_span_context()
    return f"{context.trace_id:032x}"


def emit_ai_tool_audit(
    logger: logging.Logger,
    *,
    surface: str,
    model_id: str,
    tool_name: str,
    safety_decision: str,
    confirmation_status: str,
    trace_id: str | None = None,
) -> None:
    """Emit the eight-field canonical event agreed with CDO-07.

    No prompt, response, user/session identity, confirmation token or tool
    payload is accepted by this function. The fixed redaction marker proves
    that the input was intentionally excluded from the audit record.
    """
    if safety_decision not in SAFETY_DECISIONS:
        raise ValueError(f"unsupported safety_decision: {safety_decision}")
    if confirmation_status not in CONFIRMATION_STATUSES:
        raise ValueError(f"unsupported confirmation_status: {confirmation_status}")

    logger.info(
        "ai_tool_audit",
        extra={
            "log_type": "ai_tool_audit",
            "trace_id": trace_id or current_trace_id(),
            "surface": surface,
            "model_id": model_id,
            "tool_name": tool_name,
            "tool_input_redacted": REDACTED_TOOL_INPUT,
            "safety_decision": safety_decision,
            "confirmation_status": confirmation_status,
        },
    )
