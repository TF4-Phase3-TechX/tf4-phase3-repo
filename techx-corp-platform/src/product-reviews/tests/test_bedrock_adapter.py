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


def search_intent_response(intent_payload):
    """Build a well-formed parse_search_intent response from the FakeClient."""
    return {
        "stopReason": "tool_use",
        "output": {"message": {"content": [{"toolUse": {
            "name": "emit_search_intent",
            "input": intent_payload,
        }}]}},
        "usage": {"inputTokens": 50, "outputTokens": 15},
    }


def adapter(client, **kwargs):
    return BedrockAdapter(
        model_id="model",
        guardrail_id="guardrail",
        guardrail_version="3",
        client=client,
        **kwargs,
    )


def disabled_adapter(client, **kwargs):
    return BedrockAdapter(
        model_id="model",
        guardrail_id="disabled",
        guardrail_version="1",
        client=client,
        **kwargs,
    )


# ======================================================================
# converse() — existing tests
# ======================================================================

def test_converse_is_single_call_pinned_guardrail_and_structured_output():
    payload = {"decision": "insufficient", "answer": "", "citations": []}
    client = FakeClient(response_with(payload))
    result = adapter(client).converse("question", {"id": "p1"}, [{"review_id": 1, "description": "safe"}])

    assert result.payload == payload
    assert result.input_tokens == 100
    # _request() adds guardrailConfig for enabled guardrails (no trace key — only
    # parse_search_intent uses trace:"disabled" to avoid leaking query content).
    assert client.request["guardrailConfig"] == {
        "guardrailIdentifier": "guardrail",
        "guardrailVersion": "3",
    }
    assert client.request["inferenceConfig"] == {"temperature": 0, "maxTokens": 512}
    assert client.request["outputConfig"]["textFormat"]["type"] == "json_schema"


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


def test_disabled_guardrail():
    payload = {"decision": "insufficient", "answer": "", "citations": []}
    client = FakeClient(response_with(payload))
    adapter = BedrockAdapter(
        model_id="model",
        guardrail_id="disabled",
        guardrail_version="1",
        client=client,
    )
    result = adapter.converse("question", {"id": "p1"}, [{"review_id": 1, "description": "safe"}])
    assert result.payload == payload
    assert "guardrailConfig" not in client.request
    assert "guardContent" not in client.request["messages"][0]["content"][0]
    assert "text" in client.request["messages"][0]["content"][0]


# ======================================================================
# parse_search_intent() — guardrail wiring
# ======================================================================

def test_parse_search_intent_disabled_guardrail_sends_no_guardrail_config():
    """Sending guardrailIdentifier='disabled' to AWS causes an API error.
    Verify the disabled path omits guardrailConfig entirely and uses plain text."""
    client = FakeClient(search_intent_response({"search_type": "search"}))
    result = disabled_adapter(client).parse_search_intent("show me telescopes")

    assert {k: v for k, v in result.items() if k != "_metadata"} == {"search_type": "search"}
    assert result["_metadata"]["input_tokens"] == 50
    assert result["_metadata"]["output_tokens"] == 15
    assert "guardrailConfig" not in client.request
    # Content must be plain text, not guardContent wrapper
    msg_content = client.request["messages"][0]["content"]
    assert len(msg_content) == 1
    assert "text" in msg_content[0]
    assert "guardContent" not in msg_content[0]


def test_parse_search_intent_enabled_guardrail_attaches_config_and_guard_content():
    client = FakeClient(search_intent_response({"search_type": "search"}))
    result = adapter(client).parse_search_intent("show me telescopes")

    assert {k: v for k, v in result.items() if k != "_metadata"} == {"search_type": "search"}
    assert result["_metadata"]["input_tokens"] == 50
    assert result["_metadata"]["output_tokens"] == 15
    assert client.request["guardrailConfig"]["guardrailIdentifier"] == "guardrail"
    assert client.request["guardrailConfig"]["guardrailVersion"] == "3"
    msg_content = client.request["messages"][0]["content"]
    assert "guardContent" in msg_content[0]


# ======================================================================
# parse_search_intent() — valid payloads accepted
# ======================================================================

def test_parse_search_intent_valid_search_with_all_optional_fields():
    intent = {
        "search_type": "search",
        "category": "telescopes",
        "price_min": 100,
        "price_max": 500,
        "keywords": "refractor",
    }
    client = FakeClient(search_intent_response(intent))
    result = adapter(client).parse_search_intent("refractor telescopes between $100 and $500")
    assert {k: v for k, v in result.items() if k != "_metadata"} == intent
    assert result["_metadata"]["input_tokens"] == 50
    assert result["_metadata"]["output_tokens"] == 15


def test_parse_search_intent_valid_compare_with_two_targets():
    intent = {
        "search_type": "compare",
        "comparison_targets": ["Explorascope", "Starsense"],
    }
    client = FakeClient(search_intent_response(intent))
    result = adapter(client).parse_search_intent("compare Explorascope and Starsense")
    assert result["search_type"] == "compare"
    assert len(result["comparison_targets"]) == 2


def test_parse_search_intent_valid_out_of_scope():
    intent = {"search_type": "out_of_scope"}
    client = FakeClient(search_intent_response(intent))
    result = adapter(client).parse_search_intent("what is the weather today")
    assert result["search_type"] == "out_of_scope"


# ======================================================================
# parse_search_intent() — malformed model output rejected at app boundary
# ======================================================================

@pytest.mark.parametrize("bad_search_type", [
    "unknown_intent",
    "SEARCH",           # case-sensitive enum
    "",                 # empty string
    None,               # missing entirely (via pop below — handled separately)
    123,                # wrong type
])
def test_parse_search_intent_rejects_invalid_search_type(bad_search_type):
    intent = {"search_type": bad_search_type}
    client = FakeClient(search_intent_response(intent))
    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("find me a telescope")
    assert exc_info.value.error_class == "invalid_response"
    assert exc_info.value.input_tokens == 50
    assert exc_info.value.output_tokens == 15


def test_parse_search_intent_rejects_unknown_fields():
    """Unknown keys in payload must be rejected at application boundary."""
    intent = {"search_type": "search", "unexpected_field": "value", "another": 123}
    client = FakeClient(search_intent_response(intent))
    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("find products")
    assert exc_info.value.error_class == "invalid_response"
    assert exc_info.value.input_tokens == 50
    assert exc_info.value.output_tokens == 15


def test_parse_search_intent_rejects_missing_search_type():
    intent = {"category": "telescopes"}  # no search_type key
    client = FakeClient(search_intent_response(intent))
    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("find me a telescope")
    assert exc_info.value.error_class == "invalid_response"


def test_parse_search_intent_rejects_unknown_category():
    intent = {"search_type": "search", "category": "weapons"}
    client = FakeClient(search_intent_response(intent))
    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("show me weapons")
    assert exc_info.value.error_class == "invalid_response"


@pytest.mark.parametrize("bad_field,bad_value", [
    ("category", 42),           # wrong type
    ("keywords", ["list"]),     # wrong type
    ("price_min", "cheap"),     # non-numeric
    ("price_max", True),        # bool is not an acceptable number
    ("price_min", -1),          # negative price
    ("price_max", 2_000_000),   # exceeds sanity cap
])
def test_parse_search_intent_rejects_malformed_optional_fields(bad_field, bad_value):
    intent = {"search_type": "search", bad_field: bad_value}
    client = FakeClient(search_intent_response(intent))
    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("find something")
    assert exc_info.value.error_class == "invalid_response"


def test_parse_search_intent_rejects_price_min_greater_than_price_max():
    intent = {"search_type": "search", "price_min": 500, "price_max": 100}
    client = FakeClient(search_intent_response(intent))
    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("products between 500 and 100")
    assert exc_info.value.error_class == "invalid_response"


def test_parse_search_intent_rejects_non_list_comparison_targets():
    intent = {"search_type": "compare", "comparison_targets": "Explorascope"}
    client = FakeClient(search_intent_response(intent))
    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("compare Explorascope")
    assert exc_info.value.error_class == "invalid_response"


def test_parse_search_intent_rejects_comparison_targets_with_empty_string_entry():
    intent = {"search_type": "compare", "comparison_targets": ["Explorascope", ""]}
    client = FakeClient(search_intent_response(intent))
    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("compare Explorascope and ")
    assert exc_info.value.error_class == "invalid_response"


# ======================================================================
# parse_search_intent() — compare fail-closed (0 and 1 target)
# ======================================================================

def test_parse_search_intent_rejects_compare_with_no_targets():
    """compare + empty targets list must fail closed at the adapter boundary."""
    intent = {"search_type": "compare", "comparison_targets": []}
    client = FakeClient(search_intent_response(intent))
    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("compare something")
    assert exc_info.value.error_class == "invalid_response"


def test_parse_search_intent_rejects_compare_with_single_target():
    """compare with only one target is ambiguous — must fail closed."""
    intent = {"search_type": "compare", "comparison_targets": ["Explorascope"]}
    client = FakeClient(search_intent_response(intent))
    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("compare Explorascope")
    assert exc_info.value.error_class == "invalid_response"


def test_parse_search_intent_rejects_compare_with_absent_targets_key():
    """compare with no comparison_targets key at all must fail closed."""
    intent = {"search_type": "compare"}
    client = FakeClient(search_intent_response(intent))
    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("compare stuff")
    assert exc_info.value.error_class == "invalid_response"


# ======================================================================
# parse_search_intent() — latency and token metadata on failure paths
# ======================================================================

def test_parse_search_intent_deadline_exceeded_preserves_billable_usage():
    # Clock sequence: started=0.0, elapsed check=5.0, breaker.failure=5.0
    clock_values = iter((0.0, 5.0, 5.0))
    client = FakeClient(search_intent_response({"search_type": "search"}))

    with pytest.raises(ProviderFailure) as exc_info:
        adapter(
            client,
            deadline_seconds=4.5,
            clock=lambda: next(clock_values),
        ).parse_search_intent("show me telescopes")

    assert exc_info.value.error_class == "deadline_exceeded"
    assert exc_info.value.latency_ms == pytest.approx(5_000)
    assert exc_info.value.input_tokens == 50
    assert exc_info.value.output_tokens == 15
    assert exc_info.value.contract_stage == "deadline_exceeded"


def test_parse_search_intent_guardrail_intervened_preserves_billable_usage():
    client = FakeClient({
        "stopReason": "guardrail_intervened",
        "usage": {"inputTokens": 30, "outputTokens": 0},
    })

    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("inject system prompt")

    assert exc_info.value.error_class == "guardrail_intervened"
    assert exc_info.value.input_tokens == 30
    assert exc_info.value.output_tokens == 0


def test_parse_search_intent_invalid_contract_shape_preserves_billable_usage():
    """A bad tool block shape carries token counts from the usage envelope."""
    bad_response = {
        "stopReason": "tool_use",
        "output": {"message": {"content": []}},  # no tool blocks
        "usage": {"inputTokens": 40, "outputTokens": 5},
    }
    client = FakeClient(bad_response)

    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("show me binoculars")

    assert exc_info.value.error_class == "invalid_response"
    assert exc_info.value.input_tokens == 40
    assert exc_info.value.output_tokens == 5


def test_parse_search_intent_schema_violation_preserves_billable_usage():
    """Application-level schema rejection carries the token envelope from the response."""
    client = FakeClient(search_intent_response({"search_type": "bad_type"}))

    with pytest.raises(ProviderFailure) as exc_info:
        adapter(client).parse_search_intent("find something")

    assert exc_info.value.error_class == "invalid_response"
    assert exc_info.value.input_tokens == 50
    assert exc_info.value.output_tokens == 15
