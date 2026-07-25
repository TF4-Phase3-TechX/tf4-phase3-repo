"""Deterministic review summaries used by Shopping Copilot.

This deliberately does not call the product-Q&A model.  Copilot can surface
review evidence, but it must not inherit a model-authored, partially completed
answer from the product detail review flow.
"""

from __future__ import annotations

from typing import Any

from safety import INSUFFICIENT_RESPONSE, prepare_context


def _is_vietnamese(text: str) -> bool:
    return any(char in text.lower() for char in "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")


def _score(review: dict[str, Any]) -> float:
    try:
        return float(review.get("score", 0))
    except (TypeError, ValueError):
        return 0.0


def summarize_copilot_reviews(
    question: str,
    product: Any,
    review_rows: list[tuple[Any, ...]],
) -> tuple[str, str, int]:
    """Return a complete, evidence-only Copilot review response.

    Returns ``(response, outcome, quarantined_review_count)``.  Review text is
    normalized, redacted, and injection-filtered by ``prepare_context`` before
    it is included in the response.
    """
    product_data = {
        "id": str(getattr(product, "id", "")),
        "name": str(getattr(product, "name", "")),
        "description": str(getattr(product, "description", "")),
        "categories": list(getattr(product, "categories", [])),
    }
    prepared = prepare_context(question, product_data, review_rows)
    reviews = prepared.reviews
    if not reviews:
        return INSUFFICIENT_RESPONSE, "insufficient", prepared.quarantined_review_count

    vi = _is_vietnamese(question)
    product_name = prepared.product.get("name") or "sản phẩm"
    highest = max(reviews, key=_score)
    lowest = min(reviews, key=_score)

    if len(reviews) == 1:
        if vi:
            response = (
                f"Dựa trên 1 đánh giá về **{product_name}**:\n"
                f"• Khách hàng nhận xét: “{highest['description']}” (điểm {highest['score']})."
            )
        else:
            response = (
                f"Based on 1 review of **{product_name}**:\n"
                f"• Customer feedback: “{highest['description']}” (score {highest['score']})."
            )
    elif vi:
        response = (
            f"Dựa trên {len(reviews)} đánh giá về **{product_name}**:\n"
            f"• Điểm tích cực: “{highest['description']}” (điểm {highest['score']}).\n"
            f"• Điểm cần lưu ý: “{lowest['description']}” (điểm {lowest['score']})."
        )
    else:
        response = (
            f"Based on {len(reviews)} reviews of **{product_name}**:\n"
            f"• Positive feedback: “{highest['description']}” (score {highest['score']}).\n"
            f"• Point to consider: “{lowest['description']}” (score {lowest['score']})."
        )
    return response, "answered", prepared.quarantined_review_count
