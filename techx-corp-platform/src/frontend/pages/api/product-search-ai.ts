// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import type { NextApiRequest, NextApiResponse } from 'next';
import InstrumentationMiddleware from '../../utils/telemetry/InstrumentationMiddleware';
import ProductReviewGateway from '../../gateways/rpc/ProductReview.gateway';
import { projectAiResponse } from '../../utils/aiDebugMetadata';
import { serverAiPrincipal } from '../../utils/serverAiPrincipal';

const handler = async (req: NextApiRequest, res: NextApiResponse) => {
    const { method, body } = req;
    switch (method) {
        case 'POST': {
            const { query = '', sessionId = '' } = body;
            if (![query, sessionId].every((value) => typeof value === 'string') || !query.trim() || !sessionId) {
                return res.status(400).json({ error: 'query and sessionId are required' });
            }
            const userId = serverAiPrincipal(req, res);
            const response = await ProductReviewGateway.searchProductsAIAssistant(query, sessionId, userId);
            return res.status(200).json(projectAiResponse(response));
        }
        default: {
            return res.status(405).send('');
        }
    }
};

export default InstrumentationMiddleware(handler);
