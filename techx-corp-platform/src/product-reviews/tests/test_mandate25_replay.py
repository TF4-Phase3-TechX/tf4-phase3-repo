import json
from pathlib import Path

import pytest

from tests.eval_mandate25 import replay
from safety import INSUFFICIENT_RESPONSE, UNAVAILABLE_RESPONSE


class Response:
    def __init__(self, text, has_action=False):
        self.response = text
        self._has_action = has_action

    def HasField(self, name):
        return name == "action_proposal" and self._has_action


class Stub:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def AskProductAIAssistant(self, _request, timeout):
        assert timeout == 6
        self.calls += 1
        return self.response


def case():
    return {
        "case_id": "case-1",
        "product_id": "product-1",
        "question": "safe question",
        "user_id": "user-1",
        "session_id": "session-1",
    }


@pytest.mark.parametrize(
    ("response_text", "outcome"),
    [
        (UNAVAILABLE_RESPONSE, "unavailable"),
        (INSUFFICIENT_RESPONSE, "insufficient"),
        ("grounded answer", "answered"),
    ],
)
def test_replay_records_honest_outcome_and_bounded_status(
    response_text,
    outcome,
):
    stub = Stub(Response(response_text))
    status_call = lambda *_args, **_kwargs: {
        "fault": {"mode": "timeout", "seconds_remaining": 10},
        "resilience": {
            "circuit_state": "open",
            "last_provider_outcome": "error",
            "last_provider_error": "timeout",
        },
    }

    rows = replay.replay(
        [case()],
        stub=stub,
        status_call=status_call,
        repeat=2,
        timeout_seconds=6,
    )

    assert stub.calls == 2
    assert [row["outcome"] for row in rows] == [outcome, outcome]
    assert all(row["resilience"]["circuit_state"] == "open" for row in rows)
    assert all("question" not in row for row in rows)


def test_read_cases_requires_external_identity_and_session(tmp_path: Path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps({"case_id": "missing-fields"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="required fields"):
        replay.read_cases(path)
