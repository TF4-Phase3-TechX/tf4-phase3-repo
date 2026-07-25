// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { optionalDependencyFallback } from './optionalDependency';

test('returns the dependency response without activating fallback', async () => {
  let fallbackCount = 0;
  const response = await optionalDependencyFallback({
    execute: async () => ['ad-1'],
    fallback: [] as string[],
    onFallback: () => fallbackCount++,
  });

  assert.deepEqual(response, ['ad-1']);
  assert.equal(fallbackCount, 0);
});

test('returns the safe value and records fallback when dependency fails', async () => {
  const dependencyError = new Error('deadline exceeded');
  let observedError: unknown;
  const response = await optionalDependencyFallback<never[]>({
    execute: async () => {
      throw dependencyError;
    },
    fallback: [],
    onFallback: error => {
      observedError = error;
    },
  });

  assert.deepEqual(response, []);
  assert.equal(observedError, dependencyError);
});
