// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import ProductCatalogGateway from '../gateways/rpc/ProductCatalog.gateway';
import CurrencyGateway from '../gateways/rpc/Currency.gateway';
import { Money } from '../protos/demo';

const defaultCurrencyCode = 'USD';
const maxConcurrentCurrencyConversions = 4;

async function mapWithConcurrency<T, R>(
  items: readonly T[],
  concurrency: number,
  mapper: (item: T) => Promise<R>
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let nextIndex = 0;
  const worker = async () => {
    while (nextIndex < items.length) {
      const index = nextIndex++;
      results[index] = await mapper(items[index]);
    }
  };

  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, worker));
  return results;
}

const ProductCatalogService = () => ({
  async getProductPrice(price: Money, currencyCode: string) {
    return !!currencyCode && currencyCode !== defaultCurrencyCode
      ? await CurrencyGateway.convert(price, currencyCode)
      : price;
  },
  async listProducts(currencyCode = 'USD') {
    const { products: productList } = await ProductCatalogGateway.listProducts();

    return mapWithConcurrency(productList, maxConcurrentCurrencyConversions, async product => {
      const priceUsd = await this.getProductPrice(product.priceUsd!, currencyCode);

      return {
        ...product,
        priceUsd,
      };
    });
  },
  async getProduct(id: string, currencyCode = 'USD') {
    const product = await ProductCatalogGateway.getProduct(id);

    return {
      ...product,
      priceUsd: await this.getProductPrice(product.priceUsd!, currencyCode),
    };
  },
});

export default ProductCatalogService();
