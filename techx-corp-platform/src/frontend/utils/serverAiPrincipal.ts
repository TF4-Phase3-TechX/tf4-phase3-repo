// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { createHmac, randomUUID, timingSafeEqual } from 'crypto';
import type { NextApiRequest, NextApiResponse } from 'next';

const COOKIE_NAME = 'tf4_ai_principal';
const MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

const signingSecret = (): string => {
  const configured = process.env.AI_PRINCIPAL_HMAC_SECRET || '';
  if (configured) return configured;
  if ((process.env.NODE_ENV || '').toLowerCase() === 'production') {
    throw new Error('AI_PRINCIPAL_HMAC_SECRET is required in production');
  }
  return 'local-development-only';
};

const signature = (principal: string): string =>
  createHmac('sha256', signingSecret()).update(principal).digest('base64url');

const encode = (principal: string): string => `${principal}.${signature(principal)}`;

const decode = (value: string | undefined): string | null => {
  if (!value) return null;
  const separator = value.lastIndexOf('.');
  if (separator <= 0) return null;
  const principal = value.slice(0, separator);
  const supplied = value.slice(separator + 1);
  const expected = signature(principal);
  if (!/^[0-9a-f-]{36}$/.test(principal) || supplied.length !== expected.length) return null;
  return timingSafeEqual(Buffer.from(supplied), Buffer.from(expected)) ? principal : null;
};

export const serverAiPrincipal = (req: NextApiRequest, res: NextApiResponse): string => {
  const existing = decode(req.cookies[COOKIE_NAME]);
  if (existing) return existing;

  const principal = randomUUID();
  const secure = process.env.NODE_ENV === 'production' ? '; Secure' : '';
  res.setHeader(
    'Set-Cookie',
    `${COOKIE_NAME}=${encode(principal)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${MAX_AGE_SECONDS}${secure}`,
  );
  return principal;
};
