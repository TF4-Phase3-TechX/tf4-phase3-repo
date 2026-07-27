// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import test from 'node:test';
import {
  isAiDebugMetadataEnabled,
  projectAiResponse,
} from './aiDebugMetadata';
import {
  AskProductAIAssistantResponse,
  SearchProductsAIAssistantResponse,
} from '../protos/demo';

const response = {
  response: 'Grounded answer',
  outcome: 'answered',
  cacheStatus: 'hit',
  cacheEligible: true,
  cacheReason: 'hit',
  modelCalls: 0,
  inputTokens: 0,
  outputTokens: 0,
  estimatedCostUsd: 0,
  latencyMs: 8.5,
  memoryStatus: 'not_applicable',
};

test('debug metadata is disabled unless explicitly set to true', () => {
  assert.equal(isAiDebugMetadataEnabled(undefined), false);
  assert.equal(isAiDebugMetadataEnabled('false'), false);
  assert.equal(isAiDebugMetadataEnabled('1'), false);
  assert.equal(isAiDebugMetadataEnabled(' TRUE '), true);
});

test('disabled projection removes metadata from the browser response', () => {
  assert.deepEqual(projectAiResponse(response, false), {
    response: 'Grounded answer',
    outcome: 'answered',
  });
});

test('enabled projection returns metadata only under aiDebug', () => {
  assert.deepEqual(projectAiResponse(response, true), {
    response: 'Grounded answer',
    outcome: 'answered',
    aiDebug: {
      cacheStatus: 'hit',
      cacheEligible: true,
      cacheReason: 'hit',
      modelCalls: 0,
      inputTokens: 0,
      outputTokens: 0,
      estimatedCostUsd: 0,
      latencyMs: 8.5,
      memoryStatus: 'not_applicable',
    },
  });
});

test('generated Product Q&A codec preserves diagnostics fields', () => {
  const encoded = AskProductAIAssistantResponse.encode({
    response: 'Grounded answer',
    actionProposal: undefined,
    cacheStatus: 'hit',
    cacheEligible: true,
    cacheReason: 'hit',
    modelCalls: 0,
    inputTokens: 0,
    outputTokens: 0,
    estimatedCostUsd: 0,
    latencyMs: 8.5,
    memoryStatus: 'not_applicable',
  }).finish();

  const decoded = AskProductAIAssistantResponse.decode(encoded);
  assert.equal(decoded.cacheStatus, 'hit');
  assert.equal(decoded.cacheEligible, true);
  assert.equal(decoded.latencyMs, 8.5);
  assert.equal(decoded.memoryStatus, 'not_applicable');
});

test('generated Copilot codec preserves diagnostics fields', () => {
  const encoded = SearchProductsAIAssistantResponse.encode({
    results: [],
    trace: undefined,
    actionProposal: undefined,
    response: 'Remembered preference',
    outcome: 'answered',
    cacheStatus: 'miss',
    cacheEligible: false,
    cacheReason: 'profile_dependent',
    modelCalls: 0,
    inputTokens: 0,
    outputTokens: 0,
    estimatedCostUsd: 0,
    latencyMs: 3.25,
    memoryStatus: 'recalled',
  }).finish();

  const decoded = SearchProductsAIAssistantResponse.decode(encoded);
  assert.equal(decoded.cacheStatus, 'miss');
  assert.equal(decoded.cacheReason, 'profile_dependent');
  assert.equal(decoded.latencyMs, 3.25);
  assert.equal(decoded.memoryStatus, 'recalled');
});
