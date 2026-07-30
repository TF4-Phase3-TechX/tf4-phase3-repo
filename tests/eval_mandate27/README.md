# Mandate 27 deterministic model-quality drift harness

This package pins a content-free baseline and detects adverse output-quality
drift independently for `review_summary` and `copilot`. It reuses Mandate 14
quality results and the bounded outcome telemetry from Mandates 24/25. The
detector makes no model call, does not retain prompt/response content and does
not modify flagd.

## One-command proof

From the repository root:

```bash
PYTHON_BIN=.eval-venv/bin/python \
  bash tests/eval_mandate27/repro.sh /tmp/mandate27-evidence
```

The command generates a versioned baseline, stable/noise/seasonal controls, two
shifted series, drift reports, checksums and a manifest. It also runs the
hermetic unit tests.

Expected claims:

- stable, seasonal-stable and transient-spike series: `no_drift`;
- shifted Copilot fallback series: `copilot/fallback_rate`;
- shifted review quality series: `review_summary/faithfulness`;
- no signal occurs before the injected shift.

## Replay a mentor-supplied series

Each JSONL row must satisfy `schemas/observation.schema.json`. It contains only
an event ID, timestamp, canonical surface, compatibility metadata and bounded
quality values.

```bash
python -m tests.eval_mandate27.replay mentor-series.jsonl \
  --baseline /tmp/mandate27-evidence/baseline.json \
  --output /tmp/mentor-drift-report.json
```

Add `--fail-on-drift` when CI should return exit code `2` for a valid series
that contains drift. Invalid input/config returns exit code `1`.

## Build a baseline

```bash
python -m tests.eval_mandate27.baseline normal-observations.jsonl \
  --output baseline.json \
  --model-id us.amazon.nova-2-lite-v1:0 \
  --guardrail-version 3 \
  --scorer-version mandate14-v2
```

Fewer than 50 samples for a metric/surface are retained for diagnosis but are
marked not ready. Replay then fails closed with `baseline_insufficient`.
A model, guardrail or scorer version mismatch returns `baseline_incompatible`.

## Reuse Mandate 14 reports

```bash
python -m tests.eval_mandate27.adapters.mandate14 \
  run-01/results.json run-02/results.json \
  --model-id us.amazon.nova-2-lite-v1:0 \
  --guardrail-version 3 \
  --output /tmp/m27-quality-observations.jsonl
```

The adapter retains only per-case surface, abstention and faithfulness. It does
not copy response, source or caller content into the drift contract.

## False-alarm controls

- minimum 50 baseline samples per metric/surface;
- 30-observation rolling window evaluated every 10 observations;
- adverse effect-size gate plus Wilson interval/Jensen-Shannon gate;
- two consecutive breached windows before a signal;
- model/guardrail/scorer compatibility gate;
- low traffic reports `warming_up`, never `no_drift`.

Thresholds and bin edges live inside the versioned baseline. Changing them
requires rebuilding and reviewing a new baseline.

