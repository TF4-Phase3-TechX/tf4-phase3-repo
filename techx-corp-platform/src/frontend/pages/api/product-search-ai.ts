// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import type { NextApiRequest, NextApiResponse } from 'next';
import InstrumentationMiddleware from '../../utils/telemetry/InstrumentationMiddleware';
import ProductReviewGateway from '../../gateways/rpc/ProductReview.gateway';

const handler = async ({ method, body }: NextApiRequest, res: NextApiResponse) => {
    switch (method) {
        case 'POST': {
            const { query = '', sessionId = '' } = body;
            const response = await ProductReviewGateway.searchProductsAIAssistant(query, sessionId);
            return res.status(200).json(response);
        }
        default: {
            return res.status(405).send('');
        }
    }
};

export default InstrumentationMiddleware(handler);
