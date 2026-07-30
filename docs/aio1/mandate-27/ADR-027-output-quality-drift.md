# ADR-027: Content-free output-quality drift detection

- Status: Accepted for implementation
- Date: 2026-07-30
- Owner: AIO1
- Scope: Product review summary and Shopping Copilot

## Context

Mandate 27 requires a normal baseline, a signal that names the drifting
surface/metric/time, an external replay entry, and evidence that ordinary
variation does not cause false alarms.

The production path already emits bounded model outcome metadata and Mandate 14
provides a deterministic scorer. Online prompt/response capture is disabled and
must remain disabled.

## Decision

Use output-quality drift rather than embedding drift:

- online proxies: fallback and abstention rates;
- controlled evaluation metric: Mandate 14 faithfulness;
- canonical surfaces: `review_summary` and `copilot`;
- no raw prompt, response, identity or source content in the drift contract.

Binary rates use a one-sided 99% Wilson interval plus a minimum adverse delta.
Faithfulness uses fixed-bin Jensen-Shannon divergence plus a minimum mean drop.
A signal requires two consecutive breached rolling windows. Low sample counts
and version mismatches fail closed rather than claiming no drift.

The external JSONL replay is the reproducible source of truth. Prometheus
recording/alert rules provide an operational companion using the same bounded
outcome metric, a 30-request gate, seven-day historical baseline and 30-minute
persistence.

## Consequences

- Detection adds no Bedrock calls and negligible counter overhead.
- The system can name the exact surface and quality proxy without retaining
  customer content.
- Fallback drift may be caused by provider reliability rather than semantic
  degradation; the signal intentionally names the proxy and the runbook
  requires correlation before intervention.
- Faithfulness is available from controlled M14 evaluation, not every live
  request.
- A deliberate model, guardrail or scorer change requires a reviewed baseline
  refresh; the detector never silently learns an active drift into normality.

## Rejected alternatives

- Online embeddings: additional cost, latency and content-processing risk.
- LLM-as-judge on every request: non-deterministic, expensive and susceptible
  to judge drift.
- A single fixed rate threshold without minimum samples/persistence: too prone
  to false alarms during low traffic and transient provider failures.

