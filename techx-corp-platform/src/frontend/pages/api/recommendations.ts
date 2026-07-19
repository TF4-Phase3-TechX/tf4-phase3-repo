// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import type { NextApiRequest, NextApiResponse } from 'next';
import InstrumentationMiddleware from '../../utils/telemetry/InstrumentationMiddleware';
import RecommendationsGateway from '../../gateways/rpc/Recommendations.gateway';
import { Empty, Product } from '../../protos/demo';
import ProductCatalogService from '../../services/ProductCatalog.service';

type TResponse = Product[] | Empty;

const normalizeProductIds = (productIds: string | string[] | undefined) =>
  (Array.isArray(productIds) ? productIds : [productIds])
    .flatMap(productId => productId?.split(',') || [])
    .map(productId => productId.trim())
    .filter(Boolean);

const handler = async ({ method, query }: NextApiRequest, res: NextApiResponse<TResponse>) => {
  switch (method) {
    case 'GET': {
      const { productIds, sessionId = '', currencyCode = '' } = query;
      const validProductIds = normalizeProductIds(productIds);

      if (validProductIds.length === 0) {
        return res.status(400).send('');
      }

      const { productIds: productList } = await RecommendationsGateway.listRecommendations(
        sessionId as string,
        validProductIds
      );
      const recommendedProductList = await Promise.all(
        productList.slice(0, 4).map(id => ProductCatalogService.getProduct(id, currencyCode as string))
      );

      return res.status(200).json(recommendedProductList);
    }

    default: {
      return res.status(405).send('');
    }
  }
};

export default InstrumentationMiddleware(handler);
