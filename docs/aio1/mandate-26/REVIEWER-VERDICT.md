# Mandate 26 — Reviewer Verdict

**Jira:** [TF4AIO-90](https://aio1-xbrain.atlassian.net/browse/TF4AIO-90)

## Instructions for the reviewer

1. Check out the Git revision under review.
2. Rerun the one-command repro from `MANDATE-26-EVIDENCE-INDEX.md`.
3. Confirm exit code `0`, Root@1 on cascade cases, and noise classification on `payment-cascade-with-ad-noise`.
4. Skim `ADR-026-rca-root-cause-attribution.md` for mechanism, trade-offs, and limitations.
5. Fill the table below and set the verdict.

## Verdict record

| Field | Value |
|---|---|
| Reviewer full name | _pending_ |
| Date/time (UTC) | _pending_ |
| Reviewed Git revision | _pending_ |
| Exact rerun command | `py -3 techx-corp-platform/src/aiops/benchmark/rca_replay.py docs/aio1/mandate-26/rca-labeled-scenarios-v1.jsonl --output docs/aio1/mandate-26/rca-replay-report-v1.json --force` |
| Observed report SHA-256 | _pending_ |
| Observed exit code | _pending_ |
| **Verdict** | **Pending** (`Approved` \| `Changes Requested`) |

## Checklist

- [ ] External replay accepts JSONL with Jaeger and/or normalized traces  
- [ ] Ranking + single suspected root on supported cascades  
- [ ] Explanation cites evidence; does not stop at a pure downstream symptom  
- [ ] Correlated-noise case present; noisy service not selected as root  
- [ ] At least one unseen topology/service-name case  
- [ ] Labels isolated from engine input  
- [ ] flagd not touched; remediation target unchanged  
- [ ] Machine-readable report includes input hash, git revision, limitations  
- [ ] ADR documents uncertainty and non-goals  

## Remaining limitations / uncertainty (reviewer notes)

_To be filled by reviewer._

## Signature

```
Reviewer: ______________________________
Verdict:  ______________________________
Date:     ______________________________
```
