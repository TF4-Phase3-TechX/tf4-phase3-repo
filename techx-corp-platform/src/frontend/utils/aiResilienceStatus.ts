export type ResiliencePayload = {
  fault?: {
    mode?: string;
    seconds_remaining?: number;
  };
  resilience?: {
    circuit_state?: string;
    last_provider_outcome?: string;
    last_provider_error?: string;
  };
};

const bounded = (value: unknown, fallback: string): string => {
  if (typeof value !== 'string' || !/^[a-z0-9_]{1,64}$/.test(value)) {
    return fallback;
  }
  return value;
};

export const decodeResiliencePayload = (buffer: Buffer): ResiliencePayload => {
  const parsed: unknown = JSON.parse(buffer.toString('utf8'));
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('invalid resilience response');
  }
  return parsed as ResiliencePayload;
};

export const publicResilienceStatus = (payload: ResiliencePayload) => {
  const circuitState = bounded(payload.resilience?.circuit_state, 'unknown');
  const lastProviderOutcome = bounded(
    payload.resilience?.last_provider_outcome,
    'unknown',
  );
  const lastProviderError = bounded(
    payload.resilience?.last_provider_error,
    'none',
  );
  const faultMode = bounded(payload.fault?.mode, 'off');
  const remaining = Number(payload.fault?.seconds_remaining ?? 0);
  const secondsRemaining = Number.isFinite(remaining)
    ? Math.max(0, Math.min(120, remaining))
    : 0;
  const degraded =
    circuitState !== 'closed' || lastProviderOutcome === 'error';

  return {
    status: degraded ? 'degraded' : 'healthy',
    circuitState,
    lastProviderOutcome,
    lastProviderError,
    faultMode,
    secondsRemaining,
  };
};
