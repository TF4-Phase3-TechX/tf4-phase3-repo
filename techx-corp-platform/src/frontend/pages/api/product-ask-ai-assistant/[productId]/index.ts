// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import type { NextApiRequest, NextApiResponse } from 'next';
import InstrumentationMiddleware from '../../../../utils/telemetry/InstrumentationMiddleware';
import {Empty} from '../../../../protos/demo';
import ProductReviewService from '../../../../services/ProductReview.service';
import { projectAiResponse } from '../../../../utils/aiDebugMetadata';
import { serverAiPrincipal } from '../../../../utils/serverAiPrincipal';

type TResponse = string | Empty | Record<string, unknown>;

const handler = async (req: NextApiRequest, res: NextApiResponse<TResponse>) => {
    const { method, body, query } = req;

    switch (method) {
        case 'POST': {
            const { productId = '' } = query;
            const { question = '', sessionId = '' } = body;
            if (![question, sessionId].every((value) => typeof value === 'string' && value.length > 0)) {
                return res.status(400).json({} as Empty);
            }
            const userId = serverAiPrincipal(req, res);

            const response = await ProductReviewService.askProductAIAssistant(
                productId as string,
                question,
                sessionId,
                userId,
            );

            return res.status(200).json(projectAiResponse(response));
        }

        default: {
            return res.status(405).send('');
        }
    }
};

export default InstrumentationMiddleware(handler);
