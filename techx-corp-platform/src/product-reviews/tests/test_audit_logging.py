import pytest

from audit_logging import emit_ai_tool_audit, safety_decision_for_outcome


class RecordingLogger:
    def __init__(self):
        self.calls = []

    def info(self, message, *, extra):
        self.calls.append((message, extra))


def test_canonical_audit_event_has_exact_eight_fields_and_no_content():
    logger = RecordingLogger()

    emit_ai_tool_audit(
        logger,
        trace_id="ec1f8f0087cd980b7bdad98ba0daf39d",
        surface="product_qa",
        model_id="us.amazon.nova-2-lite-v1:0",
        tool_name="bedrock.converse",
        safety_decision="provider_unavailable",
        confirmation_status="not_required",
    )

    assert len(logger.calls) == 1
    message, event = logger.calls[0]
    assert message == "ai_tool_audit"
    assert event == {
        "log_type": "ai_tool_audit",
        "trace_id": "ec1f8f0087cd980b7bdad98ba0daf39d",
        "surface": "product_qa",
        "model_id": "us.amazon.nova-2-lite-v1:0",
        "tool_name": "bedrock.converse",
        "tool_input_redacted": {"redacted": True, "content_logged": False},
        "safety_decision": "provider_unavailable",
        "confirmation_status": "not_required",
    }
    assert not ({"prompt", "response", "user_id", "session_id", "confirmation_token"} & event.keys())


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("answered", "allow"),
        ("blocked", "block"),
        ("insufficient", "refuse"),
        ("out_of_scope", "refuse"),
        ("unavailable", "provider_unavailable"),
        ("provider_failure", "provider_unavailable"),
    ],
)
def test_safety_decision_mapping_is_bounded(outcome, expected):
    assert safety_decision_for_outcome(outcome) == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [("safety_decision", "unknown"), ("confirmation_status", "expired")],
)
def test_canonical_audit_event_rejects_unbounded_values(field, value):
    kwargs = {
        "trace_id": "0" * 32,
        "surface": "product_qa",
        "model_id": "model",
        "tool_name": "bedrock.converse",
        "safety_decision": "allow",
        "confirmation_status": "not_required",
    }
    kwargs[field] = value

    with pytest.raises(ValueError):
        emit_ai_tool_audit(RecordingLogger(), **kwargs)
