// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import ProductCatalogGateway from '../gateways/rpc/ProductCatalog.gateway';
import CurrencyGateway from '../gateways/rpc/Currency.gateway';
import { Money } from '../protos/demo';

const defaultCurrencyCode = 'USD';

const ProductCatalogService = () => ({
  async getProductPrice(price: Money, currencyCode: string) {
    return !!currencyCode && currencyCode !== defaultCurrencyCode
      ? await CurrencyGateway.convert(price, currencyCode)
      : price;
  },
  async listProducts(currencyCode = 'USD') {
    const { products: productList } = await ProductCatalogGateway.listProducts();

    if (!currencyCode || currencyCode === defaultCurrencyCode || productList.length === 0) {
      return productList;
    }

    const convertedPrices = await CurrencyGateway.batchConvert(
      productList.map(product => product.priceUsd!),
      currencyCode
    );

    if (convertedPrices.length !== productList.length) {
      throw new Error('Currency conversion response does not match product count');
    }

    return productList.map((product, index) => ({
      ...product,
      priceUsd: convertedPrices[index],
    }));
  },
  async getProduct(id: string, currencyCode = 'USD') {
    const product = await ProductCatalogGateway.getProduct(id);

    return {
      ...product,
      priceUsd: await this.getProductPrice(product.priceUsd!, currencyCode),
    };
  },
  async getProductForDisplay(id: string) {
    const { name, picture, categories } = await ProductCatalogGateway.getProduct(id);

    return { name, picture, categories };
  },
});

export default ProductCatalogService();
