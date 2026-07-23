// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import type { NextApiRequest, NextApiResponse } from 'next';
import InstrumentationMiddleware from '../../../../utils/telemetry/InstrumentationMiddleware';
import {Empty} from '../../../../protos/demo';
import ProductReviewService from '../../../../services/ProductReview.service';

type TResponse = string | Empty;

const handler = async ({ method, body, query }: NextApiRequest, res: NextApiResponse<TResponse>) => {

    switch (method) {
        case 'POST': {
            const { productId = '' } = query;
            const { question = '', sessionId = '', userId = '' } = body;
            if (![question, sessionId, userId].every((value) => typeof value === 'string' && value.length > 0)) {
                return res.status(400).json({} as Empty);
            }

            const response = await ProductReviewService.askProductAIAssistant(
                productId as string,
                question,
                sessionId,
                userId,
            );

            return res.status(200).json(response);
        }

        default: {
            return res.status(405).send('');
        }
    }
};

export default InstrumentationMiddleware(handler);
