"""Content-free OpenTelemetry helpers for reconstructable AI request traces."""

from __future__ import annotations

import functools
import hashlib
import hmac
import os
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode


_TRACER = trace.get_tracer("product-reviews.llm-observability")


def observability_enabled() -> bool:
    """Return whether the identity-bearing Mandate 24 contract is active."""
    configured = os.environ.get("LLM_OBSERVABILITY_ENABLED")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return os.environ.get("APP_ENV", "local").strip().lower() in {
        "production",
        "staging",
    }


def validate_observability_configuration() -> None:
    """Fail service startup when the enabled identity contract lacks its salt."""
    if observability_enabled() and not os.environ.get(
        "LLM_OBSERVABILITY_HASH_SALT"
    ):
        raise RuntimeError("llm_observability_hash_salt_missing")


def current_trace_id() -> str:
    """Return the active W3C trace ID, or the all-zero sentinel without a span."""
    context = trace.get_current_span().get_span_context()
    return f"{context.trace_id:032x}"


def pseudonymize(value: str) -> str:
    """Return a bounded pseudonym without retaining the caller-supplied value."""
    if not value:
        return "absent"
    validate_observability_configuration()
    salt = os.environ["LLM_OBSERVABILITY_HASH_SALT"]
    digest = hmac.new(
        salt.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:24]


def annotate_request(surface: str, user_id: str, session_id: str) -> str:
    """Attach only bounded metadata to the active request span."""
    span = trace.get_current_span()
    span.set_attribute("app.ai.surface", surface)
    enabled = observability_enabled()
    span.set_attribute("app.ai.observability.enabled", enabled)
    if not enabled:
        span.set_attribute("app.content.retained", False)
        return current_trace_id()
    span.set_attribute("app.user.pseudonym", pseudonymize(user_id))
    span.set_attribute("app.session.pseudonym", pseudonymize(session_id))
    span.set_attribute("app.content.retained", False)
    return current_trace_id()


def _estimated_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens
        * float(os.environ.get("BEDROCK_INPUT_USD_PER_MILLION", "1"))
        + output_tokens
        * float(os.environ.get("BEDROCK_OUTPUT_USD_PER_MILLION", "5"))
    ) / 1_000_000


def _record_model_result(span: Any, value: Any, outcome: str) -> None:
    metadata = value.get("_metadata", {}) if isinstance(value, dict) else {}
    input_tokens = int(
        metadata.get("input_tokens", getattr(value, "input_tokens", 0))
    )
    output_tokens = int(
        metadata.get("output_tokens", getattr(value, "output_tokens", 0))
    )
    span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
    span.set_attribute(
        "app.ai.estimated_cost_usd",
        _estimated_cost(input_tokens, output_tokens),
    )
    span.set_attribute(
        "app.ai.latency_ms",
        float(metadata.get("latency_ms", getattr(value, "latency_ms", 0))),
    )
    stop_reason = (
        value.get("stopReason", "not_received")
        if isinstance(value, dict)
        else getattr(value, "stop_reason", "not_received")
    )
    span.set_attribute("gen_ai.response.finish_reasons", [str(stop_reason)[:64]])
    span.set_attribute(
        "app.ai.response_contract_stage",
        str(getattr(value, "contract_stage", "not_applicable"))[:64],
    )
    span.set_attribute("app.ai.outcome", outcome)


def trace_model_call(
    operation: str,
    output_tool: str,
    circuit_breaker_attr: str | None = None,
) -> Callable:
    """Trace one real provider attempt without accepting prompt/response content."""

    def decorator(function: Callable) -> Callable:
        @functools.wraps(function)
        def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            # A local circuit-open rejection is not a provider attempt and must
            # not create a Bedrock CLIENT span or cost/error attribution.
            if circuit_breaker_attr:
                breaker = getattr(self, circuit_breaker_attr)
                provider_started_at = self.clock()
                breaker.before_call(provider_started_at)
                kwargs["_provider_started_at"] = provider_started_at
            with _TRACER.start_as_current_span(
                "bedrock.converse",
                kind=SpanKind.CLIENT,
            ) as span:
                span.set_attribute("gen_ai.provider.name", "aws.bedrock")
                span.set_attribute("gen_ai.operation.name", operation)
                span.set_attribute("gen_ai.request.model", str(self.model_id)[:256])
                span.set_attribute(
                    "app.ai.guardrail.version",
                    str(self.guardrail_version)[:64],
                )
                span.set_attribute("gen_ai.tool.name", output_tool)
                span.set_attribute("app.content.retained", False)
                try:
                    result = function(self, *args, **kwargs)
                except Exception as exc:
                    _record_model_result(span, exc, "error")
                    error_class = str(
                        getattr(exc, "error_class", type(exc).__name__.lower())
                    )[:64]
                    span.set_attribute("error.type", error_class)
                    span.set_status(Status(StatusCode.ERROR, error_class))
                    raise
                _record_model_result(span, result, "success")
                return result

        return wrapped

    return decorator


@contextmanager
def tool_span(intent: Any, tool_name: str) -> Iterator[Any]:
    """Create a content-free child span around an application tool boundary."""
    with _TRACER.start_as_current_span(
        f"tool.{tool_name}",
        kind=SpanKind.INTERNAL,
    ) as span:
        intent_value = getattr(intent, "value", str(intent))
        span.set_attribute("app.ai.tool.name", str(tool_name)[:64])
        span.set_attribute("app.ai.intent", str(intent_value)[:64])
        span.set_attribute("app.content.retained", False)
        try:
            yield span
        except Exception as exc:
            error_class = type(exc).__name__.lower()[:64]
            span.set_attribute("app.ai.tool.outcome", "error")
            span.set_attribute("error.type", error_class)
            span.set_status(Status(StatusCode.ERROR, error_class))
            raise
        span.set_attribute("app.ai.tool.outcome", "success")
