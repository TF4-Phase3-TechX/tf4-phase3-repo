// TechX TF4 — AWS High-Level Architecture (Mandate 08 Upgraded)
// type "network" — VPC/Multi-AZ with managed services layer
import { writeFileSync } from "node:fs";
import { Diagram } from "file:///C:/DevOps/drawio-ai-kit/src/builder.mjs";
import { group, frame, icon, box, phantom, renderTree, band } from "file:///C:/DevOps/drawio-ai-kit/src/layout-engine.mjs";

const d = new Diagram("network");

/* ── Availability Zone helper ─────────────────────────────── */
const az = (s, label) =>
  group(`az_${s}`, "group_availability_zone", `Availability Zone ${label}`, { dir: "col", gap: 40, align: "center" }, [
    group(`pub_${s}`, "group_subnet", "Public Subnet", { dir: "row", gap: 16 }, [
      icon(`nat_${s}`, "nat_gateway", "NAT Gateway"),
    ]),
    group(`prv_${s}`, "group_subnet", "Private Subnet", { dir: "col", gap: 12, priv: true }, [
      icon(`node_${s}`, "ec2", `Worker Node ${s === "a" ? "1" : "2"}`),
    ]),
  ]);

/* ── Managed Services band (outside VPC, inside Region) ──── */
const managedServicesRow = band("managed_svc", "AWS Managed Data Services (Mandate 08 — Private Endpoints)", [
  icon("rds", "rds", "RDS PostgreSQL\n(Multi-AZ)"),
  icon("elasticache", "elasticache_for_valkey", "ElastiCache\nValkey (2 nodes)"),
  icon("msk", "managed_streaming_for_kafka", "MSK\n(2 brokers)"),
]);

/* ── Supporting Services band ──────────────────────────────── */
const supportingServices = band("support_svc", "Supporting AWS Services", [
  icon("ecr", "ecr", "ECR"),
  icon("secrets_mgr", "secrets_manager", "Secrets\nManager"),
  icon("cloudtrail", "cloudtrail", "CloudTrail"),
  icon("cloudwatch", "cloudwatch_2", "CloudWatch\nLogs"),
  icon("s3_logs", "s3", "S3\n(Audit Logs)"),
  icon("eventbridge", "eventbridge", "EventBridge"),
  icon("sns", "sns", "SNS"),
  icon("bedrock", "bedrock", "Bedrock"),
  icon("budgets", "budgets_2", "Budgets"),
]);

/* ── ALB Security Group ──────────────────────────────────── */
const albSg = frame("sg_alb", "SG-ALB", { dir: "row", gap: 12, stroke: "#DD344C" }, [
  icon("alb", "application_load_balancer", "ALB"),
]);

/* ── Main tree ─────────────────────────────────────────────── */
const tree = group("region", "group_region", "Region (us-east-1)", { dir: "col", gap: 24, align: "center" }, [
  group("vpc", "group_vpc", "VPC", { dir: "col", gap: 22 }, [
    icon("igw", "internet_gateway", "Internet\nGateway"),
    albSg,
    phantom("azs_body", "", { dir: "row", gap: 80, align: "top", header: 0 }, [
      az("a", "us-east-1a"),
      az("b", "us-east-1b"),
    ]),
  ]),
  managedServicesRow,
  supportingServices,
]);

renderTree(d, tree, [40, 80]);
d.title("TechX TF4 — AWS High-Level Architecture (Mandate 08 Upgraded)");

/* ── EKS Cluster box spanning private subnets ─────────────── */
d.clusterBox("eks_cluster", ["prv_a", "prv_b"], "Amazon EKS Cluster (SG-EKS-Nodes)", { icon: "eks" });

/* ── User endpoint ─────────────────────────────────────────── */

/* ── Inbound traffic flow ──────────────────────────────────── */
d.link("igw", "alb", "HTTP/HTTPS", { flow: true });
d.link("alb", "node_a", "→ frontend-proxy", { flow: true, role: "fanout" });
d.link("alb", "node_b", "→ frontend-proxy", { flow: true, role: "fanout" });

/* ── Outbound: nodes → NAT for ECR pulls ───────────────────── */
d.link("node_a", "nat_a", "egress", { dash: true });
d.link("node_b", "nat_b", "egress", { dash: true });

/* ── Managed data connections (private endpoints) ──────────── */
d.link("node_a", "rds", "DB queries", { dash: true });
d.link("node_a", "elasticache", "cache R/W", { dash: true });
d.link("node_a", "msk", "produce/consume", { dash: true });
d.link("node_b", "rds", "", { dash: true });
d.link("node_b", "elasticache", "", { dash: true });
d.link("node_b", "msk", "", { dash: true });

/* ── Supporting service connections ──────────────────────── */
d.link("nat_a", "ecr", "pull images", { dash: true });
d.link("node_a", "secrets_mgr", "credentials", { dash: true });
d.link("node_a", "bedrock", "AI inference", { dash: true });

/* ── Audit / Monitoring ─────────────────────────────────── */
d.link("cloudtrail", "s3_logs", "log archive", { dash: true });
d.link("cloudtrail", "cloudwatch", "stream", { dash: true });
d.link("eventbridge", "sns", "alerts → Slack", { dash: true });

/* ── Validate & write ─────────────────────────────────────── */
const res = d.validate();
console.log("VALIDATE:", JSON.stringify({ ok: res.ok, errors: res.errors, warnings: res.warnings, advice: res.audit.advice }));
const outPath = "c:/DevOps/tf4-phase3-repo/docs/evidence/epic-02-baseline-architecture/architecture/01-techx-tf4-aws-high-level-architecture.drawio";
writeFileSync(outPath, d.mxfile("TechX TF4 — AWS High-Level Architecture"));
console.log("DRAWIO:", outPath);
