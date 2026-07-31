# Runbook: AI model-quality drift

## Trigger

- `AIQualityFallbackDrift`
- `AIQualityAbstentionDrift`
- `AIQualityVersionMetadataMissing`
- a `mandate27-drift-signal-v1` replay result

The signal is warning-only. Do not automatically retrain, change models,
disable safety controls or modify flagd.

## Triage

1. Record alert start time, `ai_surface`, metric and current/baseline values.
2. Confirm `app_ai_quality:requests_30m >= 30` and that `model_id`,
   `guardrail_version`, and `scorer_version` are configured; treat missing
   telemetry or identity as coverage degradation, not healthy quality.
3. Check whether model ID, guardrail, prompt/scorer contract or deployment
   revision changed after the baseline.
4. For fallback drift, correlate provider errors, throttling, circuit state and
   Mandate 25 resilience evidence.
5. For abstention drift, run the current M14 external suite and inspect
   category-level outcomes; do not inspect or export raw production content.
6. Replay a bounded observation series:

   ```bash
   python -m tests.eval_mandate27.replay series.jsonl \
     --baseline baseline.json \
     --output report.json
   ```

7. Escalate only when two independent windows or the deterministic replay
   confirm the same surface/metric.
8. Preserve the alert-start rates and version labels. The online seven-day
   companion is rolling and may absorb a shift after seven days; it must not be
   used alone to close a long-lived incident.

## Mitigation

- Provider/reliability cause: follow the Mandate 25 runbook and preserve safe
  fallback behavior.
- Guardrail/config regression: roll back through the reviewed deployment path.
- Semantic quality regression: stop promotion and open a model/prompt
  remediation task with M14 before/after evidence.
- Traffic-mix change: collect a new approved normal window; do not overwrite
  the active baseline until review confirms it is expected behavior.

## Recovery

The offline detector records recovery after three clean windows and resets the
episode state so a later independent drift emits a new signal. The online alert
resolves only after the Prometheus expression clears. Capture the resolved
timestamp and rerun both stable and shifted controls.

Rebuild a baseline only after an intentional approved change. Record Git SHA,
model ID, guardrail version, scorer version, dataset hash, sample count and
baseline checksum.

If a surface or baseline-bound metric disappears, stop with
`baseline_insufficient`; never translate absent observations to `no_drift`.
