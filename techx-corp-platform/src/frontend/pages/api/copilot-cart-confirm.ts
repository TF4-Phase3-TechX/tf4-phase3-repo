// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import type { NextApiRequest, NextApiResponse } from 'next';
import ProductReviewGateway from '../../gateways/rpc/ProductReview.gateway';
import InstrumentationMiddleware from '../../utils/telemetry/InstrumentationMiddleware';
import { serverAiPrincipal } from '../../utils/serverAiPrincipal';

const handler = async (req: NextApiRequest, res: NextApiResponse) => {
  const { method, body } = req;
  if (method !== 'POST') return res.status(405).send('');

  const { sessionId = '', confirmationToken = '' } = body;
  if (![sessionId, confirmationToken].every((value) => typeof value === 'string' && value.length > 0)) {
    return res.status(400).json({ applied: false, outcome: 'invalid_request' });
  }

  const userId = serverAiPrincipal(req, res);
  const result = await ProductReviewGateway.confirmCartAction(userId, sessionId, confirmationToken);
  return res.status(result.applied ? 200 : 409).json(result);
};

export default InstrumentationMiddleware(handler);
