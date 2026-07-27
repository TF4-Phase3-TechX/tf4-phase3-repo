#!/usr/bin/env python3
"""Normalize archived OrderResult protobuf bytes and verify a drill replay."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from typing import Iterable


UUID = rb"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
# ByteArrayFormat separates Kafka values with LF. Requiring either file start or
# that separator avoids mistaking nested protobuf UUID fields for new orders.
ORDER_START = re.compile(rb"(?:(?<=\n)|\A)\x0a\x24" + UUID)


class ArchiveIntegrityError(ValueError):
    def __init__(self, message: str, record_count: int) -> None:
        super().__init__(message)
        self.record_count = record_count


def parse_utc(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def hourly_prefixes(start: str, end: str, base_prefix: str) -> Iterable[str]:
    current = parse_utc(start).replace(minute=0, second=0, microsecond=0)
    finish = parse_utc(end)
    if current >= finish:
        raise ValueError("START_TIME must be before END_TIME")
    while current < finish:
        yield (
            f"{base_prefix.rstrip('/')}/topic=orders/"
            f"year={current:%Y}/month={current:%m}/day={current:%d}/hour={current:%H}/"
        )
        current += dt.timedelta(hours=1)


def split_order_records(data: bytes, source: str) -> list[bytes]:
    stripped = data.rstrip(b"\r\n")
    if stripped.startswith(b"{"):
        try:
            marker = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{source}: invalid JSON marker: {exc}") from exc
        if not isinstance(marker, dict):
            raise ValueError(f"{source}: JSON marker must be an object")
        return [stripped]

    if data.startswith(b'"'):
        text = data.decode("utf-8")
        decoder = json.JSONDecoder()
        offset = 0
        values: list[bytes] = []
        corrupted = 0
        while offset < len(text):
            while offset < len(text) and text[offset].isspace():
                offset += 1
            if offset >= len(text):
                break
            value, offset = decoder.raw_decode(text, offset)
            if not isinstance(value, str):
                raise ValueError(f"{source}: legacy JSON record is not a string")
            if "\ufffd" in value:
                corrupted += 1
                continue
            values.append(value.encode("utf-8"))
        if corrupted:
            raise ArchiveIntegrityError(
                f"{source}: {corrupted} legacy JSON records lost protobuf bytes (U+FFFD)",
                corrupted + len(values),
            )
        if not values:
            raise ValueError(f"{source}: no legacy JSON records found")
        return values

    starts = [match.start() for match in ORDER_START.finditer(data)]
    if not starts:
        raise ValueError(f"{source}: no OrderResult record signature found")
    if data[: starts[0]].strip(b"\r\n\t "):
        raise ValueError(f"{source}: unexpected bytes before first record")

    records: list[bytes] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(data)
        record = data[start:end]
        # ByteArrayFormat appends one newline separator after each Kafka value.
        if record.endswith(b"\n"):
            record = record[:-1]
        records.append(record)
    return records


def order_id_from_protobuf(record: bytes) -> str:
    if len(record) < 38 or record[0] != 0x0A or record[1] != 0x24:
        raise ValueError("OrderResult does not start with field 1 UUID")
    order_id = record[2:38].decode("ascii")
    if not re.fullmatch(UUID.decode(), order_id):
        raise ValueError("OrderResult field 1 is not a UUID")
    return order_id.lower()


def record_identity(record: bytes) -> tuple[str, str]:
    if record.startswith(b"{"):
        marker = json.loads(record.decode("utf-8"))
        order_id = marker.get("order_id")
        marker_id = marker.get("marker_id")
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("JSON marker has no non-empty order_id")
        if not isinstance(marker_id, str) or not marker_id.strip():
            raise ValueError("JSON marker has no non-empty marker_id")
        if order_id != marker_id:
            raise ValueError("JSON marker order_id and marker_id differ")
        return order_id, "batch_marker"
    return order_id_from_protobuf(record), "order_result"


def compact(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def prepare(args: argparse.Namespace) -> int:
    input_dir = pathlib.Path(args.input_dir)
    files = sorted(path for path in input_dir.rglob("*") if path.is_file())
    if not files:
        raise ValueError("no downloaded archive objects found")

    producer_path = pathlib.Path(args.producer_file)
    manifest_path = pathlib.Path(args.manifest_file)
    summary_path = pathlib.Path(args.summary_file)

    unique: dict[str, tuple[str, bytes, str, str]] = {}
    duplicates = 0
    conflicts = 0
    records_read = 0
    failed = 0

    for path in files:
        relative = path.relative_to(input_dir).as_posix()
        try:
            records = split_order_records(path.read_bytes(), relative)
        except ArchiveIntegrityError as exc:
            print(str(exc), file=sys.stderr)
            records_read += exc.record_count
            failed += exc.record_count
            continue
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            failed += 1
            continue

        for record in records:
            records_read += 1
            try:
                order_id, record_type = record_identity(record)
                digest = hashlib.sha256(record).hexdigest()
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
                print(f"{relative}: {exc}", file=sys.stderr)
                failed += 1
                continue

            previous = unique.get(order_id)
            if previous:
                if previous[0] == digest:
                    duplicates += 1
                else:
                    conflicts += 1
                    failed += 1
                continue
            unique[order_id] = (digest, record, relative, record_type)

    marker_candidates = sum(1 for row in unique.values() if row[3] == "batch_marker")
    order_candidates = sum(1 for row in unique.values() if row[3] == "order_result")

    summary = {
        "batch_id": args.batch_id,
        "conflicting_duplicates": conflicts,
        "duplicates_skipped": duplicates,
        "failed": failed,
        "objects_read": len(files),
        "order_candidates": order_candidates,
        "records_read": records_read,
        "replay_candidates": len(unique),
        "source_marker_candidates": marker_candidates,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if not unique:
        print(compact(summary))
        return 2

    start_marker = {
        "batch_id": args.batch_id,
        "rel25_type": "BATCH_START",
        "source_window_end": args.end_time,
        "source_window_start": args.start_time,
    }
    end_marker = {
        "batch_id": args.batch_id,
        "expected_orders": len(unique),
        "rel25_type": "BATCH_END",
    }

    with producer_path.open("w", encoding="utf-8", newline="\n") as producer, (
        manifest_path.open("w", encoding="utf-8", newline="\n")
    ) as manifest:
        producer.write(f"__rel25_batch__:{args.batch_id}:start\t{compact(start_marker)}\n")
        for order_id, (digest, record, source, record_type) in sorted(unique.items()):
            envelope = {
                "batch_id": args.batch_id,
                "correlation_id": order_id,
                "order_id": order_id,
                "payload_base64": base64.b64encode(record).decode("ascii"),
                "payload_encoding": (
                    "json-marker-base64"
                    if record_type == "batch_marker"
                    else "protobuf-base64"
                ),
                "payload_sha256": digest,
                "rel25_type": (
                    "BATCH_MARKER_REPLAY"
                    if record_type == "batch_marker"
                    else "ORDER_REPLAY"
                ),
                "source_object": source,
                "source_record_type": record_type,
            }
            producer.write(f"{order_id}\t{compact(envelope)}\n")
            manifest.write(
                compact(
                    {
                        "order_id": order_id,
                        "payload_sha256": digest,
                        "record_type": record_type,
                    }
                )
                + "\n"
            )
        producer.write(f"__rel25_batch__:{args.batch_id}:end\t{compact(end_marker)}\n")

    print(compact(summary))
    return 0 if failed == 0 else 2


def verify(args: argparse.Namespace) -> int:
    expected: dict[str, tuple[str, str]] = {}
    with pathlib.Path(args.manifest_file).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            expected[row["order_id"]] = (
                row["payload_sha256"],
                row["record_type"],
            )

    observed: dict[str, tuple[str, str]] = {}
    duplicate_target_ids = 0
    failed = 0
    start_markers = 0
    end_markers = 0
    source_markers_replayed = 0
    diagnostic_lines_ignored = 0

    with pathlib.Path(args.consumed_file).open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            try:
                key, raw_value = line.split("\t", 1)
                value = json.loads(raw_value)
            except (ValueError, json.JSONDecodeError):
                # kubectl exec may merge remote Kafka CLI diagnostics into the
                # captured stream. They are not topic records; exact marker,
                # ID and hash reconciliation below still guards correctness.
                diagnostic_lines_ignored += 1
                continue
            if value.get("batch_id") != args.batch_id:
                failed += 1
                continue
            record_type = value.get("rel25_type")
            if record_type == "BATCH_START":
                start_markers += 1
            elif record_type == "BATCH_END":
                end_markers += 1
            elif record_type in {"ORDER_REPLAY", "BATCH_MARKER_REPLAY"}:
                order_id = value.get("order_id")
                digest = value.get("payload_sha256")
                source_record_type = value.get("source_record_type")
                if key != order_id or value.get("correlation_id") != order_id:
                    failed += 1
                    continue
                if record_type == "BATCH_MARKER_REPLAY":
                    if source_record_type != "batch_marker":
                        failed += 1
                        continue
                    source_markers_replayed += 1
                if order_id in observed:
                    duplicate_target_ids += 1
                observed[order_id] = (digest, source_record_type)
            else:
                failed += 1

    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    digest_mismatches = sorted(
        key for key in set(expected) & set(observed) if expected[key] != observed[key]
    )
    passed = (
        start_markers == 1
        and end_markers == 1
        and not missing
        and not unexpected
        and not digest_mismatches
        and duplicate_target_ids == 0
        and failed == 0
    )
    result = {
        "batch_id": args.batch_id,
        "duplicate_target_ids": duplicate_target_ids,
        "diagnostic_lines_ignored": diagnostic_lines_ignored,
        "end_markers": end_markers,
        "failed": failed,
        "missing": len(missing),
        "payload_mismatches": len(digest_mismatches),
        "replayed": len(observed),
        "source_markers_replayed": source_markers_replayed,
        "start_markers": start_markers,
        "unexpected": len(unexpected),
        "validation": "PASS" if passed else "FAIL",
    }
    pathlib.Path(args.result_file).write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(compact(result))
    return 0 if passed else 3


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)

    prefixes = commands.add_parser("prefixes")
    prefixes.add_argument("--start-time", required=True)
    prefixes.add_argument("--end-time", required=True)
    prefixes.add_argument("--base-prefix", required=True)

    prep = commands.add_parser("prepare")
    prep.add_argument("--input-dir", required=True)
    prep.add_argument("--producer-file", required=True)
    prep.add_argument("--manifest-file", required=True)
    prep.add_argument("--summary-file", required=True)
    prep.add_argument("--batch-id", required=True)
    prep.add_argument("--start-time", required=True)
    prep.add_argument("--end-time", required=True)

    check = commands.add_parser("verify")
    check.add_argument("--manifest-file", required=True)
    check.add_argument("--consumed-file", required=True)
    check.add_argument("--result-file", required=True)
    check.add_argument("--batch-id", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "prefixes":
            for prefix in hourly_prefixes(
                args.start_time, args.end_time, args.base_prefix
            ):
                print(prefix)
            return 0
        if args.command == "prepare":
            return prepare(args)
        return verify(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
