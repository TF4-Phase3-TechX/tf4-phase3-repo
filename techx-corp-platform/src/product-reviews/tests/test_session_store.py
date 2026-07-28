import pytest

import session_store as store_module
from session_store import (
    MAX_HISTORY_EXCHANGES,
    MAX_HISTORY_MESSAGES,
    MAX_HISTORY_TURNS,
    PROPOSAL_TTL_SECONDS,
    SESSION_TTL_SECONDS,
    SessionStore,
    SessionStoreUnavailable,
)


def make_store(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    store = SessionStore(redis_client=False)
    store._valkey_client = None
    return store


def test_history_is_scoped_and_bounded(monkeypatch):
    store = make_store(monkeypatch)
    for index in range(MAX_HISTORY_TURNS * 2 + 4):
        store.append_turn("user-1", "session-1", "user", f"turn-{index}")

    history = store.get_history("user-1", "session-1")
    assert len(history) == MAX_HISTORY_TURNS * 2
    assert history[0]["content"] == "turn-4"
    assert store.get_history("user-2", "session-1") == []


def test_history_keeps_five_complete_exchanges(monkeypatch):
    store = make_store(monkeypatch)
    for index in range(MAX_HISTORY_EXCHANGES + 2):
        store.append_exchange(
            "user-1",
            "session-1",
            f"user-{index}",
            f"assistant-{index}",
        )

    history = store.get_history("user-1", "session-1")
    assert len(history) == MAX_HISTORY_MESSAGES == 10
    assert history[0] == {"role": "user", "content": "user-2"}
    assert history[-1] == {"role": "assistant", "content": "assistant-6"}
    assert [row["role"] for row in history] == ["user", "assistant"] * 5


def test_token_trim_never_keeps_half_an_exchange(monkeypatch):
    store = make_store(monkeypatch)
    for index in range(8):
        store.append_exchange(
            "user-1",
            "session-1",
            f"user-{index}-" + ("x" * 700),
            f"assistant-{index}-" + ("y" * 700),
        )
    history = store.get_history("user-1", "session-1")
    assert len(history) % 2 == 0
    assert [row["role"] for row in history] == ["user", "assistant"] * (
        len(history) // 2
    )


def test_last_search_products_are_scoped_by_user_and_session(monkeypatch):
    store = make_store(monkeypatch)
    store.set_last_search_products("user-1", "session-1", [{"id": "product-1"}])
    store.set_last_search_products("user-2", "session-1", [{"id": "product-2"}])

    assert store.get_last_search_products("user-1", "session-1") == [{"id": "product-1"}]
    assert store.get_last_search_products("user-2", "session-1") == [{"id": "product-2"}]
    assert store.get_last_search_products("user-1", "session-2") == []


def test_local_last_search_products_expire_and_are_copied(monkeypatch):
    store = make_store(monkeypatch)
    clock = [1_000.0]
    monkeypatch.setattr(store_module.time, "time", lambda: clock[0])
    products = [{"id": "product-1", "categories": ["telescopes"]}]

    store.set_last_search_products("user-1", "session-1", products)
    products[0]["id"] = "mutated-by-caller"
    fetched = store.get_last_search_products("user-1", "session-1")
    fetched[0]["categories"].append("mutated")

    assert store.get_last_search_products("user-1", "session-1") == [
        {"id": "product-1", "categories": ["telescopes"]}
    ]

    clock[0] += SESSION_TTL_SECONDS + 1
    assert store.get_last_search_products("user-1", "session-1") == []


class FakeValkey:
    def __init__(self):
        self.values = {}
        self.setex_calls = []

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)


def test_valkey_last_search_products_use_scoped_key_and_ttl(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    valkey = FakeValkey()
    store = SessionStore(redis_client=valkey)

    store.set_last_search_products("user-1", "session-1", [{"id": "product-1"}])

    assert valkey.setex_calls == [
        (
            "copilot:session:user-1:session-1:products",
            SESSION_TTL_SECONDS,
            '[{"id": "product-1"}]',
        )
    ]
    assert store.get_last_search_products("user-1", "session-1") == [{"id": "product-1"}]
    assert store.get_last_search_products("user-2", "session-1") == []


def test_required_valkey_failure_does_not_fall_back_to_process_memory(monkeypatch):
    class BrokenValkey:
        def setex(self, *_args):
            raise OSError("unavailable")

    monkeypatch.setenv("APP_ENV", "production")
    store = SessionStore(redis_client=BrokenValkey())

    with pytest.raises(SessionStoreUnavailable):
        store.set_last_search_products("user-1", "session-1", [{"id": "product-1"}])
    assert store._memory_last_search_products == {}


def test_invalid_session_id_is_rejected(monkeypatch):
    store = make_store(monkeypatch)
    with pytest.raises(ValueError):
        store.append_turn("user-1", "../shared", "user", "hello")


def test_cart_proposal_is_bound_and_single_use(monkeypatch):
    store = make_store(monkeypatch)
    token = store.create_cart_proposal("user-1", "session-1", "product-1", "Scope", 2)

    assert store.consume_cart_proposal("user-2", "session-1", token) is None
    assert store.consume_cart_proposal("user-1", "session-2", token) is None
    proposal = store.consume_cart_proposal("user-1", "session-1", token)
    assert proposal == {
        "user_id": "user-1",
        "session_id": "session-1",
        "product_id": "product-1",
        "product_name": "Scope",
        "quantity": 2,
    }
    assert store.consume_cart_proposal("user-1", "session-1", token) is None


def test_cart_proposal_expires(monkeypatch):
    store = make_store(monkeypatch)
    now = 1_000.0
    monkeypatch.setattr(store_module.time, "time", lambda: now)
    token = store.create_cart_proposal("user-1", "session-1", "product-1", "Scope", 1)
    now += PROPOSAL_TTL_SECONDS + 1

    assert store.consume_cart_proposal("user-1", "session-1", token) is None
