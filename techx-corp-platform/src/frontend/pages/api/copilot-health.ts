import { NextApiRequest, NextApiResponse } from 'next';
import { grpc } from '@improbable-eng/grpc-web';
import { ProductService } from '../../../protos/demo_pb_service';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const backendUrl = process.env.FRONTEND_PROXY_ADDR || 'http://localhost:8080';

  try {
    const client = grpc.client(ProductService.ListProducts, {
      host: backendUrl,
    });

    const timeout = new Promise((_, reject) =>
      setTimeout(() => reject(new Error('Timeout')), 2000)
    );

    const check = new Promise((resolve, reject) => {
      client.onMessage(() => {
        resolve('healthy');
      });
      client.onEnd((code, msg, trailers) => {
        if (code === grpc.Code.OK) {
          resolve('healthy');
        } else {
          reject(new Error(`gRPC error: ${code} - ${msg}`));
        }
      });
      client.start({});
      client.finishSend();
    });

    await Promise.race([check, timeout]);
    res.status(200).json({ status: 'healthy' });
  } catch (error) {
    console.error('Health check failed:', error);
    res.status(503).json({ status: 'unhealthy', reason: 'provider_unavailable' });
  }
}
