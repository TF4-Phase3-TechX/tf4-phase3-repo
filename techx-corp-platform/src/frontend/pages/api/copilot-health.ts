import { NextApiRequest, NextApiResponse } from 'next';
import { ChannelCredentials } from '@grpc/grpc-js';
import { ProductReviewServiceClient } from '../../protos/demo';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const backendUrl = process.env.PRODUCT_REVIEWS_ADDR || 'product-reviews:3551';

  try {
    const client = new ProductReviewServiceClient(backendUrl, ChannelCredentials.createInsecure());
    
    // We can't easily ping a generic gRPC endpoint without HealthCheck protocol,
    // but initializing the client and doing a dummy call or just waiting for readiness works.
    const check = new Promise((resolve, reject) => {
      client.waitForReady(Date.now() + 2000, (err) => {
        if (err) {
          reject(err);
        } else {
          resolve('healthy');
        }
      });
    });

    await check;
    res.status(200).json({ status: 'healthy' });
  } catch (error) {
    console.error('Health check failed:', error);
    res.status(503).json({ status: 'unhealthy', reason: 'provider_unavailable' });
  }
}
