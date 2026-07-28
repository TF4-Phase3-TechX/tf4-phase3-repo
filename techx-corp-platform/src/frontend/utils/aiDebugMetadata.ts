// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

export interface AiDebugMetadata {
  cacheStatus: string;
  cacheEligible: boolean;
  cacheReason: string;
  modelCalls: number;
  inputTokens: number;
  outputTokens: number;
  estimatedCostUsd: number;
  latencyMs: number;
  memoryStatus: string;
}

const DEBUG_FIELDS = [
  'cacheStatus',
  'cacheEligible',
  'cacheReason',
  'modelCalls',
  'inputTokens',
  'outputTokens',
  'estimatedCostUsd',
  'latencyMs',
  'memoryStatus',
] as const;

export const isAiDebugMetadataEnabled = (
  value: string | undefined = process.env.AI_DEBUG_METADATA_ENABLED,
): boolean => value?.trim().toLowerCase() === 'true';

export const projectAiResponse = (
  response: object,
  enabled: boolean = isAiDebugMetadataEnabled(),
): Record<string, unknown> => {
  const source = response as Record<string, unknown>;
  const publicResponse = { ...source };
  for (const field of DEBUG_FIELDS) {
    delete publicResponse[field];
  }

  if (!enabled) {
    return publicResponse;
  }

  const aiDebug: AiDebugMetadata = {
    cacheStatus: String(source.cacheStatus || 'miss'),
    cacheEligible: Boolean(source.cacheEligible),
    cacheReason: String(source.cacheReason || ''),
    modelCalls: Number(source.modelCalls || 0),
    inputTokens: Number(source.inputTokens || 0),
    outputTokens: Number(source.outputTokens || 0),
    estimatedCostUsd: Number(source.estimatedCostUsd || 0),
    latencyMs: Number(source.latencyMs || 0),
    memoryStatus: String(source.memoryStatus || ''),
  };

  return { ...publicResponse, aiDebug };
};
