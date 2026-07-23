"""
grounding.py — Validate that returned product IDs exist in the catalog.

An empty returned-ID list is considered grounded (∅ ⊆ S for any set S).
"""

from __future__ import annotations


def validate_grounding(
    returned_ids: list[str],
    catalog_ids: set[str],
) -> dict:
    """Check whether every returned product ID belongs to the catalog.

    Args:
        returned_ids: Product IDs returned by the search system.
        catalog_ids:  Set of all valid product IDs in the catalog.

    Returns:
        {
            "grounded": bool,       # True iff every ID is valid
            "invalid_ids": list[str] # IDs not found in catalog
        }
    """
    invalid = [pid for pid in returned_ids if pid not in catalog_ids]
    return {
        "grounded": len(invalid) == 0,
        "invalid_ids": invalid,
    }
