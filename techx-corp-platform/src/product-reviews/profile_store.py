#!/usr/bin/python

"""Explicit-consent, allow-listed long-term shopping preferences."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import re
import threading
import time
from typing import Any

from safety import contains_pii, normalize_text, MAX_QUESTION_CHARS


PROFILE_SCHEMA_VERSION = "v1"
PROFILE_TTL_SECONDS = 30 * 24 * 60 * 60
ALLOWED_PROFILE_FIELDS = frozenset({"preferred_category", "max_budget_usd_cents"})
_PROFILE_METADATA_FIELDS = frozenset(
    {"schema_version", "consented_at", "updated_at", "expires_at"}
)
_UNSUPPORTED_MEMORY_MARKERS = (
    "my name",
    "my email",
    "my phone",
    "my address",
    "tên tôi",
    "email của tôi",
    "số điện thoại",
    "địa chỉ của tôi",
)
_NEGATED_MEMORY_PATTERNS = (
    r"\b(?:do not|don't|dont|never)\s+(?:remember|save|store)\b",
    r"\b(?:do not|don't|dont|never|not|no)\b"
    r"(?:\s+[\w'-]+){0,6}\s+(?:remember|save|store)\b",
    r"\b(?:not|no)\s+(?:remember|save|store)\b",
    r"(?:đừng|không)\s+(?:nhớ|lưu)\b",
    r"(?:không\s+muốn|đừng\s+có)\s+(?:bạn\s+)?(?:nhớ|lưu)\b",
)


@dataclass(frozen=True)
class MemoryCommand:
    action: str
    values: dict[str, Any]


@dataclass(frozen=True)
class ProfileResult:
    profile: dict[str, Any] | None
    status: str


def parse_memory_command(query: str) -> MemoryCommand | None:
    text = normalize_text(query, MAX_QUESTION_CHARS)
    lowered = text.casefold()
    if contains_pii(text):
        if any(marker in lowered for marker in ("remember", "nhớ", "lưu")):
            return MemoryCommand("reject", {})
        return None

    # Consent must be affirmative. Check refusals before the positive command
    # grammar so phrases such as "don't remember ..." can never persist data.
    if any(re.search(pattern, lowered) for pattern in _NEGATED_MEMORY_PATTERNS):
        return MemoryCommand("reject", {})

    if any(
        marker in lowered
        for marker in (
            "forget my preferences",
            "forget what you remember",
            "delete my preferences",
            "quên sở thích của tôi",
            "xóa điều bạn nhớ",
            "xoá điều bạn nhớ",
            "xóa sở thích",
            "xoá sở thích",
        )
    ):
        return MemoryCommand("forget", {})

    if any(
        marker in lowered
        for marker in (
            "show what you remember",
            "what do you remember about me",
            "show my preferences",
            "bạn nhớ gì về tôi",
            "cho tôi xem sở thích đã lưu",
            "xem sở thích đã lưu",
        )
    ):
        return MemoryCommand("show", {})

    if any(
        marker in lowered
        for marker in (
            "use my preferences",
            "apply my preferences",
            "based on my preferences",
            "theo sở thích của tôi",
            "áp dụng sở thích",
            "dùng sở thích đã nhớ",
        )
    ):
        return MemoryCommand("apply", {})

    # Persist only when the request itself starts with an allow-listed,
    # affirmative command. A loose substring check is unsafe here because
    # refusals such as "I don't want you to remember ..." also contain the
    # word "remember".
    explicit_consent = any(
        re.match(pattern, lowered)
        for pattern in (
            r"^(?:please\s+)?(?:remember|save|store)\b",
            r"^(?:can|could|would)\s+you\s+(?:please\s+)?"
            r"(?:remember|save|store)\b",
            r"^(?:hãy\s+)?nhớ\b",
            r"^lưu\s+sở\s+thích\b",
        )
    )
    if not explicit_consent:
        return None
    if any(marker in lowered for marker in _UNSUPPORTED_MEMORY_MARKERS):
        return MemoryCommand("reject", {})

    values: dict[str, Any] = {}
    category_patterns = (
        r"(?:preferred category|favorite category)\s*(?:is|=|:)?\s*([\w-]+)",
        r"(?:danh mục|loại sản phẩm)\s*(?:yêu thích|ưa thích)?\s*(?:là|=|:)?\s*([\w-]+)",
    )
    for pattern in category_patterns:
        matched = re.search(pattern, lowered, re.IGNORECASE)
        if matched:
            values["preferred_category"] = matched.group(1).strip().casefold()
            break

    budget_patterns = (
        r"(?:max(?:imum)? budget|budget limit)\s*(?:is|=|:)?\s*\$?\s*(\d+(?:\.\d{1,2})?)",
        r"(?:ngân sách tối đa|mức chi tối đa)\s*(?:là|=|:)?\s*\$?\s*(\d+(?:\.\d{1,2})?)",
    )
    for pattern in budget_patterns:
        matched = re.search(pattern, lowered, re.IGNORECASE)
        if matched:
            whole, dot, fraction = matched.group(1).partition(".")
            cents = int(whole) * 100 + int((fraction + "00")[:2] if dot else "00")
            if cents > 0:
                values["max_budget_usd_cents"] = cents
            break

    return MemoryCommand("remember" if values else "reject", values)


class ProfileStore:
    def __init__(
        self,
        redis_client: Any | None = None,
        *,
        secret: str | None = None,
        clock: Any = time.time,
    ) -> None:
        app_env = os.getenv("APP_ENV", "local").strip().lower()
        configured_secret = secret or os.getenv("AI_MEMORY_HMAC_SECRET")
        if not configured_secret and app_env in {"staging", "production"}:
            raise RuntimeError("AI_MEMORY_HMAC_SECRET is required outside local development")
        self._secret = (configured_secret or "local-development-only").encode("utf-8")
        self._redis = redis_client
        self._clock = clock
        self._lock = threading.Lock()
        self._memory: dict[str, tuple[float, str]] = {}

    def _key(self, user_id: str) -> str:
        digest = hmac.new(
            self._secret,
            str(user_id or "guest").encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"ai:profile:{PROFILE_SCHEMA_VERSION}:{digest}"

    @staticmethod
    def _decode(raw: Any) -> str:
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)

    @staticmethod
    def _valid_profile(profile: dict[str, Any]) -> bool:
        if (
            set(profile) - ALLOWED_PROFILE_FIELDS - _PROFILE_METADATA_FIELDS
            or profile.get("schema_version") != PROFILE_SCHEMA_VERSION
        ):
            return False
        category = profile.get("preferred_category")
        budget = profile.get("max_budget_usd_cents")
        if category is not None and (
            not isinstance(category, str) or not category or len(category) > 100
        ):
            return False
        if budget is not None and (
            isinstance(budget, bool)
            or not isinstance(budget, int)
            or budget <= 0
        ):
            return False
        return bool(category is not None or budget is not None)

    def read(self, user_id: str) -> ProfileResult:
        key = self._key(user_id)
        try:
            if self._redis is not None:
                raw = self._redis.get(key)
            else:
                with self._lock:
                    cached = self._memory.get(key)
                    if cached and cached[0] <= self._clock():
                        self._memory.pop(key, None)
                        cached = None
                    raw = cached[1] if cached else None
            if not raw:
                return ProfileResult(None, "not_found")
            profile = json.loads(self._decode(raw))
            if not isinstance(profile, dict) or not self._valid_profile(profile):
                raise ValueError("invalid profile payload")
            return ProfileResult(profile, "recalled")
        except Exception:
            return ProfileResult(None, "error")

    def write(self, user_id: str, values: dict[str, Any]) -> ProfileResult:
        if not values or not set(values).issubset(ALLOWED_PROFILE_FIELDS):
            return ProfileResult(None, "rejected")
        category = values.get("preferred_category")
        if category is not None and (
            not isinstance(category, str)
            or not category.strip()
            or len(category) > 100
        ):
            return ProfileResult(None, "rejected")
        budget = values.get("max_budget_usd_cents")
        if budget is not None and (
            isinstance(budget, bool)
            or not isinstance(budget, int)
            or budget <= 0
        ):
            return ProfileResult(None, "rejected")
        existing = self.read(user_id)
        if existing.status == "error":
            return existing
        now = datetime.fromtimestamp(self._clock(), tz=timezone.utc)
        profile = dict(existing.profile or {})
        profile.update(values)
        profile.update(
            {
                "schema_version": PROFILE_SCHEMA_VERSION,
                "consented_at": profile.get("consented_at") or now.isoformat(),
                "updated_at": now.isoformat(),
                "expires_at": datetime.fromtimestamp(
                    self._clock() + PROFILE_TTL_SECONDS, tz=timezone.utc
                ).isoformat(),
            }
        )
        serialized = json.dumps(
            profile,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        key = self._key(user_id)
        try:
            if self._redis is not None:
                self._redis.setex(key, PROFILE_TTL_SECONDS, serialized)
            else:
                with self._lock:
                    self._memory[key] = (
                        self._clock() + PROFILE_TTL_SECONDS,
                        serialized,
                    )
            return ProfileResult(dict(profile), "stored")
        except Exception:
            return ProfileResult(None, "error")

    def forget(self, user_id: str) -> ProfileResult:
        key = self._key(user_id)
        try:
            if self._redis is not None:
                self._redis.delete(key)
            else:
                with self._lock:
                    self._memory.pop(key, None)
            return ProfileResult(None, "forgotten")
        except Exception:
            return ProfileResult(None, "error")
