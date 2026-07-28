"""
evaluator.py — Single evaluate() function for all test cases, fail-closed.

Checks grounding, then evaluates based on expected_behavior:
  - return_products  → recall == 1.0 AND precision >= MIN_PRECISION_THRESHOLD
                       (all expected IDs must appear; returning the full catalog
                       does NOT pass because precision would drop below threshold)
  - refuse_*         → refusal must be triggered with no products returned
"""

try:
    from .grounding import validate_grounding
except ImportError:
    from grounding import validate_grounding

# Minimum acceptable precision for return_products cases.
# A query expecting N products from a catalog of 10 must return at most 2N
# results before failing the precision gate. This prevents a whole-catalog
# dump from certifying as "relevant products" while still allowing slight
# over-retrieval from fuzzy filters.
MIN_PRECISION_THRESHOLD = 0.5


def evaluate(
    test_case: dict,
    actual_product_ids: list[str],
    actual_refused: bool,
    catalog_ids: set[str],
) -> dict:
    """Evaluate a single test case.

    Args:
        test_case:          Dict with keys test_id, group, query,
                            expected_product_ids, expected_behavior, description.
        actual_product_ids: Product IDs returned by the system under test.
        actual_refused:     Whether the system refused to answer.
        catalog_ids:        Set of all valid product IDs in the catalog.

    Returns:
        {
            "passed": bool,
            "reason": str,
            "details": dict,
        }
    """
    try:
        expected_ids = set(test_case["expected_product_ids"])
        actual_ids = set(actual_product_ids)
        expected_behavior = test_case["expected_behavior"]

        # ---------------------------------------------------------- #
        # 1. Grounding check                                          #
        # ---------------------------------------------------------- #
        grounding_result = validate_grounding(actual_product_ids, catalog_ids)
        if not grounding_result["grounded"]:
            return {
                "passed": False,
                "reason": "grounding_failure",
                "details": {
                    "grounding_result": grounding_result,
                    "expected_behavior": expected_behavior,
                },
            }

        # ---------------------------------------------------------- #
        # 2. Behaviour-specific evaluation                            #
        # ---------------------------------------------------------- #
        if expected_behavior == "return_products":
            return _eval_return_products(
                expected_ids, actual_ids, actual_refused, grounding_result, expected_behavior
            )

        if expected_behavior in ("refuse_out_of_scope", "refuse_injection"):
            return _eval_refusal(
                actual_ids, actual_refused, grounding_result, expected_behavior
            )

        # Unknown expected_behavior → fail closed
        return {
            "passed": False,
            "reason": "evaluation_error",
            "details": {
                "grounding_result": grounding_result,
                "expected_behavior": expected_behavior,
                "error": f"Unknown expected_behavior: {expected_behavior}",
            },
        }

    except Exception as exc:  # noqa: BLE001 — fail closed
        return {
            "passed": False,
            "reason": "evaluation_error",
            "details": {
                "error": str(exc),
            },
        }


# ------------------------------------------------------------------ #
# Internal helpers                                                    #
# ------------------------------------------------------------------ #


def _eval_return_products(
    expected_ids: set[str],
    actual_ids: set[str],
    actual_refused: bool,
    grounding_result: dict,
    expected_behavior: str,
) -> dict:
    """Evaluate a test case where products are expected to be returned.

    Pass requires BOTH:
      - recall == 1.0  (all expected products are present)
      - precision >= MIN_PRECISION_THRESHOLD  (no whole-catalog dumps)
    """
    if actual_refused:
        return {
            "passed": False,
            "reason": "unexpected_refusal",
            "details": {
                "grounding_result": grounding_result,
                "expected_behavior": expected_behavior,
            },
        }

    # Recall: proportion of expected products that appear in actual
    if expected_ids:
        found = expected_ids & actual_ids
        recall = len(found) / len(expected_ids)
    else:
        # Edge case: expected is empty (should not normally happen for
        # return_products, but handle gracefully).
        recall = 1.0

    # Precision: proportion of actual products that are expected.
    # This gates against returning the full catalog and claiming 100% recall.
    if actual_ids:
        precision = len(expected_ids & actual_ids) / len(actual_ids)
    else:
        precision = 1.0 if not expected_ids else 0.0

    missing = sorted(expected_ids - actual_ids)
    extra = sorted(actual_ids - expected_ids)

    # Both gates must pass.
    recall_ok = recall == 1.0
    precision_ok = precision >= MIN_PRECISION_THRESHOLD

    if recall_ok and precision_ok:
        reason = "pass" if not extra else "pass_with_extra_results"
        passed = True
    elif not recall_ok:
        reason = "missing_expected_products"
        passed = False
    else:
        # recall_ok but precision below threshold — over-retrieval
        reason = "precision_below_threshold"
        passed = False

    return {
        "passed": passed,
        "reason": reason,
        "details": {
            "grounding_result": grounding_result,
            "expected_behavior": expected_behavior,
            "recall": recall,
            "precision": precision,
            "precision_threshold": MIN_PRECISION_THRESHOLD,
            "missing_ids": missing,
            "extra_ids": extra,
        },
    }


def _eval_refusal(
    actual_ids: set[str],
    actual_refused: bool,
    grounding_result: dict,
    expected_behavior: str,
) -> dict:
    """Evaluate a test case where a refusal is expected."""
    if not actual_refused:
        return {
            "passed": False,
            "reason": "expected_refusal_not_triggered",
            "details": {
                "grounding_result": grounding_result,
                "expected_behavior": expected_behavior,
            },
        }

    if actual_ids:
        return {
            "passed": False,
            "reason": "products_returned_on_refusal",
            "details": {
                "grounding_result": grounding_result,
                "expected_behavior": expected_behavior,
                "returned_ids": sorted(actual_ids),
            },
        }

    return {
        "passed": True,
        "reason": "pass",
        "details": {
            "grounding_result": grounding_result,
            "expected_behavior": expected_behavior,
        },
    }
