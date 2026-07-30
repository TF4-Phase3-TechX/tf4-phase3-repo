"""Verify the Mandate 24 evidence pack with cross-platform text hashes."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "artifact-sha256.txt"


def canonical_bytes(path: Path) -> bytes:
    """Preserve content while making Git's CRLF checkout conversion irrelevant."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def main() -> int:
    failures: list[str] = []
    checked = 0
    for line in MANIFEST.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        expected, relative_path = line.split(maxsplit=1)
        artifact = ROOT / relative_path
        if not artifact.is_file():
            failures.append(f"{relative_path}: missing")
            continue
        actual = hashlib.sha256(canonical_bytes(artifact)).hexdigest()
        checked += 1
        if actual != expected:
            failures.append(
                f"{relative_path}: expected {expected}, actual {actual}"
            )

    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print(f"verified={checked} failures={len(failures)}")
        return 1

    print(f"verified={checked} failures=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
