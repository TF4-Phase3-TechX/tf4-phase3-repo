"""Canonical service-name normalization for cross-service RCA.

Never silently merge arbitrary unknown names. Unknown inputs keep their
canonical form after light whitespace/case cleanup and report a reason.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Mapping


# Known aliases observed in TechX telemetry / deployment naming.
DEFAULT_ALIASES: dict[str, str] = {
    "frontend-web": "frontend",
    "frontend-proxy": "frontend-proxy",
    "productcatalog": "product-catalog",
    "product_catalog": "product-catalog",
    "productcatalogservice": "product-catalog",
    "product-catalog-service": "product-catalog",
    "productreviews": "product-reviews",
    "product_reviews": "product-reviews",
    "product-reviews-service": "product-reviews",
    "recommendationservice": "recommendation",
    "recommendation-service": "recommendation",
    "adservice": "ad",
    "ad-service": "ad",
    "cartservice": "cart",
    "cart-service": "cart",
    "checkoutservice": "checkout",
    "checkout-service": "checkout",
    "paymentservice": "payment",
    "payment-service": "payment",
    "currencyservice": "currency",
    "currency-service": "currency",
    "shippingservice": "shipping",
    "shipping-service": "shipping",
    "emailservice": "email",
    "email-service": "email",
    "quoteservice": "quote",
    "quote-service": "quote",
    # LLM telemetry label vs owning service / external provider boundary.
    "llm": "external-llm-provider",
    "bedrock": "external-llm-provider",
    "aws-bedrock": "external-llm-provider",
    "amazon-bedrock": "external-llm-provider",
}

_SUFFIX_RE = re.compile(
    r"-(?:deployment|svc|service|v\d+|primary|canary|blue|green)$",
    re.IGNORECASE,
)
_NAMESPACE_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?\.")
_SAFE_SERVICE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9./:-]{0,254})$")


@dataclass(frozen=True)
class NormalizedService:
    canonical_service: str
    original_service: str
    normalization_reason: str


def _strip_namespace(name: str) -> tuple[str, bool]:
    if _NAMESPACE_RE.match(name) and name.count(".") >= 1:
        # e.g. techx-corp.frontend -> frontend when left of first dot is ns-like
        left, _, right = name.partition(".")
        if right and left and not right.startswith("."):
            return right, True
    return name, False


def _safe_service_identifier(name: str) -> tuple[str, bool]:
    """Keep output/log/Markdown identities bounded and injection-safe.

    Malformed external identities remain distinct through a stable digest rather
    than being silently merged into a shared ``unknown`` bucket.
    """

    if _SAFE_SERVICE_RE.fullmatch(name):
        return name, False
    digest = hashlib.sha256(name.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"invalid-service-{digest}", True


def normalize_service_name(
    raw: str | None,
    *,
    aliases: Mapping[str, str] | None = None,
    strip_deployment_suffix: bool = False,
    strip_namespace_prefix: bool = False,
) -> NormalizedService:
    """Normalize a service identity for graph/candidate aggregation.

    Parameters
    ----------
    raw:
        Original service string from Decision, Jaeger process, or scenario.
    aliases:
        Optional per-scenario override merged over DEFAULT_ALIASES.
    strip_deployment_suffix:
        When true, strip known deployment suffixes after alias lookup fails.
    strip_namespace_prefix:
        When true, strip one DNS-like namespace prefix. Disabled unless the
        caller explicitly knows the telemetry naming convention.
    """

    original = "" if raw is None else str(raw)
    if not original or not original.strip():
        return NormalizedService(
            canonical_service="unknown",
            original_service=original,
            normalization_reason="empty_or_missing",
        )

    cleaned = original.strip()
    reasons: list[str] = []
    if cleaned != original:
        reasons.append("trimmed_whitespace")

    lower = cleaned.lower()
    if lower != cleaned:
        reasons.append("lowercased")
        cleaned = lower

    # Collapse internal whitespace / underscores used as separators inconsistently.
    collapsed = re.sub(r"[\s_]+", "-", cleaned)
    if collapsed != cleaned:
        reasons.append("collapsed_separators")
        cleaned = collapsed

    if strip_namespace_prefix:
        ns_stripped, did_strip_ns = _strip_namespace(cleaned)
        if did_strip_ns:
            reasons.append("stripped_namespace_prefix")
            cleaned = ns_stripped

    merged = dict(DEFAULT_ALIASES)
    if aliases:
        # Scenario aliases win; keys normalized lightly.
        for key, value in aliases.items():
            if key is None or value is None:
                continue
            k = re.sub(r"[\s_]+", "-", str(key).strip().lower())
            v = re.sub(r"[\s_]+", "-", str(value).strip().lower())
            if k and v:
                merged[k] = v

    if cleaned in merged:
        target = re.sub(r"[\s_]+", "-", merged[cleaned].strip().lower())
        if target != cleaned:
            reasons.append(f"alias:{cleaned}->{target}")
        target, unsafe = _safe_service_identifier(target)
        if unsafe:
            reasons.append("invalid_identifier_hashed")
        return NormalizedService(
            canonical_service=target,
            original_service=original,
            normalization_reason="+".join(reasons) or "identity",
        )

    if strip_deployment_suffix:
        stripped = _SUFFIX_RE.sub("", cleaned)
        if stripped != cleaned:
            reasons.append("stripped_deployment_suffix")
            cleaned = stripped
            if cleaned in merged:
                target = re.sub(r"[\s_]+", "-", merged[cleaned].strip().lower())
                if target != cleaned:
                    reasons.append(f"alias:{cleaned}->{target}")
                target, unsafe = _safe_service_identifier(target)
                if unsafe:
                    reasons.append("invalid_identifier_hashed")
                return NormalizedService(
                    canonical_service=target,
                    original_service=original,
                    normalization_reason="+".join(reasons) or "identity",
                )

    canonical, unsafe = _safe_service_identifier(cleaned)
    if unsafe:
        reasons.append("invalid_identifier_hashed")
    return NormalizedService(
        canonical_service=canonical,
        original_service=original,
        normalization_reason="+".join(reasons) or "identity",
    )


def normalize_many(
    names: list[str] | tuple[str, ...],
    *,
    aliases: Mapping[str, str] | None = None,
) -> list[NormalizedService]:
    return [normalize_service_name(name, aliases=aliases) for name in names]
