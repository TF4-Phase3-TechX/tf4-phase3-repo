// TechX TF4 — GitOps Operational Flow Diagram
// type "pipeline"
import { writeFileSync } from "node:fs";
import { Diagram } from "file:///C:/DevOps/drawio-ai-kit/src/builder.mjs";
import { group, frame, icon, phantom, renderTree } from "file:///C:/DevOps/drawio-ai-kit/src/layout-engine.mjs";

const d = new Diagram("pipeline");

const tree = phantom("root", "", { dir: "row", gap: 140, align: "center", header: 0 }, [
  icon("dev", "user", "Developer\n(Phát triển)"),
  icon("app_repo", "github", "Repo App\n(tf4-phase3-repo)"),
  icon("ci_pipeline", "githubactions", "GitHub Actions\n(CI Pipeline)"),
  phantom("middle_stack", "", { dir: "col", gap: 80 }, [
    icon("ecr_registry", "ecr", "Amazon ECR\n(Docker Registry)"),
    frame("gitops_repo_frame", "Repo GitOps", { dir: "col", gap: 20, fill: "#FAFAFA", stroke: "#232F3D" }, [
      icon("gitops_repo", "git_repository", "tf4-phase3-gitops-manifests\n(Main Branch)")
    ])
  ]),
  icon("argocd_pod", "argocd", "Argo CD\n(K8s Cluster)"),
  icon("running_app", "container_registry_image", "Ứng dụng TechX\nchạy thực tế")
]);

renderTree(d, tree, [40, 80]);
d.title("Luồng Vận Hành Chi Tiết Khi Có Thay Đổi Code Ứng Dụng (GitOps CI/CD)");

// Link 1: Dev pushes code/chart to Repo App
d.link("dev", "app_repo", "1. Push Code/Chart", { flow: true });

// Link 2: Repo App triggers CI pipeline
d.link("app_repo", "ci_pipeline", "2. Trigger CI", { flow: true });

// Link 3: CI builds and pushes Docker image to ECR
d.link("ci_pipeline", "ecr_registry", "3. Push Docker Image", { flow: true });

// Link 4: CI updates GitOps config and creates PR
d.link("ci_pipeline", "gitops_repo", "4. Promotion (Update tag/PR)", { flow: true });

// Link 5: Dev merges PR in Repo GitOps
d.link("dev", "gitops_repo", "5. Review & Merge PR", { dash: true });

// Link 6: Repo GitOps triggers Argo CD
d.link("gitops_repo", "argocd_pod", "6. Webhook / Auto Sync", { flow: true });

// Link 7: Argo CD pulls image from ECR
d.link("argocd_pod", "ecr_registry", "7. Pull Docker Image", { dash: true });

// Link 8: Argo CD deploys and rollouts app
d.link("argocd_pod", "running_app", "8. Sync & Progressive Delivery", { flow: true });

const res = d.validate();
console.log("VALIDATE:", JSON.stringify({ ok: res.ok, errors: res.errors, warnings: res.warnings, advice: res.audit.advice }));

const outPath = "c:/DevOps/tf4-phase3-repo/docs/gitops/gitops-operational-flow.drawio";
writeFileSync(outPath, d.mxfile("Luồng Vận Hành Chi Tiết Khi Có Thay Đổi Code Ứng Dụng"));
console.log("DRAWIO:", outPath);
