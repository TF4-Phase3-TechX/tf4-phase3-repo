"""Verify a committed Mandate 27 evidence pack byte for byte."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_evidence(root: Path) -> int:
    checksums_path = root / "checksums.sha256"
    manifest_path = root / "manifest.json"
    if not checksums_path.is_file() or not manifest_path.is_file():
        raise ValueError("evidence pack requires checksums.sha256 and manifest.json")

    checked = 0
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        expected, separator, relative = line.partition("  ")
        if not separator or not relative:
            raise ValueError(f"invalid checksum record: {line!r}")
        if "\\" in relative:
            raise ValueError(
                f"checksum path must use portable '/' separators: {relative}"
            )
        candidate = (root / PurePosixPath(relative)).resolve()
        if root.resolve() not in candidate.parents:
            raise ValueError(f"checksum path escapes evidence root: {relative}")
        if not candidate.is_file():
            raise ValueError(f"missing evidence artifact: {relative}")
        actual = sha256(candidate)
        if actual != expected:
            raise ValueError(
                f"checksum mismatch for {relative}: {actual} != {expected}"
            )
        checked += 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_checksums = manifest.get("checksums_sha256")
    actual_checksums = sha256(checksums_path)
    if expected_checksums != actual_checksums:
        raise ValueError(
            "manifest checksum mismatch for checksums.sha256: "
            f"{actual_checksums} != {expected_checksums}"
        )
    return checked


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_root", type=Path)
    args = parser.parse_args()
    checked = verify_evidence(args.evidence_root)
    print(f"evidence={args.evidence_root} verified_artifacts={checked}")


if __name__ == "__main__":
    main()
