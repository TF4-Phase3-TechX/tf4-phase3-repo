// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { ChannelCredentials } from '@grpc/grpc-js';
import {
    ProductReview,
    ProductReviewServiceClient,
    SearchProductsAIAssistantRequest,
    SearchProductsAIAssistantResponse,
} from '../../protos/demo';

const { PRODUCT_REVIEWS_ADDR = '' } = process.env;

const client = new ProductReviewServiceClient(PRODUCT_REVIEWS_ADDR, ChannelCredentials.createInsecure());

const ProductReviewGateway = () => ({

    getProductReviews(productId: string) {
        return new Promise<ProductReview []>((resolve, reject) =>
            client.getProductReviews({ productId }, (error, response) => (error ? reject(error) : resolve(response.productReviews)))
        );
    },
    getAverageProductReviewScore(productId: string) {
        return new Promise<string>((resolve, reject) =>
            client.getAverageProductReviewScore({ productId }, (error, response) => (error ? reject(error) : resolve(response.averageScore)))
        );
    },
    askProductAIAssistant(productId: string, question: string, sessionId: string = '') {
        return new Promise<any>((resolve, reject) =>
            client.askProductAiAssistant({ productId, question, sessionId }, (error, response) => (error ? reject(error) : resolve(response)))
        );
    },
    searchProductsAIAssistant(query: string, sessionId: string = '') {
        return new Promise<any>((resolve, reject) => {
            (client as any).makeUnaryRequest(
                '/oteldemo.ProductReviewService/SearchProductsAIAssistant',
                (value: any) => Buffer.from(SearchProductsAIAssistantRequest.encode(value).finish()),
                (value: Buffer) => SearchProductsAIAssistantResponse.decode(value),
                { query, sessionId },
                (error: any, response: any) => (error ? reject(error) : resolve(response))
            );
        });
    },
});

export default ProductReviewGateway();
