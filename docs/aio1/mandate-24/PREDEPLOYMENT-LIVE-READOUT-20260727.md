# Mandate 24 pre-deployment live readout

**Observed:** 2026-07-27T07:35:59Z

This is a pre-deployment baseline, not Mandate 24 runtime acceptance.

## Runtime identity and deployment

- Account: `511825856493`
- Read/invoke role:
  `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6`
- Namespace/workload: `techx-tf4/product-reviews`
- Deployment generation/readiness: `57`, `2/2`
- Image:
  `511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:e4b49ba-product-reviews@sha256:585a5c0334d7088942416a4d449fef16d339e19cc644dd0b806ccd757f92b4c2`

The image predates this change. Its environment has no
`LLM_OBSERVABILITY_HASH_SALT`, so it cannot be used as Mandate 24 acceptance
evidence.

## Observability verification

- Prometheus `up` query returned 19 targets.
- The committed aggregate tool ran successfully against live Prometheus.
- Over the observed one-hour baseline, all three fixed queries returned a
  `llm_model=us.amazon.nova-2-lite-v1:0` series.
- The existing series has no `ai_surface` label. The new image must add and
  demonstrate that grouping before acceptance.
- Jaeger 2.17 uses `/jaeger/ui` as its query base path. Exact trace fetch by ID
  was verified with baseline trace
  `d2a7092f3d356323e32beaf8cc10165e`.
- That baseline trace reconstructs Storefront, frontend, product-reviews,
  product-catalog, database and Bedrock boundaries. Its Bedrock span reports a
  provider `ConnectTimeoutError`; it does not contain the new Mandate 24 custom
  span contract and is not counted as provider-fallback acceptance evidence.

## Access-path verification

- Grafana: `https://grafana.techx-tf4.site/grafana`
- Jaeger: `https://jaeger.techx-tf4.site/jaeger/ui`
- Load generator: `https://loadgen.techx-tf4.site/`

All three DNS names resolve through Cloudflare Access. An unauthenticated CLI
request is redirected to the Access login, as expected.

The role can read the cluster and port-forward observability services. It
cannot patch `Deployment/product-reviews` and cannot port-forward the selected
product-reviews pod. It can create Secrets, but the observability salt Secret
was deliberately not created before the reviewed image/config promotion.
Argo Application listing is also forbidden to this role.

## Remaining acceptance path

1. Open and merge the Mandate 24 implementation PR.
2. Let the reviewed build/promotion workflow publish and deploy the new image.
3. Provision `product-reviews-llm-observability/hash-salt` through the approved
   operational path.
4. Capture normal and provider-fallback replays with returned trace IDs.
5. Fetch both traces, run aggregate/privacy/overhead checks and record the
   deployed image digest plus Argo revision.
6. Obtain the named ADR approvals.

