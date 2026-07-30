"""Produce a self-contained, deterministic Mandate 27 mentor evidence pack."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from .baseline import build_baseline
from .common import git_metadata, utc_now, write_json
from .contract import load_observations
from .generate_fixtures import generate
from .replay import replay


EXPECTED = {
    "stable": ("no_drift", []),
    "transient_spike": ("no_drift", []),
    "seasonal_stable": ("no_drift", []),
    "shifted_copilot_fallback": (
        "drift",
        [("copilot", "fallback_rate")],
    ),
    "shifted_review_faithfulness": (
        "drift",
        [("review_summary", "faithfulness")],
    ),
}


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_lf(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def build_evidence(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir = output_dir / "inputs"
    paths = generate(fixture_dir)
    baseline = build_baseline(load_observations(paths["baseline"]))
    baseline_path = output_dir / "baseline.json"
    write_json(baseline_path, baseline)

    results = {}
    for name, expected in EXPECTED.items():
        report_path = output_dir / f"{name.replace('_', '-')}-report.json"
        report = replay(paths[name], baseline_path, report_path)
        signals = [
            (signal["surface"], signal["metric"])
            for signal in report["signals"]
        ]
        if (report["status"], signals) != expected:
            raise RuntimeError(
                f"{name}: expected {expected}, got {(report['status'], signals)}"
            )
        results[name] = {
            "input": paths[name].relative_to(output_dir).as_posix(),
            "report": report_path.relative_to(output_dir).as_posix(),
            "status": report["status"],
            "signals": [
                {"surface": surface, "metric": metric}
                for surface, metric in signals
            ],
        }

    commands_path = output_dir / "commands.txt"
    _write_lf(
        commands_path,
        "\n".join(
            [
                "python -m tests.eval_mandate27.generate_fixtures --output-dir INPUT_DIR",
                "python -m tests.eval_mandate27.baseline INPUT_DIR/baseline.jsonl --output baseline.json",
                "python -m tests.eval_mandate27.replay SERIES.jsonl --baseline baseline.json --output report.json",
                "python -m pytest -q tests/eval_mandate27/tests",
            ]
        )
        + "\n",
    )

    artifact_paths = [
        baseline_path,
        commands_path,
        *sorted(fixture_dir.glob("*.jsonl")),
        *sorted(output_dir.glob("*-report.json")),
    ]
    pytest_path = output_dir / "pytest.txt"
    if pytest_path.exists():
        artifact_paths.append(pytest_path)
    verification_path = output_dir / "VERIFICATION.md"
    if verification_path.exists():
        artifact_paths.append(verification_path)
    checksums_path = output_dir / "checksums.sha256"
    _write_lf(
        checksums_path,
        "".join(
            f"{_checksum(path)}  "
            f"{path.relative_to(output_dir).as_posix()}\n"
            for path in artifact_paths
        ),
    )
    manifest = {
        "schema_version": "mandate27-evidence-v1",
        "generated_at_utc": utc_now(),
        "git": git_metadata(),
        "baseline_sha256": _checksum(baseline_path),
        "checksums_sha256": _checksum(checksums_path),
        "results": results,
        "claims": {
            "stable_false_flags": 0,
            "shifted_series_detected": 2,
            "raw_content_retained": False,
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_evidence(args.output_dir)
    print(
        f"evidence={args.output_dir} "
        f"stable_false_flags={manifest['claims']['stable_false_flags']} "
        f"shifted_series_detected={manifest['claims']['shifted_series_detected']}"
    )


if __name__ == "__main__":
    main()
