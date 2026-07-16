# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

FROM --platform=${BUILDPLATFORM} gradle:8.12-jdk21 AS builder
WORKDIR /usr/src/app/

COPY ./src/ad/ ./
COPY ./pb/ ./proto

RUN gradle installDist -PprotoSourceDir=./proto

# -----------------------------------------------------------------------------

FROM eclipse-temurin:21-jre

ARG OTEL_JAVA_AGENT_VERSION
ARG _JAVA_OPTIONS

WORKDIR /usr/src/app/

COPY --from=builder /usr/src/app/build/install/techx-corp-ad/ ./build/install/techx-corp-ad/
ADD --chmod=644 https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v$OTEL_JAVA_AGENT_VERSION/opentelemetry-javaagent.jar /usr/src/app/opentelemetry-javaagent.jar
RUN groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid app --home-dir /usr/src/app --shell /usr/sbin/nologin app && \
    chown -R app:app /usr/src/app
ENV JAVA_TOOL_OPTIONS=-javaagent:/usr/src/app/opentelemetry-javaagent.jar

EXPOSE ${AD_PORT}
USER 10001:10001
ENTRYPOINT [ "./build/install/techx-corp-ad/bin/Ad" ]
