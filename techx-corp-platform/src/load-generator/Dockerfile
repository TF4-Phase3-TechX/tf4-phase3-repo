# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM python:3.12-alpine3.22@sha256:a190708a2dec1bd18b1decb539f8e8f5407abaa9bf39cacda583f7f8c11db322 AS base
RUN apk upgrade --no-cache libcrypto3 libssl3

FROM base AS builder
RUN apk add --no-cache g++

COPY ./src/load-generator/requirements.txt .
RUN pip install --prefix="/reqs" -r requirements.txt

FROM base
WORKDIR /usr/src/app/
COPY --from=builder /reqs /usr/local
COPY ./src/load-generator/locustfile.py .
COPY ./src/load-generator/people.json .
ENTRYPOINT ["locust", "--skip-log-setup"]
