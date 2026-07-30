from __future__ import annotations

from copy import deepcopy

from run_eval import build_report
from semantic_faithfulness import (
    _copilot_catalog_projection,
    build_semantic_pair,
)


class FakeJudge:
    def __init__(self, scores):
        self.scores = list(scores)
        self.pairs = []
        self.calls = []

    def score_pairs(self, pairs, *, batch_size=8):
        self.pairs = list(pairs)
        self.calls.append(self.pairs)
        scores = self.scores or [1.0] * len(self.pairs)
        assert len(self.pairs) == len(scores)
        return scores, 0


def review_case():
    return {
        "schema_version": "mandate14-case-v2",
        "case_id": "M14-SEM-001",
        "surface": "review_summary",
        "variant": "candidate",
        "category": "grounded",
        "human_pass": True,
        "sources": [{
            "source_id": "review-1",
            "source_type": "review",
            "text": "Customers praised the compact design.",
        }],
        "expected": {
            "outcome": "answer",
            "answerable": True,
            "valid_task": True,
            "facts": [],
        },
        "observed": {
            "outcome": "answered",
            "response_text": "Buyers considered the design easy to carry.",
            "claims": [{
                "text": "Buyers considered the design easy to carry",
                "claim_type": "opinion",
                "source_ids": ["review-1"],
            }],
            "blocked": False,
            "latency_ms": 1,
            "input_tokens": 1,
            "output_tokens": 1,
            "model_requests": 1,
            "estimated_cost_usd": 0,
        },
    }


def test_semantic_judge_accepts_supported_paraphrase_without_keyword_gate():
    value = review_case()
    judge = FakeJudge([0.91])
    report = build_report([value], b"fixture", semantic_judge=judge)
    result = report["per_case"][0]

    assert result["scorer_pass"]
    assert result["grounding"]["semantic_faithfulness"] == 1.0
    assert result["grounding"]["claims"][0]["semantic_factuality_score"] == 0.91
    assert report["aggregate"]["claim_faithfulness"]["rate"] == 1.0


def test_semantic_judge_rejects_lexically_similar_contradiction():
    value = review_case()
    value["sources"][0]["text"] = "The watch is waterproof."
    value["observed"]["response_text"] = "The watch is not waterproof."
    value["observed"]["claims"][0]["text"] = "The watch is not waterproof"
    judge = FakeJudge([0.01])
    report = build_report([value], b"fixture", semantic_judge=judge)
    result = report["per_case"][0]

    assert not result["scorer_pass"]
    assert "unsupported_claim" in result["failures"]
    assert result["grounding"]["semantic_hallucinated_claims"] == 1
    assert report["aggregate"]["hallucination"]["rate"] == 1.0


def test_copilot_catalog_projection_is_not_semantic_faithfulness_credit():
    value = review_case()
    value.update({
        "case_id": "M14-SEM-COP-001",
        "surface": "copilot",
        "sources": [{
            "source_id": "catalog:scope",
            "source_type": "catalog",
            "text": "Travel Scope. Price 99 dollars.",
        }],
    })
    value["observed"]["response_text"] = "Travel Scope. Price 99 dollars."
    value["observed"]["claims"] = [{
        "text": "Travel Scope. Price 99 dollars.",
        "claim_type": "fact",
        "source_ids": ["catalog:scope"],
    }]
    report = build_report(
        [deepcopy(value)],
        b"fixture",
        semantic_judge=FakeJudge([]),
    )
    result = report["per_case"][0]

    assert result["scorer_pass"]
    assert result["grounding"]["semantic_total_claims"] == 0
    assert report["aggregate"]["claim_faithfulness"]["denominator"] == 0
    assert (
        report["aggregate"]["semantic_faithfulness_judge"][
            "copilot_catalog_projections_excluded"
        ]
        == 1
    )


def test_catalog_projection_requires_exact_order_type_and_identity():
    claim = {
        "claim_type": "fact",
        "text": "Dog bites man.",
    }
    catalog = [{
        "source_id": "catalog:dog",
        "source_type": "catalog",
        "text": "Dog bites man.",
    }]

    assert _copilot_catalog_projection("copilot", claim, catalog)
    assert not _copilot_catalog_projection(
        "copilot",
        {**claim, "text": "Man bites dog."},
        catalog,
    )
    assert not _copilot_catalog_projection(
        "copilot",
        {**claim, "text": "Dog bites man man."},
        catalog,
    )
    assert not _copilot_catalog_projection(
        "copilot",
        claim,
        [{**catalog[0], "source_type": "product_description"}],
    )
    assert not _copilot_catalog_projection(
        "copilot",
        claim,
        [{**catalog[0], "source_id": "product:dog"}],
    )


def test_shared_pair_builder_is_deterministic_and_source_ordered():
    premise = "Alpha is red. Beta is blue. Gamma is green."
    evidence, hypothesis = build_semantic_pair(
        premise,
        "Gamma is green.",
    )

    assert evidence == "Alpha is red. Gamma is green."
    assert hypothesis == "Gamma is green."


def test_empty_response_fragment_is_not_sent_to_semantic_judge():
    value = review_case()
    value["observed"]["response_text"] = (
        "Buyers considered the design easy to carry. ."
    )
    report = build_report(
        [value],
        b"fixture",
        semantic_judge=FakeJudge([0.91]),
    )

    semantic = report["aggregate"]["semantic_faithfulness_judge"]
    assert semantic["scored_response_assertions"] == 1
    assert semantic["input_truncated_count"] == 0
