import pytest

import session_store as store_module
from session_store import MAX_HISTORY_TURNS, PROPOSAL_TTL_SECONDS, SessionStore


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
