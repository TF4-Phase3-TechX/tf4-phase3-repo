#!/bin/sh
set -eu

cd "$(dirname "$0")/../.."

image=frontend-proxy-config-validation
export MSYS_NO_PATHCONV=1
trap 'docker image rm -f "$image" >/dev/null 2>&1 || true' EXIT

docker build -f src/frontend-proxy/Dockerfile -t "$image" .
docker run --rm --entrypoint /bin/sh \
  -e ENVOY_ADDR=0.0.0.0 \
  -e ENVOY_PORT=8080 \
  -e ENVOY_ADMIN_PORT=10000 \
  -e ENVOY_LOCAL_RL_AI_RPS=1 \
  -e ENVOY_LOCAL_RL_AI_BURST=2 \
  -e ENVOY_LOCAL_RL_BROWSE_RPS=2 \
  -e ENVOY_LOCAL_RL_BROWSE_BURST=4 \
  -e ENVOY_LOCAL_RL_CART_RPS=3 \
  -e ENVOY_LOCAL_RL_CHECKOUT_RPS=4 \
  -e ENVOY_LOCAL_RL_ENABLED_PERCENT=100 \
  -e ENVOY_LOCAL_RL_ENFORCED_PERCENT=0 \
  -e FLAGD_HOST=flagd \
  -e FLAGD_PORT=8013 \
  -e FLAGD_UI_HOST=flagd \
  -e FLAGD_UI_PORT=4000 \
  -e FRONTEND_HOST=frontend \
  -e FRONTEND_PORT=8080 \
  -e GRAFANA_HOST=grafana \
  -e GRAFANA_PORT=80 \
  -e IMAGE_PROVIDER_HOST=image-provider \
  -e IMAGE_PROVIDER_PORT=8081 \
  -e JAEGER_HOST=jaeger \
  -e JAEGER_UI_PORT=16686 \
  -e LOCUST_WEB_HOST=load-generator \
  -e LOCUST_WEB_PORT=8089 \
  -e OTEL_COLLECTOR_HOST=otel-collector \
  -e OTEL_COLLECTOR_PORT_GRPC=4317 \
  -e OTEL_COLLECTOR_PORT_HTTP=4318 \
  -e OTEL_SERVICE_NAME=frontend-proxy \
  "$image" -ec 'envsubst < envoy.tmpl.yaml > /tmp/envoy.yaml && envoy --mode validate -c /tmp/envoy.yaml'
