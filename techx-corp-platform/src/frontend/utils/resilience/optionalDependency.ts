// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

export interface OptionalDependencyOptions<T> {
  execute: () => Promise<T>;
  fallback: T;
  onFallback: (error: unknown) => void;
}

/**
 * Executes an optional dependency and deliberately degrades to a safe value.
 * Observability is injected so the helper remains independent from a specific
 * metrics or logging implementation.
 */
export async function optionalDependencyFallback<T>({
  execute,
  fallback,
  onFallback,
}: OptionalDependencyOptions<T>): Promise<T> {
  try {
    return await execute();
  } catch (error: unknown) {
    onFallback(error);
    return fallback;
  }
}
