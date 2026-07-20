from dataclasses import replace

from app.config import Settings
from benchmark.calibrate_detection import evaluate


def test_documented_detector_seed_classifies_all_design_fixtures():
    result = evaluate(Settings())

    assert result["fp"] == 0
    assert result["fn"] == 0


def test_sensitivity_fixture_exposes_more_aggressive_ratio_tradeoff():
    seed = evaluate(Settings())
    aggressive = evaluate(replace(Settings(), ratio_threshold=1.3))

    assert seed["fp"] == 0
    assert aggressive["fp"] > seed["fp"]
