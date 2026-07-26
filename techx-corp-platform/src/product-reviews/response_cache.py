#!/usr/bin/python

"""Exact, user-scoped AI response cache with source-fingerprint invalidation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import threading
import time
import unicodedata
from typing import Any


CACHE_SCHEMA_VERSION = "v1"
RESPONSE_SCHEMA_VERSION = "grounded-response-v1"
PRODUCT_QA_PROMPT_VERSION = "product-qa-v1"
COPILOT_REVIEW_PROMPT_VERSION = "deterministic-review-v1"
DEFAULT_CACHE_TTL_SECONDS = 300
DEFAULT_LOCK_TTL_SECONDS = 5
DEFAULT_LOCK_WAIT_SECONDS = 0.2


def normalize_exact_request(value: Any) -> str:
    """Apply only the equivalences approved for exact-cache identity."""
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(normalized.strip().split()).casefold()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def source_fingerprint(product: Any, reviews: list[Any]) -> str:
    """Hash only catalog/review fields that actually cross the AI boundary."""
    if isinstance(product, dict):
        product_payload = {
            "id": str(product.get("id", "")),
            "name": str(product.get("name", "")),
            "description": str(product.get("description", "")),
            "categories": [str(value) for value in product.get("categories", [])],
        }
    else:
        product_payload = {
            "id": str(getattr(product, "id", "")),
            "name": str(getattr(product, "name", "")),
            "description": str(getattr(product, "description", "")),
            "categories": [str(value) for value in getattr(product, "categories", [])],
        }

    review_payload = []
    for row in reviews:
        if isinstance(row, dict):
            review_payload.append(
                {
                    "id": int(row.get("review_id", row.get("id", 0))),
                    "description": str(row.get("description", "")),
                    "score": str(row.get("score", "")),
                }
            )
        else:
            review_payload.append(
                {
                    "id": int(row[0]),
                    "description": str(row[2]),
                    "score": str(row[3]),
                }
            )
    review_payload.sort(key=lambda item: item["id"])
    canonical = _canonical_json(
        {"product": product_payload, "reviews": review_payload}
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheIdentity:
    key: str
    marker_key: str
    source_fingerprint: str


@dataclass(frozen=True)
class CacheLookup:
    value: dict[str, Any] | None
    status: str
    reason: str
    lookup_latency_ms: float


class ResponseCache:
    """Valkey-backed cache; local memory exists only for tests/development."""

    def __init__(
        self,
        redis_client: Any | None = None,
        *,
        secret: str | None = None,
        ttl_seconds: int | None = None,
        clock: Any = time.time,
    ) -> None:
        app_env = os.getenv("APP_ENV", "local").strip().lower()
        configured_secret = secret or os.getenv("AI_CACHE_HMAC_SECRET")
        if not configured_secret and app_env in {"staging", "production"}:
            raise RuntimeError("AI_CACHE_HMAC_SECRET is required outside local development")
        self._secret = (configured_secret or "local-development-only").encode("utf-8")
        self._redis = redis_client
        self._ttl = int(
            ttl_seconds
            if ttl_seconds is not None
            else os.getenv("AI_RESPONSE_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS)
        )
        self._clock = clock
        self._lock = threading.Lock()
        self._memory: dict[str, tuple[float, str]] = {}

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def _digest(self, value: str, *, keyed: bool = False) -> str:
        encoded = value.encode("utf-8")
        if keyed:
            return hmac.new(self._secret, encoded, hashlib.sha256).hexdigest()
        return hashlib.sha256(encoded).hexdigest()

    def identity(
        self,
        *,
        surface: str,
        user_id: str,
        product_id: str,
        request: str,
        dependency_class: str,
        model_id: str,
        prompt_version: str,
        guardrail_version: str,
        response_schema_version: str,
        fingerprint: str,
    ) -> CacheIdentity:
        user_digest = self._digest(str(user_id or "guest"), keyed=True)
        request_digest = self._digest(normalize_exact_request(request))
        config_digest = self._digest(
            _canonical_json(
                {
                    "model": model_id,
                    "prompt": prompt_version,
                    "guardrail": guardrail_version,
                    "response_schema": response_schema_version,
                }
            )
        )
        base = (
            f"ai:response:{CACHE_SCHEMA_VERSION}:{surface}:{user_digest}:"
            f"{product_id}:{request_digest}:{dependency_class}:{config_digest}"
        )
        return CacheIdentity(
            key=f"{base}:{fingerprint}",
            marker_key=f"{base}:source",
            source_fingerprint=fingerprint,
        )

    @staticmethod
    def _decode(raw: Any) -> str:
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)

    def lookup(self, identity: CacheIdentity) -> CacheLookup:
        started = time.monotonic()
        try:
            if self._redis is not None:
                raw = self._redis.get(identity.key)
                marker = self._redis.get(identity.marker_key)
            else:
                with self._lock:
                    now = self._clock()
                    cached = self._memory.get(identity.key)
                    marker_cached = self._memory.get(identity.marker_key)
                    if cached and cached[0] <= now:
                        self._memory.pop(identity.key, None)
                        cached = None
                    if marker_cached and marker_cached[0] <= now:
                        self._memory.pop(identity.marker_key, None)
                        marker_cached = None
                    raw = cached[1] if cached else None
                    marker = marker_cached[1] if marker_cached else None
            elapsed = (time.monotonic() - started) * 1_000
            if raw:
                value = json.loads(self._decode(raw))
                if not isinstance(value, dict):
                    raise ValueError("cache payload must be an object")
                return CacheLookup(value, "hit", "hit", elapsed)
            if marker:
                marker_value = self._decode(marker)
                reason = (
                    "source_changed"
                    if marker_value != identity.source_fingerprint
                    else "expired"
                )
            else:
                reason = "cold"
            return CacheLookup(None, "miss", reason, elapsed)
        except Exception:
            return CacheLookup(
                None,
                "miss",
                "cache_error",
                (time.monotonic() - started) * 1_000,
            )

    def write(self, identity: CacheIdentity, value: dict[str, Any]) -> bool:
        serialized = _canonical_json(value)
        try:
            if self._redis is not None:
                pipe = self._redis.pipeline(transaction=True)
                pipe.setex(identity.key, self._ttl, serialized)
                pipe.setex(
                    identity.marker_key,
                    self._ttl * 2,
                    identity.source_fingerprint,
                )
                pipe.execute()
            else:
                now = self._clock()
                with self._lock:
                    self._memory[identity.key] = (now + self._ttl, serialized)
                    self._memory[identity.marker_key] = (
                        now + self._ttl * 2,
                        identity.source_fingerprint,
                    )
            return True
        except Exception:
            return False

    def acquire_lock(self, identity: CacheIdentity) -> str | None:
        token = self._digest(
            f"{identity.key}:{threading.get_ident()}:{time.monotonic()}", keyed=True
        )
        lock_key = f"{identity.key}:lock"
        try:
            if self._redis is not None:
                acquired = self._redis.set(
                    lock_key,
                    token,
                    ex=DEFAULT_LOCK_TTL_SECONDS,
                    nx=True,
                )
                return token if acquired else None
            now = self._clock()
            with self._lock:
                cached = self._memory.get(lock_key)
                if cached and cached[0] > now:
                    return None
                self._memory[lock_key] = (now + DEFAULT_LOCK_TTL_SECONDS, token)
                return token
        except Exception:
            return None

    def release_lock(self, identity: CacheIdentity, token: str | None) -> None:
        if not token:
            return
        lock_key = f"{identity.key}:lock"
        try:
            if self._redis is not None:
                script = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""
                self._redis.eval(script, 1, lock_key, token)
                return
            with self._lock:
                cached = self._memory.get(lock_key)
                if cached and cached[1] == token:
                    self._memory.pop(lock_key, None)
        except Exception:
            return

    def wait_for_fill(
        self,
        identity: CacheIdentity,
        timeout_seconds: float = DEFAULT_LOCK_WAIT_SECONDS,
    ) -> CacheLookup:
        deadline = time.monotonic() + timeout_seconds
        last = CacheLookup(None, "miss", "lock_timeout", 0)
        while time.monotonic() < deadline:
            time.sleep(0.01)
            last = self.lookup(identity)
            if last.status == "hit" or last.reason == "cache_error":
                return last
        return CacheLookup(None, "miss", "lock_timeout", last.lookup_latency_ms)
