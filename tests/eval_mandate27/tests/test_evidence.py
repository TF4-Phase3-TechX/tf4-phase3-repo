import hashlib

from tests.eval_mandate27.evidence import build_evidence
from tests.eval_mandate27.verify_evidence import verify_evidence


def test_evidence_checksums_cover_verification_record(tmp_path):
    verification_path = tmp_path / "VERIFICATION.md"
    verification_path.write_text(
        "# Verification\n\nImplementation commit: `candidate`\n",
        encoding="utf-8",
    )

    manifest = build_evidence(tmp_path)
    checksums_path = tmp_path / "checksums.sha256"
    checksum_lines = checksums_path.read_text(encoding="utf-8").splitlines()

    assert any(
        line.endswith("  VERIFICATION.md") for line in checksum_lines
    )
    assert manifest["checksums_sha256"] == hashlib.sha256(
        checksums_path.read_bytes()
    ).hexdigest()
    for line in checksum_lines:
        expected, relative_path = line.split("  ", maxsplit=1)
        assert hashlib.sha256(
            (tmp_path / relative_path).read_bytes()
        ).hexdigest() == expected
    assert verify_evidence(tmp_path) == len(checksum_lines)
