// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import type { NextApiRequest, NextApiResponse } from 'next';
import ProductReviewGateway from '../../gateways/rpc/ProductReview.gateway';
import InstrumentationMiddleware from '../../utils/telemetry/InstrumentationMiddleware';

const handler = async ({ method, body }: NextApiRequest, res: NextApiResponse) => {
  if (method !== 'POST') return res.status(405).send('');

  const { userId = '', sessionId = '', confirmationToken = '' } = body;
  if (![userId, sessionId, confirmationToken].every((value) => typeof value === 'string' && value.length > 0)) {
    return res.status(400).json({ applied: false, outcome: 'invalid_request' });
  }

  const result = await ProductReviewGateway.confirmCartAction(userId, sessionId, confirmationToken);
  return res.status(result.applied ? 200 : 409).json(result);
};

export default InstrumentationMiddleware(handler);
