"""Canonicalize bounded runtime surface labels without increasing cardinality."""

from __future__ import annotations


SURFACE_ALIASES = {
    "review_summary": "review_summary",
    "product_qa": "review_summary",
    "copilot_review": "copilot",
    "copilot": "copilot",
    "copilot_search": "copilot",
    "copilot_compare": "copilot",
    "shopping_copilot": "copilot",
}


def canonical_surface(value: str) -> str:
    normalized = str(value).strip().lower()
    try:
        return SURFACE_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported AI surface: {value!r}") from exc
