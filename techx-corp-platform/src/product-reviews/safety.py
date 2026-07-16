#!/usr/bin/python

"""Deterministic safety controls for the product-review AI path.

The provider and its guardrail are defense in depth.  Data is normalized,
minimized and filtered here before it leaves the workload, and model output is
validated again before it can be returned to the storefront.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any


INSUFFICIENT_RESPONSE = (
    "I don't have enough information in the available product details and reviews "
    "to answer that question."
)
BLOCKED_RESPONSE = (
    "I can't follow instructions embedded in reviews, reveal hidden instructions, "
    "or perform shopping actions."
)
UNAVAILABLE_RESPONSE = (
    "The AI assistant is temporarily unavailable. Please use the original product "
    "details and reviews and try again later."
)

MAX_QUESTION_CHARS = 500
MAX_REVIEW_CHARS = 1_024
MAX_CONTEXT_CHARS = 12_000

_ATTACK_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|system|developer|instructions?)\b",
        r"\b(system|developer)\s*(prompt|message|instructions?)\b",
        r"\b(reveal|print|repeat|extract|show)\b.{0,50}\b(prompt|hidden|secret|canary|instructions?)\b",
        r"\b(jailbreak|prompt\s*injection|override\s+instructions?)\b",
        r"<\s*(system|assistant|developer)\s*>",
    )
)
_ACTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(add|put)\b.{0,30}\b(cart|basket)\b",
        r"\b(check\s*out|place|submit|confirm|complete)\b.{0,30}\b(order|purchase|payment)\b",
        r"\b(buy|purchase|refund|cancel)\b.{0,20}\b(for me|my order|this item)\b",
    )
)
_PII_PATTERNS = tuple(
    re.compile(pattern, flags)
    for pattern, flags in (
        (r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        (r"(?<!\w)(?:\+?\d[\s().-]?){8,15}(?!\w)", 0),
        (r"\b(?:\d[ -]*?){13,19}\b", 0),
        (r"\b\d{3}-\d{2}-\d{4}\b", 0),
        (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", 0),
    )
)


class UnsafeModelOutput(ValueError):
    """Raised when provider output cannot safely be displayed."""


@dataclass(frozen=True)
class PreparedContext:
    question: str
    product: dict[str, Any]
    reviews: list[dict[str, Any]]
    quarantined_review_count: int


def normalize_text(value: Any, max_chars: int) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = " ".join(text.replace("\x00", " ").split())
    return text[:max_chars]


def is_attack_or_action(text: str) -> bool:
    normalized = normalize_text(text, MAX_REVIEW_CHARS)
    return any(p.search(normalized) for p in (*_ATTACK_PATTERNS, *_ACTION_PATTERNS))


def contains_pii(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in _PII_PATTERNS)


def redact_pii(text: Any, max_chars: int = MAX_REVIEW_CHARS) -> str:
    redacted = normalize_text(text, max_chars)
    for pattern in _PII_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _sanitize_product(product: dict[str, Any]) -> dict[str, Any]:
    # Only fields useful for answering are allowed across the provider boundary.
    allowed = ("id", "name", "description", "categories")
    result: dict[str, Any] = {}
    for key in allowed:
        value = product.get(key)
        if isinstance(value, list):
            result[key] = [redact_pii(item, 200) for item in value[:10]]
        elif value is not None:
            result[key] = redact_pii(value, 2_000)
    return result


def prepare_context(
    question: str,
    product: dict[str, Any],
    review_rows: list[tuple[Any, ...]],
) -> PreparedContext:
    normalized_question = normalize_text(question, MAX_QUESTION_CHARS)
    safe_reviews: list[dict[str, Any]] = []
    quarantined = 0
    context_chars = 0

    for row in review_rows:
        # Current DB contract is (id, username, description, score). Username is
        # deliberately discarded; it is not needed for grounded Q&A.
        review_id, _, description, score = row
        normalized_description = normalize_text(description, MAX_REVIEW_CHARS)
        if is_attack_or_action(normalized_description):
            quarantined += 1
            continue
        description_safe = redact_pii(normalized_description)
        candidate = {
            "review_id": int(review_id),
            "description": description_safe,
            "score": str(score),
        }
        candidate_size = len(json.dumps(candidate, ensure_ascii=False))
        if context_chars + candidate_size > MAX_CONTEXT_CHARS:
            break
        safe_reviews.append(candidate)
        context_chars += candidate_size

    return PreparedContext(
        question=redact_pii(normalized_question, MAX_QUESTION_CHARS),
        product=_sanitize_product(product),
        reviews=safe_reviews,
        quarantined_review_count=quarantined,
    )


def validate_grounded_output(
    payload: Any,
    supplied_reviews: list[dict[str, Any]],
    system_canary: str,
) -> dict[str, Any]:
    if isinstance(payload, dict):
        payload = {k: v for k, v in payload.items() if k in {"decision", "answer", "citations"}}
        if "citations" in payload and isinstance(payload["citations"], list):
            cleaned = []
            for citation in payload["citations"]:
                if isinstance(citation, dict):
                    cleaned.append({k: v for k, v in citation.items() if k in {"review_id", "evidence_quote"}})
                else:
                    cleaned.append(citation)
            payload["citations"] = cleaned

    if not isinstance(payload, dict) or set(payload) != {"decision", "answer", "citations"}:
        raise UnsafeModelOutput("schema")
    if payload["decision"] not in ("answered", "insufficient"):
        raise UnsafeModelOutput("decision")
    if not isinstance(payload["answer"], str) or not isinstance(payload["citations"], list):
        raise UnsafeModelOutput("types")

    answer = normalize_text(payload["answer"], 2_000)
    if contains_pii(answer) or (system_canary and system_canary in answer):
        raise UnsafeModelOutput("sensitive_output")

    if payload["decision"] == "insufficient":
        if payload["citations"]:
            raise UnsafeModelOutput("insufficient_with_citations")
        return {"decision": "insufficient", "answer": INSUFFICIENT_RESPONSE, "citations": []}

    if not answer or not payload["citations"]:
        raise UnsafeModelOutput("answer_without_evidence")
    review_by_id = {review["review_id"]: review["description"] for review in supplied_reviews}
    validated_citations: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for citation in payload["citations"]:
        if not isinstance(citation, dict) or set(citation) != {"review_id", "evidence_quote"}:
            raise UnsafeModelOutput("citation_schema")
        try:
            review_id = int(citation["review_id"])
        except (TypeError, ValueError) as exc:
            raise UnsafeModelOutput("citation_id") from exc
        quote = citation["evidence_quote"]
        if not isinstance(quote, str) or not quote or quote not in review_by_id.get(review_id, ""):
            raise UnsafeModelOutput("citation_quote")
        if contains_pii(quote):
            raise UnsafeModelOutput("citation_pii")
        if review_id not in seen_ids:
            validated_citations.append({"review_id": review_id, "evidence_quote": quote})
            seen_ids.add(review_id)

    return {"decision": "answered", "answer": answer, "citations": validated_citations}
