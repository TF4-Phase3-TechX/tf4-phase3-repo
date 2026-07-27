import assert from 'node:assert/strict';
import test from 'node:test';
import type { NextApiRequest, NextApiResponse } from 'next';
import ProductReviewService from '../services/ProductReview.service';
import { handler } from '../pages/api/product-ask-ai-assistant/[productId]';

type ResponseDouble = NextApiResponse & {
  cookie?: string;
  payload?: unknown;
};

const responseDouble = (): ResponseDouble => {
  const response: any = {
    statusCode: 200,
    setHeader: (name: string, value: string) => {
      if (name === 'Set-Cookie') response.cookie = value;
    },
    status: (statusCode: number) => {
      response.statusCode = statusCode;
      return response;
    },
    json: (payload: unknown) => {
      response.payload = payload;
      return response;
    },
    send: () => response,
  };
  return response as ResponseDouble;
};

test('product AI route ignores a spoofed body userId and preserves the signed principal', async () => {
  process.env.AI_PRINCIPAL_HMAC_SECRET = 'test-principal-secret';
  const original = ProductReviewService.askProductAIAssistant;
  const captured: string[] = [];
  ProductReviewService.askProductAIAssistant = async (...args: any[]) => {
    captured.push(args[3]);
    return { response: 'ok' };
  };

  try {
    const firstResponse = responseDouble();
    await handler(
      {
        method: 'POST',
        query: { productId: 'OLJCESPC7Z' },
        cookies: {},
        body: { question: 'What do reviews say?', sessionId: 'session-a', userId: 'victim-user' },
      } as unknown as NextApiRequest,
      firstResponse,
    );
    assert.notEqual(captured[0], 'victim-user');
    assert.ok(firstResponse.cookie);

    const signedPrincipal = firstResponse.cookie!.split(';', 1)[0].split('=', 2)[1];
    await handler(
      {
        method: 'POST',
        query: { productId: 'OLJCESPC7Z' },
        cookies: { tf4_ai_principal: signedPrincipal },
        body: { question: 'What do reviews say?', sessionId: 'session-a', userId: 'another-victim' },
      } as unknown as NextApiRequest,
      responseDouble(),
    );
    assert.equal(captured[1], captured[0]);
  } finally {
    ProductReviewService.askProductAIAssistant = original;
  }
});
