// TechX TF4 — GitOps Relationship Diagram
// type "network"
import { writeFileSync } from "node:fs";
import { Diagram } from "file:///C:/DevOps/drawio-ai-kit/src/builder.mjs";
import { group, frame, icon, phantom, renderTree } from "file:///C:/DevOps/drawio-ai-kit/src/layout-engine.mjs";

const d = new Diagram("network");

const tree = phantom("root", "", { dir: "row", gap: 140, align: "center", header: 0 }, [
  // Cột 1: Các repositories chứa code nguồn và cấu hình hạ tầng
  frame("app_repo", "Repo Nguồn: tf4-phase3-repo", { dir: "col", gap: 40, fill: "#FAFAFA", stroke: "#232F3D" }, [
    icon("platform_src", "source_code", "techx-corp-platform\n(Mã nguồn các service)"),
    icon("helm_chart", "helm", "techx-corp-chart\n(Helm Chart template)"),
    icon("infra_tf", "terraform", "infra/terraform\n(Hạ tầng AWS / EKS Cluster)")
  ]),

  // Cột 2: Amazon ECR và Repo GitOps
  phantom("middle_col", "", { dir: "col", gap: 80 }, [
    icon("ecr_registry", "ecr", "Amazon ECR\n(Docker Registry)"),
    frame("gitops_repo", "Repo GitOps: tf4-phase3-gitops-manifests", { dir: "col", gap: 40, fill: "#FAFAFA", stroke: "#232F3D" }, [
      icon("gitops_prod", "config", "environments/production\n(image-revisions.yaml / values)"),
      icon("gitops_apps", "argocd", "argocd/root-resources\n(applications.yaml)")
    ])
  ]),

  // Cột 3: Kubernetes Cluster (AWS EKS) chạy thực tế
  group("eks_cluster", "group_vpc", "Kubernetes Cluster (AWS EKS)", { dir: "col", gap: 60 }, [
    icon("argocd_pod", "argocd", "Argo CD\n(Controller)"),
    icon("running_app", "container_registry_image", "Ứng dụng TechX\nchạy thực tế")
  ])
]);

renderTree(d, tree, [40, 80]);
d.title("Mối Quan Hệ Giữa Hai Repository & Luồng Deploy GitOps (Production)");

// Link 1: App code build & push to ECR (animated flow)
d.link("platform_src", "ecr_registry", "1. Build & Push Image", { flow: true });

// Link 2: Helm chart update targetRevision in GitOps applications
d.link("helm_chart", "gitops_apps", "2. Cập nhật targetRevision", { dash: true });

// Link 3: App code update image tag in production values
d.link("platform_src", "gitops_prod", "3. Cập nhật image tag", { dash: true });

// Link 4: Argo CD reads applications config from GitOps repo
d.link("gitops_apps", "argocd_pod", "4. Đọc cấu hình ứng dụng", { dash: true });

// Link 5: Argo CD reads production values from GitOps repo
d.link("gitops_prod", "argocd_pod", "4. Đọc values & configs", { dash: true });

// Link 6: Argo CD pulls image from ECR
d.link("ecr_registry", "running_app", "5. Kéo (Pull) image", { dash: true });

// Link 7: Argo CD syncs and deploys running pod (animated flow)
d.link("argocd_pod", "running_app", "6. Sync & Deploy", { flow: true });

const res = d.validate();
console.log("VALIDATE:", JSON.stringify({ ok: res.ok, errors: res.errors, warnings: res.warnings, advice: res.audit.advice }));

const outPath = "c:/DevOps/tf4-phase3-repo/docs/gitops/gitops-relationship.drawio";
writeFileSync(outPath, d.mxfile("Mối Quan Hệ Giữa Hai Repository & Luồng Deploy GitOps"));
console.log("DRAWIO:", outPath);

import { execFileSync as __exec } from "node:child_process";
try {
  console.log(__exec("drawio-ai", ["render", outPath, "--check", "-o", outPath + ".png"], { encoding: "utf8" }).trim());
} catch (e) {
  console.error("RENDER-SKIPPED:", String(e.message).split("\n")[0]);
}
