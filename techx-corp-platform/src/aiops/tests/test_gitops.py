from __future__ import annotations

import copy
from types import SimpleNamespace

import httpx
import pytest

from app.gitops import (
    FileTokenProvider,
    GitOpsError,
    GitHubGitOpsRemediationAdapter,
    KubernetesRuntimeObserver,
    build_forced_wrong_document,
    build_remediation_document,
    component,
    forced_wrong_active,
)
from app.saga import GitTransaction


class Token:
    def token(self):
        return "redacted-test-token"


class Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_file_token_provider_rejects_wrong_identity(tmp_path, monkeypatch):
    token_path = tmp_path / "token"
    token_path.write_text("redacted-test-token", encoding="utf-8")
    provider = FileTokenProvider(
        token_path=str(token_path),
        expected_login="expected-user",
    )

    class Client:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def get(self, *_args, **_kwargs):
            response = Response({"login": "wrong-user"})
            response.status_code = 200
            return response

    monkeypatch.setattr(httpx, "Client", Client)
    with pytest.raises(GitOpsError, match="identity does not match"):
        provider.login()


def test_dual_token_reviewer_approves_and_merges(monkeypatch):
    reviewer = SimpleNamespace(
        token=lambda: "reviewer-token",
        login=lambda: "reviewer-user",
    )
    adapter = GitHubGitOpsRemediationAdapter(
        repository="owner/repository",
        base_branch="main",
        policy_path=".aiops/mandate22-policy.yaml",
        token_provider=Token(),
        reviewer_token_provider=reviewer,
        merge_strategy="dual-token",
    )
    item = transaction()
    item.pr_number = 7
    item.pr_node_id = "PR_7"
    item.head_sha = "1" * 40
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs.get("reviewer", False)))
        if method == "GET":
            return Response([])
        if path.endswith("/reviews"):
            return Response({"state": "APPROVED"})
        return Response({"merged": True, "sha": "9" * 40})

    monkeypatch.setattr(adapter, "_discover", lambda value: value)
    monkeypatch.setattr(adapter, "_request", request)
    result = adapter._submit_sync(item, queue_merge=True)
    assert result.merge_sha == "9" * 40
    assert result.state == "merged"
    assert calls == [
        ("GET", "/repos/owner/repository/pulls/7/reviews", True),
        ("POST", "/repos/owner/repository/pulls/7/reviews", True),
        ("PUT", "/repos/owner/repository/pulls/7/merge", True),
    ]


def test_runtime_observer_waits_until_old_rollout_pods_are_gone():
    deployment = SimpleNamespace(
        metadata=SimpleNamespace(generation=7),
        spec=SimpleNamespace(
            replicas=1,
            template={
                "metadata": {
                    "annotations": {"aiops.techx.io/remediation-id": "inc-runtime"}
                },
                "spec": {
                    "containers": [
                        {
                            "name": "product-reviews",
                            "env": [{"name": "SANDBOX_LABEL", "value": "kept"}],
                        }
                    ]
                },
            },
        ),
        status=SimpleNamespace(
            observed_generation=7,
            replicas=2,
            ready_replicas=1,
            updated_replicas=1,
            available_replicas=1,
        ),
    )
    observer = object.__new__(KubernetesRuntimeObserver)
    observer.namespace = "m22"
    observer.api = SimpleNamespace(
        read_namespaced_deployment_status=lambda *_: deployment
    )
    observer.serializer = SimpleNamespace(
        sanitize_for_serialization=lambda value: value
    )

    still_draining = observer._observe("product-reviews")
    assert still_draining["ready"] is False

    deployment.status.replicas = 1
    converged = observer._observe("product-reviews")
    assert converged["ready"] is True
    assert converged["remediation_id"] == "inc-runtime"


def transaction():
    return GitTransaction(
        kind="remediation",
        branch="aiops/remediation/inc-timeout",
        base_sha="a" * 40,
        policy_sha="b" * 40,
        known_good_sha="c" * 40,
        target_file="environments/production/app-values.yaml",
        before_hash="d" * 64,
        after_hash="e" * 64,
        before_file_sha="f" * 40,
        before_document={"components": {"product-reviews": {"replicas": 2}}},
        after_document={
            "components": {
                "product-reviews": {
                    "replicas": 2,
                    "podAnnotations": {"aiops.techx.io/remediation-id": "inc-timeout"},
                }
            }
        },
    )


def test_ambiguous_write_rediscovers_existing_branch_and_pr(monkeypatch):
    adapter = GitHubGitOpsRemediationAdapter(
        repository="owner/repository",
        base_branch="main",
        policy_path=".aiops/mandate22-policy.yaml",
        token_provider=Token(),
    )
    item = transaction()
    discovered = copy.deepcopy(item)
    discovered.pr_number = 17
    discovered.pr_node_id = "PR_node"
    discovered.pr_url = "https://github.test/pull/17"
    discovered.head_sha = "1" * 40
    calls = iter([None, discovered])
    monkeypatch.setattr(adapter, "_discover", lambda _: next(calls))

    def timeout(*_, **__):
        raise httpx.ReadTimeout("response lost after write")

    monkeypatch.setattr(adapter, "_request", timeout)
    result = adapter._submit_sync(item, queue_merge=False)
    assert result.pr_number == 17
    assert result.branch == "aiops/remediation/inc-timeout"


def test_discovery_qualifies_head_and_ignores_unrelated_prs(monkeypatch):
    adapter = GitHubGitOpsRemediationAdapter(
        repository="owner/repository",
        base_branch="main",
        policy_path=".aiops/mandate22-policy.yaml",
        token_provider=Token(),
    )
    item = transaction()
    captured = {}

    class Client:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def get(self, *_args, **_kwargs):
            response = Response({"object": {"sha": "1" * 40}})
            response.status_code = 200
            return response

    def request(_method, _path, **kwargs):
        captured.update(kwargs["params"])
        return Response(
            [
                {
                    "number": 99,
                    "node_id": "PR_unrelated",
                    "html_url": "https://github.test/pull/99",
                    "state": "open",
                    "head": {
                        "ref": "unrelated",
                        "repo": {"full_name": "owner/repository"},
                    },
                    "base": {"ref": "main"},
                },
                {
                    "number": 17,
                    "node_id": "PR_exact",
                    "html_url": "https://github.test/pull/17",
                    "state": "open",
                    "head": {
                        "ref": item.branch,
                        "repo": {"full_name": "owner/repository"},
                    },
                    "base": {"ref": "main"},
                },
            ]
        )

    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setattr(adapter, "_request", request)

    discovered = adapter._discover(item)

    assert captured["head"] == f"owner:{item.branch}"
    assert discovered is not None
    assert discovered.pr_number == 17
    assert discovered.pr_node_id == "PR_exact"


def test_partial_branch_is_completed_without_a_second_branch_or_pr(monkeypatch):
    adapter = GitHubGitOpsRemediationAdapter(
        repository="owner/repository",
        base_branch="main",
        policy_path=".aiops/mandate22-policy.yaml",
        token_provider=Token(),
    )
    item = transaction()
    partial = copy.deepcopy(item)
    partial.head_sha = partial.base_sha
    committed = copy.deepcopy(item)
    committed.head_sha = "1" * 40
    discoveries = iter([partial, committed])
    monkeypatch.setattr(adapter, "_discover", lambda _: next(discoveries))
    writes = []

    def request(method, path, **_):
        writes.append((method, path))
        if method == "PUT":
            return Response(
                {
                    "commit": {"sha": "1" * 40},
                    "content": {"sha": "2" * 40},
                }
            )
        return Response(
            {
                "number": 9,
                "node_id": "PR_9",
                "html_url": "https://github.test/pull/9",
            }
        )

    monkeypatch.setattr(adapter, "_request", request)
    result = adapter._submit_sync(item, queue_merge=False)
    assert result.pr_number == 9
    assert [method for method, _ in writes] == ["PUT", "POST"]


def test_managed_env_transform_rejects_no_protected_field_changes():
    current = {
        "components": {
            "product-reviews": {
                "replicas": 2,
                "image": {"tag": "protected"},
                "envOverrides": [
                    {
                        "name": "SECRET_REF",
                        "valueFrom": {"secretKeyRef": {"name": "x"}},
                    },
                    {"name": "MANDATE22_REVIEW_DELAY_MS", "value": "5000"},
                ],
            },
            "checkout": {"replicas": 3},
        }
    }
    known = {
        "components": {
            "product-reviews": {
                "replicas": 2,
                "envOverrides": [{"name": "MANDATE22_REVIEW_DELAY_MS", "value": "0"}],
            }
        }
    }
    after = build_remediation_document(
        current,
        known,
        component_name="product-reviews",
        managed_env_names=("MANDATE22_REVIEW_DELAY_MS",),
        incident_id="inc-transform",
    )
    target = component(after, "product-reviews")
    assert target["replicas"] == 2
    assert target["image"] == {"tag": "protected"}
    assert target["envOverrides"][0]["name"] == "SECRET_REF"
    assert target["envOverrides"][1] == {
        "name": "MANDATE22_REVIEW_DELAY_MS",
        "value": "0",
    }
    assert after["components"]["checkout"] == {"replicas": 3}


def test_forced_wrong_is_incident_bound_expiring_and_annotation_only():
    policy = {
        "forcedWrongProfile": {
            "enabled": True,
            "incidentId": "inc-forced-wrong",
            "expiresAt": "2099-01-01T00:00:00Z",
            "allowedDelta": "correlation_annotation_only",
        }
    }
    assert forced_wrong_active(policy, "inc-forced-wrong") is True
    current = {
        "components": {
            "product-reviews": {
                "envOverrides": [{"name": "MANDATE22_REVIEW_DELAY_MS", "value": "5000"}]
            }
        }
    }
    after = build_forced_wrong_document(
        current,
        component_name="product-reviews",
        incident_id="inc-forced-wrong",
    )
    assert (
        component(after, "product-reviews")["envOverrides"]
        == component(current, "product-reviews")["envOverrides"]
    )
    assert (
        component(after, "product-reviews")["podAnnotations"][
            "aiops.techx.io/remediation-id"
        ]
        == "inc-forced-wrong"
    )
    policy["forcedWrongProfile"]["expiresAt"] = "2000-01-01T00:00:00Z"
    with pytest.raises(GitOpsError, match="expired"):
        forced_wrong_active(policy, "inc-forced-wrong")
