import os

os.environ.setdefault("DB_CONNECTION_STRING", "postgresql://unused:unused@127.0.0.1:1/unused")

import product_reviews_server as server
from session_store import SessionStore


class RecordingCartStub:
    def __init__(self):
        self.requests = []

    def AddItem(self, request, timeout):
        self.requests.append((request, timeout))


def local_store(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    store = SessionStore(redis_client=False)
    store._valkey_client = None
    return store


def test_confirmation_applies_server_stored_values_once(monkeypatch):
    store = local_store(monkeypatch)
    cart = RecordingCartStub()
    monkeypatch.setattr(server, "session_store", store)
    monkeypatch.setattr(server, "cart_stub", cart)
    token = store.create_cart_proposal("user-1", "session-1", "product-1", "Scope", 2)

    first = server.confirm_cart_action("user-1", "session-1", token)
    replay = server.confirm_cart_action("user-1", "session-1", token)

    assert first.applied is True
    assert replay.applied is False
    assert replay.outcome == "invalid_or_expired"
    assert len(cart.requests) == 1
    request, timeout = cart.requests[0]
    assert request.user_id == "user-1"
    assert request.item.product_id == "product-1"
    assert request.item.quantity == 2
    assert timeout == 2.0


def test_cross_session_attempt_does_not_consume_valid_proposal(monkeypatch):
    store = local_store(monkeypatch)
    cart = RecordingCartStub()
    monkeypatch.setattr(server, "session_store", store)
    monkeypatch.setattr(server, "cart_stub", cart)
    token = store.create_cart_proposal("user-1", "session-1", "product-1", "Scope", 1)

    wrong_session = server.confirm_cart_action("user-1", "session-2", token)
    owner = server.confirm_cart_action("user-1", "session-1", token)

    assert wrong_session.applied is False
    assert owner.applied is True
    assert len(cart.requests) == 1
