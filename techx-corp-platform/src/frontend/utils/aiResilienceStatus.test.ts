import test from 'node:test';
import assert from 'node:assert/strict';

import {
  decodeResiliencePayload,
  publicResilienceStatus,
} from './aiResilienceStatus';

test('reports provider circuit state rather than gRPC transport readiness', () => {
  const status = publicResilienceStatus({
    fault: { mode: 'throttling', seconds_remaining: 12 },
    resilience: {
      circuit_state: 'open',
      last_provider_outcome: 'error',
      last_provider_error: 'throttlingexception',
    },
  });

  assert.equal(status.status, 'degraded');
  assert.equal(status.circuitState, 'open');
  assert.equal(status.faultMode, 'throttling');
});

test('bounds untrusted status fields', () => {
  const payload = decodeResiliencePayload(
    Buffer.from(
      JSON.stringify({
        fault: { mode: '<script>', seconds_remaining: 999 },
        resilience: {
          circuit_state: 'closed',
          last_provider_outcome: 'success',
        },
      }),
    ),
  );
  const status = publicResilienceStatus(payload);

  assert.equal(status.status, 'healthy');
  assert.equal(status.faultMode, 'off');
  assert.equal(status.secondsRemaining, 120);
});
