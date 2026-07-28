import { NextApiRequest, NextApiResponse } from 'next';
import {
  ChannelCredentials,
  Client,
  Metadata,
  ServiceError,
} from '@grpc/grpc-js';
import {
  decodeResiliencePayload,
  publicResilienceStatus,
  ResiliencePayload,
} from '../../utils/aiResilienceStatus';

const STATUS_METHOD = '/tf4.mandate25.ResilienceControl/GetStatus';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const backendUrl = process.env.PRODUCT_REVIEWS_ADDR || 'product-reviews:3551';
  const client = new Client(backendUrl, ChannelCredentials.createInsecure());

  try {
    const status = await new Promise<ResiliencePayload>((resolve, reject) => {
      client.makeUnaryRequest<Record<string, never>, ResiliencePayload>(
        STATUS_METHOD,
        (value) => Buffer.from(JSON.stringify(value), 'utf8'),
        decodeResiliencePayload,
        {},
        new Metadata(),
        { deadline: Date.now() + 2000 },
        (error: ServiceError | null, value?: ResiliencePayload) => {
          if (error || !value) {
            reject(error ?? new Error('empty resilience response'));
            return;
          }
          resolve(value);
        },
      );
    });
    const publicStatus = publicResilienceStatus(status);
    return res
      .status(publicStatus.status === 'healthy' ? 200 : 503)
      .json(publicStatus);
  } catch (error) {
    console.error('AI resilience status check failed:', error);
    return res.status(503).json({
      status: 'unavailable',
      circuitState: 'unknown',
      lastProviderOutcome: 'unknown',
      lastProviderError: 'status_contract_unavailable',
      faultMode: 'unknown',
      secondsRemaining: 0,
    });
  } finally {
    client.close();
  }
}
