import time

import pytest

from response_cache import ResponseCache, normalize_exact_request, source_fingerprint


def test_normalization_is_exact_and_does_not_remove_punctuation():
    assert normalize_exact_request("  HỎI   GÌ?  ") == "hỏi gì?"
    assert normalize_exact_request("Hỏi gì") != normalize_exact_request("Hỏi gì?")


def test_key_contains_no_raw_user_question_or_session():
    cache = ResponseCache(secret="test-secret")
    identity = cache.identity(
        surface="product_qa",
        user_id="alice@example.com",
        product_id="p1",
        request="Is this good?",
        dependency_class="explicit_product_qa_v1",
        model_id="model",
        prompt_version="prompt-v1",
        guardrail_version="guardrail-v1",
        response_schema_version="response-v1",
        fingerprint="source-fingerprint",
    )

    assert "alice" not in identity.key
    assert "Is this good" not in identity.key
    assert "session" not in identity.key


def test_cold_hit_cross_user_and_source_change():
    cache = ResponseCache(secret="test-secret", ttl_seconds=10)

    def identity(user, fingerprint):
        return cache.identity(
            surface="product_qa",
            user_id=user,
            product_id="p1",
            request="Is this good?",
            dependency_class="explicit_product_qa_v1",
            model_id="model",
            prompt_version="prompt-v1",
            guardrail_version="guardrail-v1",
            response_schema_version="response-v1",
            fingerprint=fingerprint,
        )

    first = identity("user-a", "source-a")
    assert cache.lookup(first).reason == "cold"
    assert cache.write(first, {"response": "yes", "outcome": "answered"})
    assert cache.lookup(first).status == "hit"
    assert cache.lookup(identity("user-b", "source-a")).status == "miss"
    changed = cache.lookup(identity("user-a", "source-b"))
    assert changed.status == "miss"
    assert changed.reason == "source_changed"


def test_ttl_expiry_is_reported():
    clock = [1_000.0]
    cache = ResponseCache(
        secret="test-secret",
        ttl_seconds=2,
        clock=lambda: clock[0],
    )
    identity = cache.identity(
        surface="product_qa",
        user_id="user-a",
        product_id="p1",
        request="question",
        dependency_class="explicit_product_qa_v1",
        model_id="model",
        prompt_version="prompt-v1",
        guardrail_version="guardrail-v1",
        response_schema_version="response-v1",
        fingerprint="source-a",
    )
    cache.write(identity, {"response": "yes"})
    clock[0] += 3

    lookup = cache.lookup(identity)
    assert lookup.status == "miss"
    assert lookup.reason == "expired"


def test_source_fingerprint_excludes_username_and_is_order_stable():
    product = {
        "id": "p1",
        "name": "Scope",
        "description": "Clear",
        "categories": ["telescopes"],
    }
    rows_a = [
        (2, "bob", "Heavy mount", 2),
        (1, "alice", "Clear moon", 5),
    ]
    rows_b = [
        (1, "different-user", "Clear moon", 5),
        (2, "another-user", "Heavy mount", 2),
    ]
    assert source_fingerprint(product, rows_a) == source_fingerprint(product, rows_b)


def test_lock_limits_duplicate_fill():
    cache = ResponseCache(secret="test-secret")
    identity = cache.identity(
        surface="product_qa",
        user_id="user-a",
        product_id="p1",
        request="question",
        dependency_class="explicit_product_qa_v1",
        model_id="model",
        prompt_version="prompt-v1",
        guardrail_version="guardrail-v1",
        response_schema_version="response-v1",
        fingerprint="source-a",
    )
    token = cache.acquire_lock(identity)
    assert token
    assert cache.acquire_lock(identity) is None
    cache.release_lock(identity, token)
    assert cache.acquire_lock(identity)


def test_lock_wait_must_be_shorter_than_lock_ttl():
    with pytest.raises(ValueError, match="shorter than lock TTL"):
        ResponseCache(
            secret="test-secret",
            lock_ttl_seconds=1,
            lock_wait_seconds=1,
        )


def test_model_prompt_guardrail_and_schema_versions_change_identity():
    cache = ResponseCache(secret="test-secret")
    common = {
        "surface": "product_qa",
        "user_id": "user-a",
        "product_id": "p1",
        "request": "question",
        "dependency_class": "explicit_product_qa_v1",
        "model_id": "model-v1",
        "prompt_version": "prompt-v1",
        "guardrail_version": "guardrail-v1",
        "response_schema_version": "response-v1",
        "fingerprint": "source-a",
    }
    baseline = cache.identity(**common).key
    variants = []
    for field, value in (
        ("model_id", "model-v2"),
        ("prompt_version", "prompt-v2"),
        ("guardrail_version", "guardrail-v2"),
        ("response_schema_version", "response-v2"),
    ):
        changed = dict(common)
        changed[field] = value
        variants.append(cache.identity(**changed).key)

    assert len({baseline, *variants}) == 5
