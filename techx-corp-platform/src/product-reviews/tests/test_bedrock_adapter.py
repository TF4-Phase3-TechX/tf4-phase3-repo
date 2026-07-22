import json

import pytest

from bedrock_adapter import BedrockAdapter, CircuitBreaker, CircuitOpen, ProviderFailure


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.request = None

    def converse(self, **request):
        self.request = request
        if self.error:
            raise self.error
        return self.response


def response_with(payload):
    return {
        "stopReason": "end_turn",
        "output": {"message": {"content": [{"text": json.dumps(payload)}]}},
        "usage": {"inputTokens": 100, "outputTokens": 20},
    }


def tool_response_with(tool_input, *, stop_reason="tool_use", tool_name="emit_grounded_answer"):
    return {
        "stopReason": stop_reason,
        "output": {"message": {"content": [{"toolUse": {
            "name": tool_name,
            "input": tool_input,
        }}]}},
        "usage": {"inputTokens": 101, "outputTokens": 21},
    }


def adapter(client, **kwargs):
    return BedrockAdapter(
        model_id="model",
        guardrail_id="guardrail",
        guardrail_version="3",
        client=client,
        **kwargs,
    )


def test_converse_is_single_call_pinned_guardrail_and_structured_output():
    payload = {"decision": "insufficient", "answer": "", "citations": []}
    client = FakeClient(response_with(payload))
    result = adapter(client).converse("question", {"id": "p1"}, [{"review_id": 1, "description": "safe"}])

    assert result.payload == payload
    assert result.input_tokens == 100
    assert client.request["guardrailConfig"] == {
        "guardrailIdentifier": "guardrail",
        "guardrailVersion": "3",
        "trace": "disabled",
    }
    assert client.request["inferenceConfig"] == {"temperature": 0, "maxTokens": 512}
    assert client.request["outputConfig"]["textFormat"]["type"] == "json_schema"

    guarded_blocks = client.request["messages"][0]["content"]
    assert len(guarded_blocks) == 2
    assert all(set(block) == {"guardContent"} for block in guarded_blocks)

    context_block = guarded_blocks[0]["guardContent"]["text"]
    question_block = guarded_blocks[1]["guardContent"]["text"]
    assert json.loads(context_block["text"]) == {
        "product": {"id": "p1"},
        "reviews": [{"review_id": 1, "description": "safe"}],
    }
    assert context_block["qualifiers"] == ["grounding_source", "guard_content"]
    assert question_block == {
        "text": "question",
        "qualifiers": ["query", "guard_content"],
    }
    assert all(
        "guard_content" in block["guardContent"]["text"]["qualifiers"]
        for block in guarded_blocks
    )


def test_guardrail_intervention_is_a_safe_provider_failure():
    client = FakeClient({"stopReason": "guardrail_intervened"})
    breaker = CircuitBreaker(threshold=1)
    with pytest.raises(ProviderFailure, match="guardrail_intervened"):
        adapter(client, circuit_breaker=breaker).converse("q", {}, [{}])
    # An intervention is a policy result, not a provider outage.
    breaker.before_call(0)


def test_nova_tool_mode_only_accepts_forced_non_action_tool():
    client = FakeClient(tool_response_with({"decision": "insufficient", "answer": "", "citations": []}))
    result = adapter(client, output_mode="tool").converse("q", {}, [{}])
    assert result.payload["decision"] == "insufficient"
    assert result.stop_reason == "tool_use"
    assert result.contract_stage == "tool_input_dict"
    assert client.request["toolConfig"]["toolChoice"] == {"tool": {"name": "emit_grounded_answer"}}
    tool_schema = client.request["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"]
    assert set(tool_schema) == {"type", "properties", "required"}
    assert tool_schema["type"] == "object"


@pytest.mark.parametrize(
    ("tool_input", "expected_stage"),
    [
        ("not-json", "tool_input_type"),
        ("[]", "tool_input_type"),
        (42, "tool_input_type"),
    ],
)
def test_nova_tool_mode_rejects_non_object_or_invalid_tool_input_safely(tool_input, expected_stage):
    with pytest.raises(ProviderFailure) as failure:
        adapter(FakeClient(tool_response_with(tool_input)), output_mode="tool").converse("q", {}, [{}])

    assert failure.value.error_class == "invalid_response"
    assert failure.value.contract_stage == expected_stage
    assert failure.value.stop_reason == "tool_use"
    assert failure.value.input_tokens == 101
    assert failure.value.output_tokens == 21


@pytest.mark.parametrize(
    ("response", "expected_stage"),
    [
        (tool_response_with({}, stop_reason="end_turn"), "tool_stop_reason"),
        (tool_response_with({}, stop_reason="max_tokens"), "tool_stop_reason"),
        (tool_response_with({}, tool_name="unexpected_tool"), "tool_name"),
        ({"stopReason": "tool_use", "output": {"message": {"content": []}}, "usage": {}}, "tool_block_count"),
    ],
)
def test_nova_tool_mode_rejects_unexpected_contract_shape_without_content(response, expected_stage):
    with pytest.raises(ProviderFailure) as failure:
        adapter(FakeClient(response), output_mode="tool").converse("q", {}, [{}])

    assert failure.value.error_class == "invalid_response"
    assert failure.value.contract_stage == expected_stage


def test_response_after_deadline_fails_closed_and_preserves_billable_usage():
    clock_values = iter((0.0, 4.6, 4.6))

    with pytest.raises(ProviderFailure) as failure:
        adapter(
            FakeClient(tool_response_with({"decision": "insufficient", "answer": "", "citations": []})),
            output_mode="tool",
            deadline_seconds=4.5,
            clock=lambda: next(clock_values),
        ).converse("q", {}, [{}])

    assert failure.value.error_class == "deadline_exceeded"
    assert failure.value.latency_ms == pytest.approx(4_600)
    assert failure.value.input_tokens == 101
    assert failure.value.output_tokens == 21
    assert failure.value.stop_reason == "tool_use"
    assert failure.value.contract_stage == "deadline_exceeded"


def test_diagnostic_dimensions_reject_unbounded_provider_values():
    failure = ProviderFailure(
        "invalid_response",
        stop_reason="provider-returned-content",
        contract_stage="dynamic-untrusted-stage",
    )

    assert failure.stop_reason == "missing_or_unknown"
    assert failure.contract_stage == "missing_or_unknown"


def test_circuit_opens_after_five_failures_and_recovers_after_cooldown():
    breaker = CircuitBreaker(threshold=5, window_seconds=30, cooldown_seconds=60)
    for now in range(5):
        breaker.before_call(now)
        breaker.failure(now)
    with pytest.raises(CircuitOpen):
        breaker.before_call(5)
    breaker.before_call(65)


def test_rejects_draft_guardrail():
    with pytest.raises(ValueError, match="numeric"):
        BedrockAdapter("model", "guardrail", "DRAFT", client=FakeClient())
