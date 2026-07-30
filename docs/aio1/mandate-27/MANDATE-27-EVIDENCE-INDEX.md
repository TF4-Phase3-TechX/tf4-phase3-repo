# Mandate 27 evidence index

## Reproduction

```bash
PYTHON_BIN=.eval-venv/bin/python \
  bash tests/eval_mandate27/repro.sh /tmp/mandate27-evidence
```

## Required artifacts

The committed hermetic pack is in
[`evidence/public-20260730/`](./evidence/public-20260730/). Its manifest records
the exact clean implementation commit.

- `manifest.json`: Git state, claims and case-to-report map.
- `baseline.json`: versioned distribution, thresholds and compatibility.
- `inputs/stable.jsonl`: stable negative control.
- `inputs/transient-spike.jsonl`: ordinary short-lived deviation.
- `inputs/seasonal-stable.jsonl`: bounded periodic variation.
- `inputs/shifted-copilot-fallback.jsonl`: Copilot-only fallback shift.
- `inputs/shifted-review-faithfulness.jsonl`: review-only quality shift.
- matching `*-report.json` files.
- `checksums.sha256` and `commands.txt`.

Synthetic replay proves detector behavior; it is not production-quality
evidence. Runtime completion additionally requires:

- `/metrics` proof for `app_ai_quality_events_total`;
- Prometheus rule load/health;
- Grafana current-versus-baseline panels;
- one normal runtime window;
- one controlled shifted replay or alert drill;
- immutable image and Git revision correlation.

## Acceptance

| Series | Expected |
|---|---|
| Stable | no signal |
| Transient spike | no final signal |
| Seasonal stable | no signal |
| Copilot fallback shift | `copilot/fallback_rate` after shift |
| Review faithfulness shift | `review_summary/faithfulness` after shift |
