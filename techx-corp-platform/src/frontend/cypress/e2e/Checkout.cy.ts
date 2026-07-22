// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import getSymbolFromCurrency from 'currency-symbol-map';
import { getElementByField } from '../../utils/Cypress';
import { CypressFields } from '../../utils/enums/CypressFields';

type CheckoutResponse = {
  orderId: string;
  shippingCost: { units: number; nanos: number; currencyCode: string };
  items: Array<{
    cost: { units: number; nanos: number; currencyCode: string };
    item: { productId: string; quantity: number; product: Record<string, unknown> };
  }>;
};

const moneyToNanos = ({ units, nanos }: { units: number; nanos: number }) => Number(units) * 1_000_000_000 + Number(nanos);

describe('Checkout Flow', () => {
  before(() => {
    cy.intercept('POST', '/api/cart*').as('addToCart');
    cy.intercept('GET', '/api/cart*').as('getCart');
    cy.intercept('POST', '/api/checkout*').as('placeOrder');
  });

  beforeEach(() => {
    cy.visit('/');
  });

  const addFirstAndLastProductsToCart = () => {
    getElementByField(CypressFields.ProductCard).first().click();
    getElementByField(CypressFields.ProductAddToCart).click();
    cy.wait('@addToCart');
    cy.wait('@getCart', { timeout: 10000 });

    cy.visit('/');
    getElementByField(CypressFields.ProductCard).last().click();
    getElementByField(CypressFields.ProductAddToCart).click();
    cy.wait('@addToCart');
    cy.wait('@getCart', { timeout: 10000 });

    getElementByField(CypressFields.CartIcon).click({ force: true });
    getElementByField(CypressFields.CartGoToShopping).click();
  };

  it('preserves authoritative non-USD amounts while hydrating display-only products', () => {
    getElementByField(CypressFields.CurrencySwitcher).select('EUR');
    addFirstAndLastProductsToCart();
    getElementByField(CypressFields.CheckoutPlaceOrder).click();

    cy.wait('@placeOrder').then(({ request, response }) => {
      const order = response?.body as CheckoutResponse;
      expect(request.url).to.include('currencyCode=EUR');
      expect(response?.statusCode).to.equal(200);
      expect(order.orderId).to.be.a('string').and.not.be.empty;
      expect(order.items).to.have.length(2);
      expect(order.shippingCost.currencyCode).to.equal('EUR');

      order.items.forEach(({ cost, item }) => {
        expect(item.productId).to.be.a('string').and.not.be.empty;
        expect(item.quantity).to.equal(1);
        expect(cost.currencyCode).to.equal('EUR');
        expect(item.product).to.have.all.keys('name', 'picture', 'categories');
        expect(item.product).not.to.have.property('priceUsd');
      });

      const total = order.items.reduce(
        (nanos, { cost, item }) => nanos + moneyToNanos(cost) * item.quantity,
        moneyToNanos(order.shippingCost)
      );
      const expectedTotal = `${getSymbolFromCurrency('EUR')} ${(total / 1_000_000_000).toFixed(2)}`;

      cy.location('href').should('match', new RegExp(`/checkout/${order.orderId}`));
      getElementByField(CypressFields.CheckoutItem).should('have.length', order.items.length).each(($item, index) => {
        expect($item).to.contain(String(order.items[index].item.product.name));
      });
      getElementByField(CypressFields.ProductPrice).last().should('have.text', expectedTotal);
    });
  });
});

export {};
