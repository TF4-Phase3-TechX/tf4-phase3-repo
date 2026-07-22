// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { ChannelCredentials } from '@grpc/grpc-js';
import {
    ProductReview,
    ProductReviewServiceClient,
    ConfirmCartActionRequest,
    ConfirmCartActionResponse,
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
    askProductAIAssistant(productId: string, question: string, sessionId: string = '', userId: string = '') {
        return new Promise<any>((resolve, reject) =>
            client.askProductAiAssistant({ productId, question, sessionId, userId }, (error, response) => (error ? reject(error) : resolve(response)))
        );
    },
    searchProductsAIAssistant(query: string, sessionId: string = '', userId: string = '') {
        return new Promise<any>((resolve, reject) => {
            (client as any).makeUnaryRequest(
                '/oteldemo.ProductReviewService/SearchProductsAIAssistant',
                (value: any) => Buffer.from(SearchProductsAIAssistantRequest.encode(value).finish()),
                (value: Buffer) => SearchProductsAIAssistantResponse.decode(value),
                { query, sessionId, userId },
                (error: any, response: any) => (error ? reject(error) : resolve(response))
            );
        });
    },
    confirmCartAction(userId: string, sessionId: string, confirmationToken: string) {
        return new Promise<ConfirmCartActionResponse>((resolve, reject) => {
            client.makeUnaryRequest(
                '/oteldemo.ProductReviewService/ConfirmCartAction',
                (value: ConfirmCartActionRequest) => Buffer.from(ConfirmCartActionRequest.encode(value).finish()),
                (value: Buffer) => ConfirmCartActionResponse.decode(value),
                { userId, sessionId, confirmationToken },
                (error, response) => (error ? reject(error) : response ? resolve(response) : reject(new Error('Empty confirmation response')))
            );
        });
    },
});

export default ProductReviewGateway();
