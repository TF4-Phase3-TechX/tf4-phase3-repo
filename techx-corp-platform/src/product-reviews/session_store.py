#!/usr/bin/python

"""Server-side session store for Copilot multi-turn conversation history.

In staging/production (EKS), Valkey/Redis is used to guarantee multi-pod state consistency.
In local single-instance environments, an in-memory TTL cache acts as a fallback.
"""

from __future__ import annotations

import json
import logging
import os
import time
import threading
from typing import Any

logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS = 5
MAX_HISTORY_TOKENS = 2_000
SESSION_TTL_SECONDS = 1800  # 30 minutes


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._memory_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
        self._valkey_client: Any = None
        self._init_valkey()

    def _init_valkey(self) -> None:
        valkey_host = os.getenv("VALKEY_HOST", "valkey")
        valkey_port = int(os.getenv("VALKEY_PORT", "6379"))
        try:
            import redis
            client = redis.Redis(
                host=valkey_host,
                port=valkey_port,
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
            )
            client.ping()
            self._valkey_client = client
            logger.info("SessionStore initialized with Valkey/Redis at %s:%d", valkey_host, valkey_port)
        except Exception as exc:
            logger.info("SessionStore Valkey connection unavailable (%s); using in-memory TTL fallback", exc)
            self._valkey_client = None

    def _make_key(self, user_id: str, session_id: str) -> str:
        clean_user = (user_id or "guest").strip()
        clean_session = (session_id or "default").strip()
        return f"session:{clean_user}:{clean_session}"

    def get_history(self, user_id: str, session_id: str) -> list[dict[str, str]]:
        if not session_id:
            return []
        key = self._make_key(user_id, session_id)

        if self._valkey_client is not None:
            try:
                raw_data = self._valkey_client.get(key)
                if raw_data:
                    return json.loads(raw_data.decode("utf-8"))
                return []
            except Exception as exc:
                logger.warning("Valkey read error for key %s: %s", key, exc)

        with self._lock:
            now = time.time()
            if key in self._memory_cache:
                timestamp, turns = self._memory_cache[key]
                if now - timestamp <= SESSION_TTL_SECONDS:
                    return list(turns)
                else:
                    del self._memory_cache[key]
            return []

    def append_turn(self, user_id: str, session_id: str, role: str, content: str) -> None:
        if not session_id or not content:
            return
        key = self._make_key(user_id, session_id)
        history = self.get_history(user_id, session_id)

        # Append turn and bound to MAX_HISTORY_TURNS
        history.append({"role": role, "content": str(content)[:1000]})
        if len(history) > MAX_HISTORY_TURNS * 2:
            history = history[-(MAX_HISTORY_TURNS * 2):]

        if self._valkey_client is not None:
            try:
                serialized = json.dumps(history, ensure_ascii=False)
                self._valkey_client.setex(key, SESSION_TTL_SECONDS, serialized)
                return
            except Exception as exc:
                logger.warning("Valkey write error for key %s: %s", key, exc)

        with self._lock:
            self._memory_cache[key] = (time.time(), history)

    def set_last_search_products(self, user_id: str, session_id: str, products: list[dict]) -> None:
        if not session_id:
            return
        key = self._make_key(user_id, session_id) + ":products"
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
        key = self._make_key(user_id, session_id) + ":products"
        if self._valkey_client is not None:
            try:
                raw_data = self._valkey_client.get(key)
                if raw_data:
                    return json.loads(raw_data.decode("utf-8"))
            except Exception as exc:
                logger.warning("Valkey read error for key %s: %s", key, exc)
        with self._lock:
            now = time.time()
            if key in self._memory_cache:
                timestamp, prods = self._memory_cache[key]
                if now - timestamp <= SESSION_TTL_SECONDS:
                    return list(prods)
        return []


# Global singleton instance
session_store = SessionStore()
