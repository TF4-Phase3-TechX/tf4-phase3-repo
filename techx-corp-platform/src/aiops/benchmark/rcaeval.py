from __future__ import annotations

import json
import math
import random
import re
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


CASE_PATTERN = re.compile(
    r"^re(?P<round>\d+)(?P<system>ss|tt|ob)_(?P<service>.+)_"
    r"(?P<fault>cpu|mem|disk|delay|loss|socket|f\d+)_(?P<replicate>\d+)$"
)
METRIC_SUFFIXES = (
    "latency-90",
    "latency-50",
    "workload",
    "diskio",
    "socket",
    "cpu",
    "mem",
)


@dataclass(frozen=True)
class CaseLabel:
    name: str
    system: str
    service: str
    fault: str
    replicate: int


@dataclass(frozen=True)
class MetricWindow:
    service: str
    metric: str
    baseline: tuple[float, ...]
    incident: tuple[float, ...]


def parse_case_name(name: str) -> CaseLabel:
    match = CASE_PATTERN.fullmatch(name)
    if not match:
        raise ValueError(f"Unsupported RCAEval case name: {name}")
    return CaseLabel(
        name=name,
        system=match.group("system"),
        service=match.group("service"),
        fault=match.group("fault"),
        replicate=int(match.group("replicate")),
    )


def split_metric_name(name: str) -> tuple[str, str] | None:
    for suffix in METRIC_SUFFIXES:
        marker = f"_{suffix}"
        if name.endswith(marker):
            return name[: -len(marker)], suffix
    return None


def stratified_sample(labels: list[CaseLabel], limit: int | None, seed: int = 7) -> list[CaseLabel]:
    if limit is None or limit >= len(labels):
        return sorted(labels, key=lambda label: label.name)
    if limit <= 0:
        return []
    rng = random.Random(seed)
    strata: dict[tuple[str, str], list[CaseLabel]] = {}
    for label in labels:
        strata.setdefault((label.system, label.fault), []).append(label)
    for cases in strata.values():
        cases.sort(key=lambda label: label.name)
        rng.shuffle(cases)
    # Interleave systems within each fault type so even small smoke samples do
    # not accidentally select only the alphabetically first ecosystem.
    ordered_strata = sorted(strata, key=lambda key: (key[1], key[0]))
    selected: list[CaseLabel] = []
    while len(selected) < limit:
        progressed = False
        for key in ordered_strata:
            cases = strata[key]
            if cases:
                selected.append(cases.pop())
                progressed = True
                if len(selected) == limit:
                    break
        if not progressed:
            break
    return selected


class RCAEvalArchive:
    """Lazy RCAEval-v2 reader for real ZIPs and gzip-tars with a .zip suffix."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.archive: zipfile.ZipFile | None = None

    def __enter__(self) -> "RCAEvalArchive":
        if zipfile.is_zipfile(self.path):
            self.archive = zipfile.ZipFile(self.path)
        return self

    def __exit__(self, *_: object) -> None:
        if self.archive:
            self.archive.close()
        self.archive = None

    def labels(self) -> list[CaseLabel]:
        labels: list[CaseLabel] = []
        if self.archive:
            names = self.archive.namelist()
            for name in names:
                match = re.fullmatch(r"data/([^/]+)/metrics\.json", name)
                if match:
                    labels.append(parse_case_name(match.group(1)))
        else:
            # The provided RCAEval-v2.zip is actually a gzip-compressed tar.
            # Its case directories precede file payloads, so label discovery
            # stops at the first file without inflating the full 4.4 GB stream.
            with tarfile.open(self.path, mode="r|gz") as archive:
                for member in archive:
                    if member.isdir():
                        match = re.fullmatch(r"data/([^/]+)/?", member.name)
                        if match:
                            try:
                                labels.append(parse_case_name(match.group(1)))
                            except ValueError:
                                pass
                    elif labels:
                        break
        return sorted(labels, key=lambda label: label.name)

    def iter_cases(
        self, labels: list[CaseLabel]
    ) -> Iterator[tuple[CaseLabel, int, dict[str, list[list[float]]]]]:
        selected = {label.name: label for label in labels}
        if self.archive:
            for label in labels:
                prefix = f"data/{label.name}"
                injection_time = int(self.archive.read(f"{prefix}/inject_time.txt").decode().strip())
                metrics = json.loads(self.archive.read(f"{prefix}/metrics.json"))
                yield label, injection_time, metrics
            return

        partial: dict[str, dict[str, object]] = {}
        with tarfile.open(self.path, mode="r|gz") as archive:
            for member in archive:
                match = re.fullmatch(r"data/([^/]+)/(metrics\.json|inject_time\.txt)", member.name)
                if not match or match.group(1) not in selected or not member.isfile():
                    continue
                case_name, filename = match.groups()
                stream = archive.extractfile(member)
                if stream is None:
                    continue
                slot = partial.setdefault(case_name, {})
                if filename == "metrics.json":
                    slot["metrics"] = json.load(stream)
                else:
                    slot["injection_time"] = int(stream.read().decode().strip())
                if "metrics" in slot and "injection_time" in slot:
                    yield (
                        selected[case_name],
                        int(slot["injection_time"]),
                        slot["metrics"],  # type: ignore[arg-type]
                    )
                    del partial[case_name]


# Backward-compatible alias for callers that used the initial adapter name.
RCAEvalZip = RCAEvalArchive


def metric_windows(
    metrics: dict[str, list[list[float]]],
    injection_time: int,
    *,
    baseline_seconds: int = 600,
    incident_seconds: int = 600,
    guard_seconds: int = 30,
    minimum_points: int = 30,
) -> Iterator[MetricWindow]:
    baseline_start = injection_time - baseline_seconds
    baseline_end = injection_time - guard_seconds
    incident_end = injection_time + incident_seconds
    for name, points in metrics.items():
        split = split_metric_name(name)
        if not split:
            continue
        service, metric = split
        baseline: list[float] = []
        incident: list[float] = []
        for timestamp, raw_value in points:
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            timestamp = int(timestamp)
            if baseline_start <= timestamp < baseline_end:
                baseline.append(value)
            elif injection_time <= timestamp <= incident_end:
                incident.append(value)
        if len(baseline) >= minimum_points and len(incident) >= minimum_points:
            yield MetricWindow(service, metric, tuple(baseline), tuple(incident))
