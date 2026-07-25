// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import {Address, Cart, OrderItem, OrderResult, Product, ProductDisplay} from '../protos/demo';

export interface IProductCartItem {
  productId: string;
  quantity: number;
  product: Product;
}

export interface IProductCheckoutItem extends Omit<OrderItem, 'item' | 'productDisplay'> {
  item: Omit<IProductCartItem, 'product'> & { product: ProductDisplay };
}

export interface IProductCheckout extends Omit<OrderResult, 'items'> {
  items: IProductCheckoutItem[];
  shippingAddress: Address;
}

export interface IProductCart extends Cart {
  items: IProductCartItem[];
}
