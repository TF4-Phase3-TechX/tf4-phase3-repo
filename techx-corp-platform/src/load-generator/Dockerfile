# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM python:3.12-slim-bookworm AS base

FROM base AS builder
RUN apt-get -qq update \
    && apt-get install -y --no-install-recommends g++ \
    && rm -rf /var/lib/apt/lists/*

COPY ./src/load-generator/requirements.txt .
RUN pip install --prefix="/reqs" -r requirements.txt

FROM base
WORKDIR /usr/src/app/
COPY --from=builder /reqs /usr/local
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
RUN playwright install --with-deps chromium
RUN groupadd --gid 10001 loadgenerator \
    && useradd --uid 10001 --gid 10001 \
        --create-home --home-dir /home/loadgenerator \
        --shell /usr/sbin/nologin loadgenerator \
    && mkdir -p /home/loadgenerator/.cache \
    && chown -R 10001:10001 /usr/src/app /home/loadgenerator /opt/pw-browsers
ENV HOME=/home/loadgenerator \
    XDG_CACHE_HOME=/home/loadgenerator/.cache
COPY --chown=10001:10001 ./src/load-generator/locustfile.py .
COPY --chown=10001:10001 ./src/load-generator/people.json .
USER 10001:10001
ENTRYPOINT ["locust", "--skip-log-setup"]
