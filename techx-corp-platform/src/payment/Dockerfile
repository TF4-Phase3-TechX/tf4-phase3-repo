# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM docker.io/library/node:22-slim@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3 AS builder

WORKDIR /usr/src/app/

COPY ./src/payment/package.json package.json
COPY ./src/payment/package-lock.json package-lock.json

RUN npm ci --omit=dev

# -----------------------------------------------------------------------------

FROM docker.io/library/node:22-alpine3.23@sha256:8516dce0483394d5708d4b2ee6cacb79fb1d617ea4e2787c2120bcca92ce372e

WORKDIR /usr/src/app/

RUN rm -rf /usr/local/lib/node_modules/npm \
    /usr/local/lib/node_modules/corepack \
    /usr/local/bin/npm \
    /usr/local/bin/npx \
    /usr/local/bin/corepack \
    /opt/yarn-*

COPY --chown=node:node --from=builder /usr/src/app/node_modules/ node_modules/

COPY --chown=node:node ./pb/demo.proto demo.proto

COPY --chown=node:node ./src/payment/charge.js charge.js
COPY --chown=node:node ./src/payment/index.js index.js
COPY --chown=node:node ./src/payment/logger.js logger.js
COPY --chown=node:node ./src/payment/opentelemetry.js opentelemetry.js

EXPOSE ${PAYMENT_PORT}

USER node

CMD ["node", "--require=./opentelemetry.js", "index.js"]
