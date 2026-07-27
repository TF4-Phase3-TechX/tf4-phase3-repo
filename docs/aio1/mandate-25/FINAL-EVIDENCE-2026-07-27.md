# Mandate 25 evidence packet — 2026-07-27

Canonical Jira: [TF4AIO-86](https://aio1-xbrain.atlassian.net/browse/TF4AIO-86)

## Current verdict

Evidence level 3: implemented and tested offline. No level-4 deployment,
level-5 runtime observation, or level-6 acceptance is claimed.

## Implemented artifact

- explicit capped retry/backoff in `bedrock_adapter.py`;
- normalized provider error and circuit state contract;
- `resilience_control.py` token/TTL/readback/auto-expiry control;
- `inject_mandate25_faults.sh` bounded external drill wrapper;
- `tests/eval_mandate25/replay.py` standalone external request/status replay;
- provider/circuit-aware frontend health route;
- offline tests for retry cap, ClientError normalization, open/fast-fail,
  cooldown recovery, malformed-output no-action, authorization, TTL expiry,
  external gRPC readback, and restoration.

## Safety boundary

This implementation does not mutate flagd. `SetFault` fails closed when the
dedicated token is absent. Fault state is process-local, allow-listed, and
expires after at most 120 seconds.

## Still required

- merge and deploy the reviewed SHA;
- provision the dedicated control Secret through the approved path;
- run timeout/429/5xx and malformed-output drills externally;
- capture exact attempts, latency, fallback, breaker-open, fast-fail,
  recovery, no-action, and final `off` readback;
- obtain named ADR acceptance.

The control script and offline tests are not runtime evidence.
