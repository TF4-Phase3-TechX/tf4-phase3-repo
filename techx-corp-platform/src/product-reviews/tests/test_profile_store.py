from profile_store import PROFILE_TTL_SECONDS, ProfileStore, parse_memory_command


def test_profile_requires_explicit_consent():
    assert parse_memory_command("I like telescopes") is None
    command = parse_memory_command(
        "Please remember my preferred category is telescopes"
    )
    assert command.action == "remember"
    assert command.values == {"preferred_category": "telescopes"}


def test_budget_is_stored_as_integer_cents():
    command = parse_memory_command("Hãy nhớ ngân sách tối đa là $123.45")
    assert command.action == "remember"
    assert command.values["max_budget_usd_cents"] == 12_345


def test_pii_memory_command_is_rejected_before_persistence():
    command = parse_memory_command(
        "Remember my preferred category is telescopes and email me at a@b.com"
    )
    assert command.action == "reject"


def test_profile_is_cross_session_but_isolated_by_user():
    store = ProfileStore(secret="test-secret")
    result = store.write("user-a", {"preferred_category": "telescopes"})
    assert result.status == "stored"
    assert store.read("user-a").profile["preferred_category"] == "telescopes"
    assert store.read("user-b").status == "not_found"


def test_read_does_not_refresh_retention_and_expiry_is_enforced():
    clock = [1_000.0]
    store = ProfileStore(secret="test-secret", clock=lambda: clock[0])
    store.write("user-a", {"preferred_category": "telescopes"})
    key = store._key("user-a")
    original_expiry = store._memory[key][0]
    clock[0] += 100
    assert store.read("user-a").status == "recalled"
    assert store._memory[key][0] == original_expiry
    clock[0] = 1_000.0 + PROFILE_TTL_SECONDS + 1
    assert store.read("user-a").status == "not_found"


def test_forget_is_scoped_and_idempotent():
    store = ProfileStore(secret="test-secret")
    store.write("user-a", {"preferred_category": "telescopes"})
    store.write("user-b", {"preferred_category": "books"})
    assert store.forget("user-a").status == "forgotten"
    assert store.read("user-a").status == "not_found"
    assert store.read("user-b").profile["preferred_category"] == "books"


def test_arbitrary_field_is_rejected():
    store = ProfileStore(secret="test-secret")
    result = store.write("user-a", {"raw_utterance": "secret"})
    assert result.status == "rejected"


def test_allow_list_values_are_validated_at_persistence_boundary():
    store = ProfileStore(secret="test-secret")
    assert store.write("user-a", {"preferred_category": ""}).status == "rejected"
    assert (
        store.write("user-a", {"max_budget_usd_cents": 10.5}).status
        == "rejected"
    )
    assert (
        store.write("user-a", {"max_budget_usd_cents": -1}).status
        == "rejected"
    )


def test_explicit_unsupported_personal_field_rejects_whole_command():
    command = parse_memory_command(
        "Remember my name is Alice and my preferred category is telescopes"
    )
    assert command.action == "reject"


def test_profile_key_contains_no_raw_user_id():
    store = ProfileStore(secret="test-secret")
    key = store._key("alice@example.com")
    assert "alice" not in key
    assert "example.com" not in key


def test_profile_read_write_and_delete_fail_closed_on_store_errors():
    class BrokenStore:
        def get(self, *_args):
            raise OSError("read unavailable")

        def setex(self, *_args):
            raise OSError("write unavailable")

        def delete(self, *_args):
            raise OSError("delete unavailable")

    store = ProfileStore(redis_client=BrokenStore(), secret="test-secret")
    assert store.read("user-a").status == "error"
    assert (
        store.write("user-a", {"preferred_category": "telescopes"}).status
        == "error"
    )
    assert store.forget("user-a").status == "error"
