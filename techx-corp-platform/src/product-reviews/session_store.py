#!/usr/bin/python

"""Server-owned Copilot sessions and single-use cart proposals."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
import time
from typing import Any


logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS = 5
MAX_HISTORY_TOKENS = 2_000
MAX_HISTORY_CHARS = MAX_HISTORY_TOKENS * 4
MAX_TURN_CHARS = MAX_HISTORY_CHARS // (MAX_HISTORY_TURNS * 2)
SESSION_TTL_SECONDS = 1_800
PROPOSAL_TTL_SECONDS = 300
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


class SessionStoreUnavailable(RuntimeError):
    """Raised when the production session safety boundary is unavailable."""


def _validated_id(value: str, field: str, *, allow_guest: bool = False) -> str:
    cleaned = (value or "").strip()
    if allow_guest and cleaned == "guest":
        return cleaned
    if not cleaned or not _ID_RE.fullmatch(cleaned):
        raise ValueError(f"invalid {field}")
    return cleaned


class SessionStore:
    def __init__(self, redis_client: Any | None = None) -> None:
        self._lock = threading.Lock()
        self._memory_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
        self._memory_proposals: dict[str, tuple[float, dict[str, Any]]] = {}
        self._required = os.getenv("APP_ENV", "local").strip().lower() in {"staging", "production"}
        self._valkey_client: Any = redis_client
        if redis_client is None:
            self._init_valkey()

    def _init_valkey(self) -> None:
        address = os.getenv("VALKEY_ADDR", "valkey-cart:6379")
        host, _, raw_port = address.rpartition(":")
        if not host:
            host, raw_port = address, "6379"
        try:
            import redis

            client = redis.Redis(
                host=host,
                port=int(raw_port),
                password=os.getenv("VALKEY_PASSWORD") or None,
                ssl=os.getenv("VALKEY_TLS", "false").lower() == "true",
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
                decode_responses=True,
            )
            client.ping()
            self._valkey_client = client
            logger.info("SessionStore initialized with Valkey/Redis at %s", address)
        except Exception as exc:
            self._valkey_client = None
            if self._required:
                raise SessionStoreUnavailable("Valkey is required for Copilot sessions in staging/production") from exc
            logger.info("SessionStore Valkey unavailable in local mode (%s); using memory", exc)

    def _history_key(self, user_id: str, session_id: str) -> str:
        user = _validated_id(user_id or "guest", "user_id", allow_guest=True)
        session = _validated_id(session_id, "session_id")
        return f"copilot:session:{user}:{session}"

    def _handle_runtime_error(self, operation: str, exc: Exception) -> None:
        logger.warning("Valkey %s error: %s", operation, exc)
        if self._required:
            raise SessionStoreUnavailable(f"Valkey {operation} failed") from exc

    def get_history(self, user_id: str, session_id: str) -> list[dict[str, str]]:
        if not session_id:
            return []
        key = self._history_key(user_id, session_id)

        if self._valkey_client is not None:
            try:
                rows = self._valkey_client.lrange(key, 0, -1)
                return [json.loads(row) for row in rows]
            except Exception as exc:
                self._handle_runtime_error("read", exc)

        with self._lock:
            now = time.time()
            cached = self._memory_cache.get(key)
            if cached and now - cached[0] <= SESSION_TTL_SECONDS:
                return list(cached[1])
            self._memory_cache.pop(key, None)
            return []

    def append_turn(self, user_id: str, session_id: str, role: str, content: str) -> None:
        if not session_id or not content:
            return
        if role not in {"user", "assistant"}:
            raise ValueError("invalid conversation role")
        key = self._history_key(user_id, session_id)
        turn = {"role": role, "content": str(content)[:MAX_TURN_CHARS]}

        if self._valkey_client is not None:
            try:
                pipe = self._valkey_client.pipeline(transaction=True)
                pipe.rpush(key, json.dumps(turn, ensure_ascii=False))
                pipe.ltrim(key, -(MAX_HISTORY_TURNS * 2), -1)
                pipe.expire(key, SESSION_TTL_SECONDS)
                pipe.execute()
                return
            except Exception as exc:
                self._handle_runtime_error("append", exc)

        with self._lock:
            history = list(self._memory_cache.get(key, (0, []))[1])
            history.append(turn)
            history = history[-(MAX_HISTORY_TURNS * 2):]
            while history and sum(len(item["content"]) for item in history) > MAX_HISTORY_CHARS:
                history.pop(0)
            self._memory_cache[key] = (time.time(), history)

    def set_last_search_products(self, user_id: str, session_id: str, products: list[dict]) -> None:
        if not session_id:
            return
        key = self._history_key(user_id, session_id) + ":products"
        serialized = json.dumps(products, ensure_ascii=False)
        if self._valkey_client is not None:
            try:
                self._valkey_client.setex(key, SESSION_TTL_SECONDS, serialized)
                return
            except Exception as exc:
                logger.warning("Valkey write error for key %s: %s", key, exc)
        with self._lock:
            self._memory_cache[key] = (time.time(), products)

    def get_last_search_products(self, user_id: str, session_id: str) -> list[dict]:
        if not session_id:
            return []
        key = self._history_key(user_id, session_id) + ":products"
        if self._valkey_client is not None:
            try:
                raw_data = self._valkey_client.get(key)
                if raw_data:
                    return json.loads(raw_data.decode("utf-8") if isinstance(raw_data, bytes) else raw_data)
            except Exception as exc:
                logger.warning("Valkey read error for key %s: %s", key, exc)
        with self._lock:
            now = time.time()
            if key in self._memory_cache:
                timestamp, prods = self._memory_cache[key]
                if now - timestamp <= SESSION_TTL_SECONDS:
                    return list(prods)
        return []
    def create_cart_proposal(
        self,
        user_id: str,
        session_id: str,
        product_id: str,
        product_name: str,
        quantity: int,
    ) -> str:
        user = _validated_id(user_id or "guest", "user_id", allow_guest=True)
        session = _validated_id(session_id, "session_id")
        token = secrets.token_urlsafe(32)
        payload = {
            "user_id": user,
            "session_id": session,
            "product_id": str(product_id)[:128],
            "product_name": str(product_name)[:256],
            "quantity": max(1, min(int(quantity), 10)),
        }
        key = f"copilot:proposal:{token}"

        if self._valkey_client is not None:
            try:
                created = self._valkey_client.set(
                    key,
                    json.dumps(payload, ensure_ascii=False),
                    ex=PROPOSAL_TTL_SECONDS,
                    nx=True,
                )
                if not created:
                    raise RuntimeError("proposal token collision")
                return token
            except Exception as exc:
                self._handle_runtime_error("proposal-create", exc)

        with self._lock:
            self._memory_proposals[token] = (time.time(), payload)
        return token

    def consume_cart_proposal(self, user_id: str, session_id: str, token: str) -> dict[str, Any] | None:
        user = _validated_id(user_id or "guest", "user_id", allow_guest=True)
        session = _validated_id(session_id, "session_id")
        cleaned_token = (token or "").strip()
        if not _TOKEN_RE.fullmatch(cleaned_token):
            return None
        key = f"copilot:proposal:{cleaned_token}"

        if self._valkey_client is not None:
            script = """
local raw = redis.call('GET', KEYS[1])
if not raw then return nil end
local value = cjson.decode(raw)
if value['user_id'] ~= ARGV[1] or value['session_id'] ~= ARGV[2] then return nil end
redis.call('DEL', KEYS[1])
return raw
"""
            try:
                raw = self._valkey_client.eval(script, 1, key, user, session)
                return json.loads(raw) if raw else None
            except Exception as exc:
                self._handle_runtime_error("proposal-consume", exc)

        with self._lock:
            cached = self._memory_proposals.get(cleaned_token)
            if not cached or time.time() - cached[0] > PROPOSAL_TTL_SECONDS:
                self._memory_proposals.pop(cleaned_token, None)
                return None
            payload = cached[1]
            if payload["user_id"] != user or payload["session_id"] != session:
                return None
            self._memory_proposals.pop(cleaned_token, None)
            return dict(payload)


session_store = SessionStore()
