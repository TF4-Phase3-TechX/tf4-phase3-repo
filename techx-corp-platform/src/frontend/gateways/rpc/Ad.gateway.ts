// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { ChannelCredentials, Metadata } from '@grpc/grpc-js';
import { AdResponse, AdServiceClient } from '../../protos/demo';

const { AD_ADDR = '' } = process.env;
const configuredTimeoutMs = Number(process.env.AD_TIMEOUT_MS ?? 750);
const adTimeoutMs = Number.isFinite(configuredTimeoutMs) && configuredTimeoutMs > 0 ? configuredTimeoutMs : 750;

const client = new AdServiceClient(AD_ADDR, ChannelCredentials.createInsecure());

const AdGateway = () => ({
  listAds(contextKeys: string[]) {
    return new Promise<AdResponse>((resolve, reject) =>
      client.getAds(
        { contextKeys: contextKeys },
        new Metadata(),
        { deadline: Date.now() + adTimeoutMs },
        (error, response) => (error ? reject(error) : resolve(response))
      )
    );
  },
});

export default AdGateway();
