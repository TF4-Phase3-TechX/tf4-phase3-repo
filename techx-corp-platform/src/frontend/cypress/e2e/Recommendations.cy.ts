// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { getElementByField } from '../../utils/Cypress';
import { CypressFields } from '../../utils/enums/CypressFields';

describe('Recommendations requests', () => {
  it('does not request recommendations for an empty cart', () => {
    cy.intercept('GET', '/api/recommendations*').as('getRecommendations');

    cy.visit('/cart');

    cy.get('@getRecommendations.all').should('have.length', 0);
  });

  it('only sends normalized product IDs and changes the request for a currency transition', () => {
    cy.intercept('GET', '/api/recommendations*').as('getRecommendations');

    cy.visit('/');
    getElementByField(CypressFields.ProductCard).first().click();
    cy.wait('@getRecommendations').then(({ request: firstRequest }) => {
      expect(new URL(firstRequest.url).searchParams.get('productIds')).to.match(/\S/);
    });
    cy.get('@getRecommendations.all').should('have.length', 1);

    getElementByField(CypressFields.CurrencySwitcher).select('EUR');
    cy.wait('@getRecommendations').then(({ request: currencyRequest }) => {
      const query = new URL(currencyRequest.url).searchParams;
      expect(query.get('productIds')).to.match(/\S/);
      expect(query.get('currencyCode')).to.equal('EUR');
    });
  });

  it('rejects missing and blank product IDs before recommendation work', () => {
    cy.request({ failOnStatusCode: false, url: '/api/recommendations' }).its('status').should('equal', 400);
    cy.request({ failOnStatusCode: false, url: '/api/recommendations?productIds=%20%20&productIds=' })
      .its('status')
      .should('equal', 400);
  });

  it('accepts valid string and repeated productIds query values', () => {
    const sessionId = 'recommendations-cypress-session';

    cy.request({
      url: `/api/recommendations?productIds=OLJCESPC7Z&sessionId=${sessionId}&currencyCode=USD`,
      timeout: 10000,
    })
      .its('status')
      .should('equal', 200);
    cy.request({
      url: `/api/recommendations?productIds=OLJCESPC7Z&productIds=66VCHSJNUP&sessionId=${sessionId}&currencyCode=USD`,
      timeout: 10000,
    })
      .its('status')
      .should('equal', 200);
  });
});

export {};
