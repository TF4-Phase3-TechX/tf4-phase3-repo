# ADR-025: Bounded retry, circuit breaker, and controlled AI fallback

- Date: 2026-07-27
- Status: Proposed; named reviewer acceptance pending
- Accountable owner: Tất Văn
- Jira: TF4AIO-86

## Context

Product Reviews calls Amazon Bedrock for grounded product Q&A. Provider
timeouts, throttling, 5xx responses, and malformed model output must not cause
an HTTP/gRPC 500, an unbounded retry storm, fabricated content, or an invalid
tool execution.

The team also needs an external fault drill. The protected BTC-owned flagd
source is not an application test database and must not be mutated by this
workstream.

## Decision

1. Disable hidden SDK retries (`max_attempts=0`) and own a visible application
   retry loop. A request makes at most two attempts with a bounded exponential
   backoff inside the existing application deadline.
2. Normalize Bedrock `ClientError` codes before circuit accounting. Only
   availability failures (timeout, throttling, provider 5xx) trip the breaker;
   malformed content does not.
3. Open the in-process breaker after five failed requests in 30 seconds,
   fast-fail during a 60-second cooldown, and allow recovery after cooldown.
4. Return the existing honest unavailable/insufficient responses. A malformed
   `emit_grounded_answer` payload is validated as data and cannot execute a
   cart/catalog mutation.
5. Provide a dedicated application-owned gRPC control:
   `tf4.mandate25.ResilienceControl`.
   - `SetFault` requires `MANDATE25_FAULT_TOKEN`;
   - modes are allow-listed;
   - TTL is mandatory and capped at 120 seconds;
   - state auto-restores to `off`;
   - `GetStatus` exposes only bounded fault/circuit/outcome metadata.
6. The drill helper must read back effective state and restore `off` in an
   exit trap. It never edits or publishes flagd.

## Trade-off

Application-owned retries and control are more code than delegating retries to
the SDK or mutating feature flags. In return, retry count, latency, circuit
accounting, injection lifetime, and restoration are deterministic and directly
testable. The control token is an additional secret; when absent, fault
mutation fails closed while normal AI traffic remains available.

## Rejected alternatives

- SDK retries: rejected because individual attempts and total latency are
  harder to reconstruct and cap.
- Protected flagd mutation: rejected because it violates ownership boundaries
  and couples a grading drill to a shared runtime control plane.
- Magic user prompts: rejected because an end user could accidentally or
  intentionally trigger a production fault.
- Opening the circuit on malformed output: rejected because content/schema
  failure is not provider unavailability.

## Activation and rollback

Activation requires a reviewed image, a dedicated control Secret, an external
replay tied to the deployed SHA, and named ADR acceptance. Rollback removes the
control-token Secret or rolls back the image; without the token, `SetFault`
remains disabled.
