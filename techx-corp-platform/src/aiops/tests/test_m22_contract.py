from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_rbac_has_no_deployment_patch_and_only_lease_writes():
    text = (ROOT / "techx-corp-chart/templates/aiops-rbac.yaml").read_text(
        encoding="utf-8"
    )
    deployment_rule = text.split('resources: ["deployments"]', 1)[1].split(
        "- apiGroups:", 1
    )[0]
    assert '"patch"' not in deployment_rule
    assert '"update"' not in deployment_rule
    assert 'resources: ["leases"]' in text


def test_controller_has_no_direct_kubernetes_or_argo_mutation_path():
    app = ROOT / "techx-corp-platform/src/aiops/app"
    source = "\n".join(path.read_text(encoding="utf-8") for path in app.glob("*.py"))
    assert "patch_namespaced_deployment" not in source
    assert "patch_template" not in source
    assert "ignoreDifferences" not in source
    assert "Argo Application" not in source
