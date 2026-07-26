// TechX TF4 — EKS Namespace Application Architecture (Mandate 08 Upgraded)
// type "pipeline" — internal cluster flow with programming language annotations
import { writeFileSync } from "node:fs";
import { Diagram } from "file:///C:/DevOps/drawio-ai-kit/src/builder.mjs";
import { group, frame, icon, box, phantom, renderTree, band, stage } from "file:///C:/DevOps/drawio-ai-kit/src/layout-engine.mjs";

const d = new Diagram("pipeline");

/* ── Entry + Load Test (side by side at top) ─────────────── */
const entryLayer = stage("entry", 0, "Entry — frontend-proxy", [
  icon("fp", "envoy", "frontend-proxy\n[Envoy]"),
  box("loadgen", "load-generator\n[Python / Locust]"),
]);

/* ── Storefront Layer ────────────────────────────────────── */
const storefrontLayer = stage("storefront", 1, "Storefront", [
  box("frontend", "frontend\n[TypeScript / Next.js]"),
  icon("imgprov", "nginx", "image-provider\n[Nginx]"),
]);

/* ── Product & AI Layer (left column) ────────────────────── */
const productAiLayer = stage("product_ai", 2, "Product & AI", [
  box("prodcat", "product-catalog\n[Go]"),
  box("prodrev", "product-reviews\n[Python]"),
  box("llm_svc", "llm\n[Python]"),
  box("rec", "recommendation\n[Python]"),
  box("ad_svc", "ad\n[Java]"),
  box("flagd_svc", "flagd\n[Go] — Feature Flags"),
]);

/* ── Checkout Revenue Path (right column) ────────────────── */
const checkoutLayer = stage("checkout_layer", 3, "Checkout — Revenue Path", [
  box("cart", "cart\n[C# .NET]"),
  box("checkout", "checkout\n[Go]"),
  box("payment", "payment\n[Node.js]"),
  box("email_svc", "email\n[Ruby]"),
  box("currency", "currency\n[C++]"),
  box("shipping", "shipping\n[Rust]"),
  box("quote", "quote\n[PHP]"),
]);

/* ── AWS Managed Data Services (Mandate 08) — placed between
     service layers and async consumers ──────────────────── */
const managedDataLayer = band("managed_data", "AWS Managed Data Services (Mandate 08)", [
  icon("rds_pg", "rds", "RDS PostgreSQL\n(Multi-AZ)"),
  icon("elc_valkey", "elasticache_for_valkey", "ElastiCache\nValkey"),
  icon("msk_kafka", "managed_streaming_for_kafka", "MSK Kafka\n(2 brokers)"),
  icon("secrets", "secrets_manager", "Secrets\nManager"),
  icon("bedrock_ai", "bedrock", "Amazon\nBedrock"),
]);

/* ── Async Consumers (right next to managed data) ─────────── */
const asyncLayer = stage("async", 4, "Async Consumers", [
  box("accounting", "accounting\n[C# .NET]"),
  box("fraud", "fraud-detection\n[Kotlin/JVM]"),
]);

/* ── Observability ───────────────────────────────────────── */
const obsLayer = band("observability", "Observability", [
  icon("otel", "opentelemetry", "otel-collector\n(DaemonSet)"),
  icon("prom", "prometheus", "prometheus"),
  icon("jaeg", "jaeger", "jaeger"),
  icon("graf", "grafana", "grafana"),
  icon("osearch", "opensearch", "opensearch"),
]);

/* ── Main tree: vertical pipeline layout ─────────────────── */
const tree = frame("eks_ns", "EKS Cluster — Namespace: techx-tf4", { dir: "col", gap: 18, stroke: "#ED7100" }, [
  entryLayer,
  storefrontLayer,
  phantom("svc_row", "", { dir: "row", gap: 24, align: "top", header: 0 }, [
    productAiLayer,
    checkoutLayer,
  ]),
  managedDataLayer,
  asyncLayer,
  obsLayer,
]);

renderTree(d, tree, [40, 60]);
d.title("TechX TF4 — EKS Namespace Application Architecture (Mandate 08 Upgraded)");

/* ── Traffic flow: entry ─────────────────────────────────── */
d.link("loadgen", "fp", "synthetic traffic", { dash: true });
d.link("fp", "frontend", "route to storefront", { flow: true });

/* ── Frontend → Product & AI APIs ────────────────────────── */
d.link("frontend", "prodcat", "Product & AI APIs", { flow: true, role: "fanout" });
d.link("frontend", "ad_svc", "", { role: "fanout" });
d.link("frontend", "rec", "", { role: "fanout" });
d.link("frontend", "prodrev", "", { role: "fanout" });

/* ── Frontend → Checkout APIs ────────────────────────────── */
d.link("frontend", "cart", "Cart & Checkout APIs", { flow: true, role: "fanout" });
d.link("frontend", "checkout", "", { flow: true, role: "fanout" });

/* ── Checkout internal dependencies ──────────────────────── */
d.link("checkout", "cart", "");
d.link("checkout", "currency", "");
d.link("checkout", "email_svc", "");
d.link("checkout", "payment", "");
d.link("checkout", "prodcat", "");
d.link("checkout", "shipping", "");
d.link("shipping", "quote", "");
d.link("checkout", "msk_kafka", "order events", { flow: true });

/* ── Product layer → DB ──────────────────────────────────── */
d.link("prodcat", "rds_pg", "DB queries");
d.link("prodrev", "rds_pg", "DB queries");

/* ── Cart → Valkey ───────────────────────────────────────── */
d.link("cart", "elc_valkey", "cache R/W");

/* ── Kafka consumers ─────────────────────────────────────── */
d.link("msk_kafka", "accounting", "order events");
d.link("msk_kafka", "fraud", "order events");
d.link("accounting", "rds_pg", "DB writes");

/* ── AI integration ──────────────────────────────────────── */
d.link("prodrev", "bedrock_ai", "AI inference", { dash: true });
d.link("prodrev", "prodcat", "product data");

/* ── Observability: all services → otel-collector ─────────── */
d.link("otel", "prom", "metrics");
d.link("otel", "jaeg", "traces");
d.link("otel", "osearch", "logs");
d.link("jaeg", "osearch", "storage");
d.link("prom", "graf", "data source", { dash: true });

/* ── Feature flags: flagd → nearby services ──────────────── */
d.link("flagd_svc", "ad_svc", "fault flags", { dash: true });
d.link("flagd_svc", "rec", "fault flags", { dash: true });

/* ── Secrets Manager → managed data ──────────────────────── */
d.link("secrets", "rds_pg", "credentials", { dash: true });
d.link("secrets", "elc_valkey", "credentials", { dash: true });
d.link("secrets", "msk_kafka", "credentials", { dash: true });

/* ── Validate & write ─────────────────────────────────────── */
const res = d.validate();
console.log("VALIDATE:", JSON.stringify({ ok: res.ok, errors: res.errors, warnings: res.warnings, advice: res.audit.advice }));
const outPath = "c:/DevOps/tf4-phase3-repo/docs/evidence/epic-02-baseline-architecture/architecture/02-techx-tf4-eks-namespace-architecture.drawio";
writeFileSync(outPath, d.mxfile("TechX TF4 — EKS Namespace Architecture"));
console.log("DRAWIO:", outPath);
