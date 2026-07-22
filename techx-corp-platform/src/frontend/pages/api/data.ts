// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import type { NextApiRequest, NextApiResponse } from 'next';
import InstrumentationMiddleware from '../../utils/telemetry/InstrumentationMiddleware';
import AdGateway from '../../gateways/rpc/Ad.gateway';
import { Ad, Empty } from '../../protos/demo';
import { metrics } from '@opentelemetry/api';
import { optionalDependencyFallback } from '../../utils/resilience/optionalDependency';

type TResponse = Ad[] | Empty;

const fallbackCounter = metrics.getMeter('frontend').createCounter('app.frontend.dependency_fallbacks', {
  description: 'Number of optional downstream calls replaced by a safe fallback',
});

const handler = async ({ method, query }: NextApiRequest, res: NextApiResponse<TResponse>) => {
  switch (method) {
    case 'GET': {
      const { contextKeys = [] } = query;
      const adList = await optionalDependencyFallback({
        execute: async () => {
          const { ads } = await AdGateway.listAds(Array.isArray(contextKeys) ? contextKeys : contextKeys.split(','));
          return ads;
        },
        fallback: [] as Ad[],
        onFallback: (error: unknown) => {
          fallbackCounter.add(1, { dependency: 'ad', operation: 'GetAds' });
          console.warn(
            JSON.stringify({
              event: 'optional_dependency_fallback',
              dependency: 'ad',
              operation: 'GetAds',
              error: error instanceof Error ? error.message : String(error),
            })
          );
        },
      });

      return res.status(200).json(adList);
    }

    default: {
      return res.status(405).send('');
    }
  }
};

export default InstrumentationMiddleware(handler);
