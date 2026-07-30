"""Disposable Kind/Argo drill harness for Mandate 22.

This harness exercises the production detector, worker, remediation controller,
Kubernetes runtime observer and Lease lock. A local Git adapter models the
protected PR/check/merge boundary while writing real commits to a disposable
repository consumed by a real Argo CD Application.

It deliberately does not claim GitHub App/ruleset or production evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import Settings  # noqa: E402
from app.detection import Detector  # noqa: E402
from app.gitops import (
    GitObservation,
    GitOpsError,
    GitOpsRemediationAdapter,
    KubernetesLeaseTargetLock,
    KubernetesRuntimeObserver,
    build_compensation_document,
    build_forced_wrong_document,
    build_remediation_document,
    component,
    forced_wrong_active,
    structured_hash,
)  # noqa: E402
from app.models import Incident, IncidentStatus  # noqa: E402
from app.remediation import RemediationController  # noqa: E402
from app.saga import (  # noqa: E402
    FileSagaStore,
    GitTransaction,
    RemediationSaga,
    SagaPhase,
)
from app.store import IncidentStore  # noqa: E402
from app.worker import AIOpsWorker  # noqa: E402


MANAGED_ENV_NAMES = (
    "MANDATE22_REVIEW_DELAY_MS",
    "MANDATE22_REVIEW_DELAY_TTL_SECONDS",
    "MANDATE22_REVIEW_DELAY_MAX_REQUESTS",
)
REQUIRED_CHECKS = (
    "validate",
    "check-pinned-dependencies",
    "aiops-remediation-policy",
)
PYTHON_IMAGE = (
    "docker.io/library/python:3.12-alpine3.22@"
    "sha256:a190708a2dec1bd18b1decb539f8e8f5407abaa9bf39cacda583f7f8c11db322"
)


def run(
    *args: str,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout: int = 120,
) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout.strip()


def git(cwd: Path, *args: str) -> str:
    return run("git", *args, cwd=cwd)


def simulate_git_webhook(context: str, application: str) -> None:
    """Invalidate Argo's repo cache as a Git-provider webhook would."""

    run(
        "kubectl",
        "--context",
        context,
        "-n",
        "argocd",
        "annotate",
        "application",
        application,
        "argocd.argoproj.io/refresh=hard",
        "--overwrite",
    )


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def values_document(
    *, fault: bool, remediation_id: str | None = None
) -> dict[str, Any]:
    product_reviews: dict[str, Any] = {
        "replicas": 1,
        "image": PYTHON_IMAGE,
        "envOverrides": [
            {"name": "SANDBOX_LABEL", "value": "preserved-unmanaged-value"},
        ],
        "podAnnotations": {},
    }
    if fault:
        product_reviews["envOverrides"].extend(
            [
                {"name": "MANDATE22_REVIEW_DELAY_MS", "value": "800"},
                {
                    "name": "MANDATE22_REVIEW_DELAY_TTL_SECONDS",
                    "value": "300",
                },
                {
                    "name": "MANDATE22_REVIEW_DELAY_MAX_REQUESTS",
                    "value": "100",
                },
            ]
        )
    if remediation_id:
        product_reviews["podAnnotations"]["aiops.techx.io/remediation-id"] = (
            remediation_id
        )
    return {"components": {"product-reviews": product_reviews}}


SERVER_SOURCE = r"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

started_at = None
requests = 0
lock = threading.Lock()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def do_GET(self):
        global started_at, requests
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if not self.path.startswith("/api/product-reviews/"):
            self.send_response(404)
            self.end_headers()
            return
        delay_ms = int(os.getenv("MANDATE22_REVIEW_DELAY_MS", "0") or "0")
        ttl = int(os.getenv("MANDATE22_REVIEW_DELAY_TTL_SECONDS", "0") or "0")
        cap = int(os.getenv("MANDATE22_REVIEW_DELAY_MAX_REQUESTS", "0") or "0")
        apply_fault = False
        with lock:
            now = time.monotonic()
            if delay_ms:
                if started_at is None:
                    started_at = now
                if now - started_at < ttl and requests < cap:
                    requests += 1
                    apply_fault = True
        if apply_fault:
            time.sleep(delay_ms / 1000)
        payload = json.dumps({
            "product_id": self.path.rsplit("/", 1)[-1],
            "fault_applied": apply_fault,
            "request_ordinal": requests,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
""".strip()


CHART_YAML = """\
apiVersion: v2
name: m22-product-reviews
version: 0.1.0
type: application
"""


DEPLOYMENT_TEMPLATE = r"""
{{- $productReviews := index .Values.components "product-reviews" }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: product-reviews-sandbox
data:
  server.py: |
{{ .Files.Get "files/server.py" | indent 4 }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: product-reviews
spec:
  replicas: {{ $productReviews.replicas }}
  selector:
    matchLabels:
      app: product-reviews
  template:
    metadata:
      labels:
        app: product-reviews
      annotations:
{{- toYaml $productReviews.podAnnotations | nindent 8 }}
    spec:
      containers:
        - name: product-reviews
          image: {{ $productReviews.image | quote }}
          imagePullPolicy: IfNotPresent
          command: ["python", "/sandbox/server.py"]
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
            periodSeconds: 1
            failureThreshold: 30
          env:
{{- toYaml $productReviews.envOverrides | nindent 12 }}
          volumeMounts:
            - name: server
              mountPath: /sandbox
              readOnly: true
      volumes:
        - name: server
          configMap:
            name: product-reviews-sandbox
---
apiVersion: v1
kind: Service
metadata:
  name: product-reviews
spec:
  selector:
    app: product-reviews
  ports:
    - name: http
      port: 8080
      targetPort: http
""".strip()


class DisposableRepository:
    def __init__(self, root: Path):
        self.root = root
        self.work = root / "work"
        self.repo_name = f"repo-{os.getpid()}.git"
        self.bare = root / "git" / self.repo_name
        self.git_server_name = f"m22-git-{os.getpid()}"
        self.git_server_ip = ""
        self.known_good_sha = ""

    @property
    def git_url(self) -> str:
        return f"git://{self.git_server_ip}:9418/{self.repo_name}"

    def initialize(self) -> None:
        self.bare.parent.mkdir(parents=True, exist_ok=True)
        run("git", "init", "--bare", str(self.bare))
        run("git", "init", "-b", "main", str(self.work))
        git(self.work, "config", "user.name", "Mandate 22 Sandbox")
        git(self.work, "config", "user.email", "m22-sandbox@invalid")
        git(self.work, "remote", "add", "origin", str(self.bare))

        (self.work / "chart" / "templates").mkdir(parents=True, exist_ok=True)
        (self.work / "chart" / "files").mkdir(parents=True, exist_ok=True)
        (self.work / "chart" / "Chart.yaml").write_text(CHART_YAML, encoding="utf-8")
        (self.work / "chart" / "files" / "server.py").write_text(
            SERVER_SOURCE + "\n", encoding="utf-8"
        )
        (self.work / "chart" / "templates" / "all.yaml").write_text(
            DEPLOYMENT_TEMPLATE + "\n", encoding="utf-8"
        )
        write_yaml(
            self.work / "chart" / "values.yaml",
            values_document(fault=False),
        )
        write_yaml(
            self.work / "environments" / "production" / "app-values.yaml",
            values_document(fault=False),
        )
        git(self.work, "add", ".")
        git(self.work, "commit", "-m", "feat(sandbox): known-good product-reviews")
        self.known_good_sha = git(self.work, "rev-parse", "HEAD")

        policy = {
            "policyVersion": "m22-gitops-v1",
            "incidentType": "service_latency_spike",
            "runbook": "product-reviews-config-rollback",
            "repository": "sandbox/m22-gitops",
            "baseBranch": "main",
            "targetFile": "environments/production/app-values.yaml",
            "component": "product-reviews",
            "managedEnvNames": list(MANAGED_ENV_NAMES),
            "knownGoodCommit": self.known_good_sha,
            "requiredChecks": list(REQUIRED_CHECKS),
            "githubAppLogin": "sandbox-remediator[bot]",
            "correlationAnnotation": "aiops.techx.io/remediation-id",
            "forcedWrongProfile": {
                "enabled": False,
                "incidentId": "",
                "expiresAt": "1970-01-01T00:00:00Z",
                "allowedDelta": "correlation_annotation_only",
            },
        }
        write_yaml(self.work / ".aiops" / "mandate22-policy.yaml", policy)
        git(self.work, "add", ".aiops/mandate22-policy.yaml")
        git(self.work, "commit", "-m", "chore(sandbox): add protected M22 policy")
        git(self.work, "push", "-u", "origin", "main")

    def start_server(self) -> None:
        image = (
            "docker.io/library/alpine@"
            "sha256:4bcff63911fcb4448bd4fdacec207030997caf25e9bea4045fa6c8c44de311d1"
        )
        mount = f"{self.bare.parent}:/git"
        run(
            "docker",
            "run",
            "-d",
            "--name",
            self.git_server_name,
            "--network",
            "kind",
            "-v",
            mount,
            image,
            "sh",
            "-c",
            (
                "apk add --no-cache git-daemon >/tmp/apk.log && "
                "exec git daemon --reuseaddr --base-path=/git --export-all "
                "--enable=receive-pack --verbose"
            ),
            timeout=60,
        )
        self.git_server_ip = run(
            "docker",
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            self.git_server_name,
        )
        if not self.git_server_ip:
            raise RuntimeError("disposable Git server has no Docker network address")

    def inject_fault(self) -> str:
        git(self.work, "checkout", "main")
        git(self.work, "reset", "--hard", "origin/main")
        write_yaml(
            self.work / "environments" / "production" / "app-values.yaml",
            values_document(fault=True),
        )
        git(self.work, "add", "environments/production/app-values.yaml")
        git(self.work, "commit", "-m", "test(m22): inject bounded review latency")
        git(self.work, "push", "origin", "main")
        return git(self.work, "rev-parse", "HEAD")

    def enable_forced_wrong(self, incident_id: str) -> str:
        git(self.work, "checkout", "main")
        git(self.work, "reset", "--hard", "origin/main")
        policy_path = self.work / ".aiops" / "mandate22-policy.yaml"
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        policy["forcedWrongProfile"] = {
            "enabled": True,
            "incidentId": incident_id,
            "expiresAt": (
                datetime.now(timezone.utc) + timedelta(minutes=10)
            ).isoformat(),
            "allowedDelta": "correlation_annotation_only",
        }
        write_yaml(policy_path, policy)
        git(self.work, "add", ".aiops/mandate22-policy.yaml")
        git(
            self.work,
            "commit",
            "-m",
            f"test(m22): authorize forced-wrong {incident_id}",
        )
        git(self.work, "push", "origin", "main")
        return git(self.work, "rev-parse", "HEAD")

    def stop_server(self) -> None:
        subprocess.run(
            ["docker", "rm", "-f", self.git_server_name],
            capture_output=True,
            check=False,
        )


class LocalPullRequestAdapter(GitOpsRemediationAdapter):
    """Real Git commits with a deterministic local PR/check/merge boundary."""

    def __init__(
        self,
        repository: DisposableRepository,
        *,
        context: str,
        application: str,
    ):
        self.repository = repository
        self.context = context
        self.application = application
        self.merges: dict[str, str] = {}

    def _show_yaml(self, ref: str, path: str) -> tuple[dict[str, Any], str]:
        raw = git(self.repository.work, "show", f"{ref}:{path}")
        document = yaml.safe_load(raw)
        if not isinstance(document, dict):
            raise GitOpsError(f"{path} at {ref} is not a mapping")
        blob = git(self.repository.work, "rev-parse", f"{ref}:{path}")
        return document, blob

    async def prepare(
        self,
        incident: Incident,
        *,
        compensation_for: RemediationSaga | None = None,
    ) -> GitTransaction:
        git(self.repository.work, "fetch", "origin")
        base_sha = git(self.repository.work, "rev-parse", "origin/main")
        policy, policy_sha = self._show_yaml(base_sha, ".aiops/mandate22-policy.yaml")
        known_good_sha = str(policy["knownGoodCommit"])
        run(
            "git",
            "merge-base",
            "--is-ancestor",
            known_good_sha,
            base_sha,
            cwd=self.repository.work,
        )
        target_file = str(policy["targetFile"])
        current, current_blob = self._show_yaml(base_sha, target_file)
        if compensation_for:
            after = build_compensation_document(
                current,
                compensation_for,
                component_name="product-reviews",
            )
            kind = "compensation"
        else:
            if forced_wrong_active(policy, incident.incident_id):
                after = build_forced_wrong_document(
                    current,
                    component_name="product-reviews",
                    incident_id=incident.incident_id,
                )
            else:
                known_good, _ = self._show_yaml(known_good_sha, target_file)
                after = build_remediation_document(
                    current,
                    known_good,
                    component_name="product-reviews",
                    managed_env_names=MANAGED_ENV_NAMES,
                    incident_id=incident.incident_id,
                )
            kind = "remediation"
        return GitTransaction(
            kind=kind,
            branch=f"aiops/{kind}/{incident.incident_id}",
            base_sha=base_sha,
            policy_sha=policy_sha,
            known_good_sha=known_good_sha,
            target_file=target_file,
            before_hash=structured_hash(component(current, "product-reviews")),
            after_hash=structured_hash(component(after, "product-reviews")),
            before_file_sha=current_blob,
            before_document=current,
            after_document=after,
            state="prepared",
        )

    async def submit(
        self, transaction: GitTransaction, *, queue_merge: bool = False
    ) -> GitTransaction:
        work = self.repository.work
        if transaction.pr_number is None:
            git(work, "fetch", "origin")
            remote_ref = f"refs/remotes/origin/{transaction.branch}"
            remote = subprocess.run(
                ["git", "rev-parse", "--verify", remote_ref],
                cwd=work,
                text=True,
                capture_output=True,
                check=False,
            )
            if remote.returncode == 0:
                transaction.head_sha = remote.stdout.strip()
                transaction.after_file_sha = git(
                    work,
                    "rev-parse",
                    f"{transaction.head_sha}:{transaction.target_file}",
                )
                transaction.pr_number = 1 if transaction.kind == "remediation" else 2
                transaction.pr_node_id = (
                    f"sandbox-pr-{transaction.pr_number}-{transaction.head_sha[:12]}"
                )
                transaction.pr_url = (
                    f"sandbox://pull/{transaction.pr_number}/{transaction.branch}"
                )
                transaction.state = "open"
                return transaction
            git(work, "checkout", "-B", transaction.branch, transaction.base_sha)
            write_yaml(work / transaction.target_file, transaction.after_document or {})
            git(work, "add", transaction.target_file)
            git(
                work,
                "commit",
                "-m",
                f"fix(aiops): {transaction.kind} "
                f"{transaction.branch.rsplit('/', 1)[-1]}",
            )
            transaction.head_sha = git(work, "rev-parse", "HEAD")
            transaction.after_file_sha = git(
                work, "rev-parse", f"HEAD:{transaction.target_file}"
            )
            git(work, "push", "-f", "origin", transaction.branch)
            transaction.pr_number = 1 if transaction.kind == "remediation" else 2
            transaction.pr_node_id = (
                f"sandbox-pr-{transaction.pr_number}-{transaction.head_sha[:12]}"
            )
            transaction.pr_url = (
                f"sandbox://pull/{transaction.pr_number}/{transaction.branch}"
            )
            transaction.state = "open"
            return transaction

        if queue_merge and not transaction.merge_queued:
            if not set(REQUIRED_CHECKS) <= {
                name for name, state in transaction.checks.items() if state == "success"
            }:
                raise GitOpsError("sandbox rules rejected merge before checks")
            git(work, "fetch", "origin")
            git(work, "checkout", "main")
            git(work, "reset", "--hard", "origin/main")
            git(work, "merge", "--squash", f"origin/{transaction.branch}")
            git(
                work,
                "commit",
                "-m",
                f"fix(aiops): merge {transaction.kind} "
                f"{transaction.branch.rsplit('/', 1)[-1]}",
            )
            git(work, "push", "origin", "main")
            transaction.merge_sha = git(work, "rev-parse", "HEAD")
            transaction.merge_queued = True
            transaction.state = "merged"
            self.merges[transaction.branch] = transaction.merge_sha
            simulate_git_webhook(self.context, self.application)
        return transaction

    async def observe(self, transaction: GitTransaction) -> GitObservation:
        if merge_sha := self.merges.get(transaction.branch):
            return GitObservation(
                state="merged",
                checks=dict(transaction.checks),
                head_sha=transaction.head_sha,
                merge_sha=merge_sha,
                merge_queued=True,
            )
        git(self.repository.work, "fetch", "origin")
        main_sha = git(self.repository.work, "rev-parse", "origin/main")
        current, _ = self._show_yaml(main_sha, transaction.target_file)
        if (
            main_sha != transaction.base_sha
            and structured_hash(component(current, "product-reviews"))
            == transaction.after_hash
        ):
            return GitObservation(
                state="merged",
                checks=dict(transaction.checks),
                head_sha=transaction.head_sha,
                merge_sha=main_sha,
                merge_queued=True,
            )
        if not transaction.head_sha:
            return GitObservation(state="missing", checks={})
        changed = git(
            self.repository.work,
            "diff",
            "--name-only",
            transaction.base_sha,
            transaction.head_sha,
        ).splitlines()
        if changed != [transaction.target_file]:
            return GitObservation(
                state="checks",
                checks={name: "failure" for name in REQUIRED_CHECKS},
                head_sha=transaction.head_sha,
                reason=f"unexpected files changed: {changed}",
            )
        rendered = transaction.after_document or {}
        target = component(rendered, "product-reviews")
        env_names = {
            item.get("name")
            for item in target.get("envOverrides") or []
            if isinstance(item, dict)
        }
        annotation = (target.get("podAnnotations") or {}).get(
            "aiops.techx.io/remediation-id"
        )
        incident_id = transaction.branch.rsplit("/", 1)[-1]
        hash_matches = structured_hash(target) == transaction.after_hash
        policy, _ = self._show_yaml(
            transaction.base_sha,
            ".aiops/mandate22-policy.yaml",
        )
        forced_wrong = transaction.kind == "remediation" and forced_wrong_active(
            policy, incident_id
        )
        passed = hash_matches and (
            transaction.kind == "compensation"
            or (
                (forced_wrong or not (set(MANAGED_ENV_NAMES) & env_names))
                and annotation == incident_id
                and target.get("replicas") == 1
            )
        )
        checks = {
            "validate": "success" if rendered.get("components") else "failure",
            "check-pinned-dependencies": (
                "success" if "@sha256:" in str(target.get("image", "")) else "failure"
            ),
            "aiops-remediation-policy": "success" if passed else "failure",
        }
        transaction.checks = checks
        return GitObservation(
            state="checks",
            checks=checks,
            head_sha=transaction.head_sha,
        )

    async def cancel(self, transaction: GitTransaction, reason: str) -> None:
        transaction.state = f"closed: {reason}"


class MeasuredTelemetry:
    def __init__(self, latency_points: list[float]):
        self.latency_points = latency_points

    async def query_range(self, query: str) -> list[dict[str, Any]]:
        now = int(time.time())
        if "histogram_quantile" in query:
            return [
                {
                    "metric": {"service_name": "product-reviews"},
                    "values": [
                        [now - (len(self.latency_points) - index) * 15, str(value)]
                        for index, value in enumerate(self.latency_points)
                    ],
                }
            ]
        if "status_code" in query or "http_response_status_code" in query:
            return [
                {
                    "metric": {"service_name": "product-reviews"},
                    "values": [[now - 15, "0"], [now, "0"]],
                }
            ]
        return []

    async def query(self, _query: str) -> list[dict[str, Any]]:
        return []

    async def search_logs(
        self, _services: tuple[str, ...], _terms: tuple[str, ...]
    ) -> list[dict[str, Any]]:
        return []

    async def find_traces(self, _service: str) -> list[dict[str, Any]]:
        return [{"traceID": "sandbox-real-traffic"}]


class ServiceTraffic:
    def __init__(self, context: str, namespace: str):
        self.context = context
        self.namespace = namespace
        self.port = self._free_port()
        self.process: subprocess.Popen[str] | None = None

    @staticmethod
    def _free_port() -> int:
        import socket

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def start(self) -> None:
        self.process = subprocess.Popen(
            [
                "kubectl",
                "--context",
                self.context,
                "-n",
                self.namespace,
                "port-forward",
                "service/product-reviews",
                f"{self.port}:8080",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/healthz", timeout=1
                ) as response:
                    if response.status == 200:
                        return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("product-reviews port-forward did not become ready")

    def sample(self, count: int) -> list[float]:
        values: list[float] = []
        for index in range(count):
            started = time.perf_counter()
            with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/api/product-reviews/{index}",
                timeout=5,
            ) as response:
                if response.status != 200:
                    raise RuntimeError(f"review request failed: {response.status}")
                response.read()
            values.append((time.perf_counter() - started) * 1000)
        return values

    def restart(self) -> None:
        self.stop()
        self.start()

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


def percentile95(points: list[float]) -> float:
    ordered = sorted(points)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def wait_for_application(
    context: str,
    *,
    expected_env: set[str],
    remediation_id: str | None,
    timeout: int = 180,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            raw = run(
                "kubectl",
                "--context",
                context,
                "-n",
                "m22",
                "get",
                "deployment",
                "product-reviews",
                "-o",
                "json",
                timeout=15,
            )
            last = json.loads(raw)
        except Exception:
            time.sleep(2)
            continue
        template = last["spec"]["template"]
        env = {
            item.get("name")
            for item in template["spec"]["containers"][0].get("env") or []
        }
        annotation = (
            template.get("metadata", {})
            .get("annotations", {})
            .get("aiops.techx.io/remediation-id")
        )
        status = last.get("status") or {}
        desired = int(last["spec"].get("replicas", 1))
        ready = (
            status.get("observedGeneration") == last["metadata"].get("generation")
            and status.get("replicas", 0) == desired
            and status.get("readyReplicas", 0) == desired
            and status.get("availableReplicas", 0) == desired
            and status.get("updatedReplicas", 0) == desired
        )
        if (
            ready
            and expected_env <= env
            and not (set(MANAGED_ENV_NAMES) - expected_env) & env
        ):
            if annotation == remediation_id:
                return last
        time.sleep(2)
    raise RuntimeError(
        "Argo runtime did not converge to expected identity: "
        + json.dumps(
            {
                "expected_env": sorted(expected_env),
                "remediation_id": remediation_id,
                "last_generation": (last.get("metadata") or {}).get("generation"),
            }
        )
    )


def apply_application(context: str, repository_url: str) -> None:
    run(
        "kubectl",
        "--context",
        context,
        "-n",
        "argocd",
        "delete",
        "application",
        "techx-corp",
        "--ignore-not-found=true",
        "--wait=true",
    )
    run(
        "kubectl",
        "--context",
        context,
        "-n",
        "argocd",
        "patch",
        "configmap",
        "argocd-cm",
        "--type",
        "merge",
        "-p",
        json.dumps(
            {
                "data": {
                    "timeout.reconciliation": "5s",
                    "timeout.reconciliation.jitter": "0s",
                }
            }
        ),
    )
    run(
        "kubectl",
        "--context",
        context,
        "-n",
        "argocd",
        "rollout",
        "restart",
        "statefulset/argocd-application-controller",
    )
    run(
        "kubectl",
        "--context",
        context,
        "-n",
        "argocd",
        "rollout",
        "status",
        "statefulset/argocd-application-controller",
        "--timeout=180s",
        timeout=200,
    )
    application = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {"name": "techx-corp", "namespace": "argocd"},
        "spec": {
            "project": "default",
            "sources": [
                {
                    "repoURL": repository_url,
                    "targetRevision": "main",
                    "path": "chart",
                    "helm": {
                        "releaseName": "product-reviews",
                        "valueFiles": [
                            "$values/environments/production/app-values.yaml"
                        ],
                    },
                },
                {
                    "repoURL": repository_url,
                    "targetRevision": "main",
                    "ref": "values",
                },
            ],
            "destination": {
                "server": "https://kubernetes.default.svc",
                "namespace": "m22",
            },
            "syncPolicy": {
                "automated": {"prune": False, "selfHeal": True},
                "syncOptions": ["CreateNamespace=true"],
            },
        },
    }
    run(
        "kubectl",
        "--context",
        context,
        "apply",
        "-f",
        "-",
        input_text=yaml.safe_dump(application, sort_keys=False),
    )


def sandbox_settings(evidence_dir: Path) -> Settings:
    return replace(
        Settings(),
        namespace="m22",
        services=("product-reviews",),
        generic_signal_services=("product-reviews",),
        llm_services=(),
        llm_log_services=(),
        service_slo_targets={},
        sustained_polls=1,
        latency_threshold_ms=500,
        latency_high_multiplier=1.2,
        remediation_confidence_threshold=0.5,
        remediation_mode="gitops/live",
        autonomous_remediation_enabled=True,
        autonomous_runbooks=("product-reviews-config-rollback",),
        allowed_deployments=("product-reviews",),
        gitops_repository="sandbox/m22-gitops",
        gitops_observe_interval_seconds=1,
        gitops_merge_timeout_seconds=60,
        gitops_runtime_timeout_seconds=180,
        verification_settle_seconds=0,
        verification_interval_seconds=1,
        verification_polls=3,
        verification_consecutive_healthy_polls=3,
        verification_minimum_request_count=5,
        saga_backend="file",
        saga_path=str(evidence_dir / "sagas"),
    )


def incident_from_samples(
    settings: Settings,
    samples: list[float],
    *,
    incident_id: str,
) -> Incident:
    now = int(time.time())
    query = "sandbox exact product-reviews review RPC p95"
    series = [
        {
            "metric": {"service_name": "product-reviews"},
            "values": [
                [now - (len(samples) - index) * 15, str(value)]
                for index, value in enumerate(samples)
            ],
        }
    ]
    decision = Detector(settings).latency("product-reviews", series, query)
    if not decision.anomalous:
        raise RuntimeError("sandbox samples did not produce a detector incident")
    return Incident(
        incident_id=incident_id,
        incident_type=decision.incident_type,
        severity=decision.severity,
        affected_service=decision.service,
        confidence=decision.confidence,
        suspected_root_cause=decision.root_cause,
        impact=decision.impact,
        evidence=decision.evidence,
        rca_candidates=decision.candidates,
        runbook_id=decision.runbook_id,
        recommended_action=decision.recommended_action,
    )


def measured_verifier(
    traffic: ServiceTraffic,
    runs: list[dict[str, Any]],
):
    async def verify(_target: str) -> dict[str, Any]:
        await asyncio.to_thread(traffic.restart)
        samples = await asyncio.to_thread(traffic.sample, 5)
        result = {
            "healthy": percentile95(samples) < 250,
            "request_count": len(samples),
            "p95_latency_ms": round(percentile95(samples), 3),
            "rpc": "/api/product-reviews/<id>",
            "samples_ms": [round(value, 3) for value in samples],
        }
        runs.append(result)
        return result

    return verify


def argo_snapshot(context: str) -> dict[str, Any]:
    application = json.loads(
        run(
            "kubectl",
            "--context",
            context,
            "-n",
            "argocd",
            "get",
            "application",
            "techx-corp",
            "-o",
            "json",
        )
    )
    return {
        "sync": (application.get("status") or {}).get("sync"),
        "health": (application.get("status") or {}).get("health"),
        "self_heal": application["spec"]["syncPolicy"]["automated"]["selfHeal"],
    }


async def run_success_drill(
    *,
    context: str,
    repository: DisposableRepository,
    evidence_dir: Path,
) -> dict[str, Any]:
    fault_env = set(MANAGED_ENV_NAMES)
    repository_url = repository.git_url
    apply_application(context, repository_url)
    wait_for_application(
        context,
        expected_env=set(),
        remediation_id=None,
    )
    traffic = ServiceTraffic(context, "m22")
    traffic.start()
    try:
        healthy_baseline = traffic.sample(6)
        fault_sha = repository.inject_fault()
        simulate_git_webhook(context, "techx-corp")
        wait_for_application(
            context,
            expected_env=fault_env,
            remediation_id=None,
        )
        traffic.restart()
        fault_samples = traffic.sample(3)
        detection_points = [*healthy_baseline, *fault_samples]
        print(
            json.dumps(
                {
                    "event": "sandbox_latency_samples",
                    "healthy_ms": [round(value, 3) for value in healthy_baseline],
                    "fault_ms": [round(value, 3) for value in fault_samples],
                }
            )
        )

        settings = replace(
            Settings(),
            namespace="m22",
            services=("product-reviews",),
            generic_signal_services=("product-reviews",),
            llm_services=(),
            llm_log_services=(),
            service_slo_targets={},
            sustained_polls=1,
            latency_threshold_ms=500,
            latency_high_multiplier=1.2,
            remediation_confidence_threshold=0.5,
            remediation_mode="gitops/live",
            autonomous_remediation_enabled=True,
            autonomous_runbooks=("product-reviews-config-rollback",),
            allowed_deployments=("product-reviews",),
            gitops_repository="sandbox/m22-gitops",
            gitops_observe_interval_seconds=1,
            gitops_merge_timeout_seconds=60,
            gitops_runtime_timeout_seconds=180,
            verification_settle_seconds=0,
            verification_interval_seconds=1,
            verification_polls=3,
            verification_consecutive_healthy_polls=3,
            verification_minimum_request_count=5,
            saga_backend="file",
            saga_path=str(evidence_dir / "sagas"),
        )
        adapter = LocalPullRequestAdapter(
            repository,
            context=context,
            application="techx-corp",
        )
        runtime_observer = KubernetesRuntimeObserver("m22")
        target_lock = KubernetesLeaseTargetLock("m22")

        verification_runs: list[dict[str, Any]] = []

        async def verifier(_target: str) -> dict[str, Any]:
            await asyncio.to_thread(traffic.restart)
            samples = await asyncio.to_thread(traffic.sample, 5)
            result = {
                "healthy": percentile95(samples) < 250,
                "request_count": len(samples),
                "p95_latency_ms": round(percentile95(samples), 3),
                "rpc": "/api/product-reviews/<id>",
                "samples_ms": [round(value, 3) for value in samples],
            }
            verification_runs.append(result)
            return result

        saga_store = FileSagaStore(evidence_dir / "sagas")
        remediation = RemediationController(
            settings,
            adapter=adapter,
            runtime_observer=runtime_observer,
            target_lock=target_lock,
            verifier=verifier,
            saga_store=saga_store,
        )
        incident_store = IncidentStore(cooldown_seconds=0)
        worker = AIOpsWorker(
            settings,
            MeasuredTelemetry(detection_points),
            Detector(settings),
            incident_store,
            remediation=remediation,
        )
        await worker.poll_once()
        if worker._remediation_tasks:
            await asyncio.gather(
                *list(worker._remediation_tasks), return_exceptions=False
            )
        incidents = await incident_store.list()
        if len(incidents) != 1:
            raise RuntimeError(f"expected one detector incident, got {len(incidents)}")
        incident = incidents[0]
        saga = next(
            (
                item
                for item in await saga_store.list_all()
                if item.incident_id == incident.incident_id
            ),
            None,
        )
        if saga is None:
            raise RuntimeError("durable remediation saga was not persisted")
        wait_for_application(
            context,
            expected_env=set(),
            remediation_id=incident.incident_id,
        )
        runtime = await runtime_observer.observe_deployment("product-reviews")
        application = json.loads(
            run(
                "kubectl",
                "--context",
                context,
                "-n",
                "argocd",
                "get",
                "application",
                "techx-corp",
                "-o",
                "json",
            )
        )
        evidence = {
            "schema_version": 1,
            "scenario": "success",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "kind_context": context,
            "argo_version": "v3.4.2",
            "repository": "disposable-local-git",
            "known_good_sha": repository.known_good_sha,
            "fault_sha": fault_sha,
            "healthy_baseline_ms": [round(value, 3) for value in healthy_baseline],
            "fault_samples_ms": [round(value, 3) for value in fault_samples],
            "detector_incident": incident.model_dump(mode="json"),
            "verification_runs": verification_runs,
            "runtime_observation": runtime,
            "argo": {
                "sync": (application.get("status") or {}).get("sync"),
                "health": (application.get("status") or {}).get("health"),
                "self_heal": application["spec"]["syncPolicy"]["automated"]["selfHeal"],
            },
            "saga": saga.public_evidence(),
            "outcome": {
                "incident_status": incident.status.value,
                "saga_phase": saga.phase.value,
                "saga_outcome": saga.outcome.value if saga.outcome else None,
                "managed_env_removed": runtime.get("managed_env_present") == [],
                "correlation_matches": (
                    runtime.get("remediation_id") == incident.incident_id
                ),
            },
            "claim_boundary": (
                "Kind/Argo runtime evidence level 5 in a disposable sandbox. "
                "The local adapter writes real Git branches/commits and enforces "
                "the three checks, but it does not prove GitHub App/rulesets or "
                "production behavior."
            ),
        }
        passed = (
            incident.status == IncidentStatus.RESOLVED
            and saga.outcome is not None
            and saga.outcome.value == "resolved"
            and evidence["outcome"]["managed_env_removed"]
            and evidence["outcome"]["correlation_matches"]
            and evidence["argo"]["self_heal"] is True
            and all(item["healthy"] for item in verification_runs)
        )
        evidence["passed"] = passed
        if not passed:
            raise RuntimeError("success drill did not meet its pass boundary")
        return evidence
    finally:
        traffic.stop()


async def run_forced_wrong_drill(
    *,
    context: str,
    repository: DisposableRepository,
    evidence_dir: Path,
) -> dict[str, Any]:
    fault_env = set(MANAGED_ENV_NAMES)
    repository_url = repository.git_url
    apply_application(context, repository_url)
    wait_for_application(context, expected_env=set(), remediation_id=None)
    traffic = ServiceTraffic(context, "m22")
    traffic.start()
    try:
        healthy_baseline = traffic.sample(6)
        fault_sha = repository.inject_fault()
        simulate_git_webhook(context, "techx-corp")
        wait_for_application(
            context,
            expected_env=fault_env,
            remediation_id=None,
        )
        traffic.restart()
        fault_samples = traffic.sample(3)
        settings = sandbox_settings(evidence_dir)
        incident = incident_from_samples(
            settings,
            [*healthy_baseline, *fault_samples],
            incident_id="inc-forcedwrong",
        )
        forced_policy_sha = repository.enable_forced_wrong(incident.incident_id)
        simulate_git_webhook(context, "techx-corp")

        verification_runs: list[dict[str, Any]] = []
        adapter = LocalPullRequestAdapter(
            repository,
            context=context,
            application="techx-corp",
        )
        runtime_observer = KubernetesRuntimeObserver("m22")
        saga_store = FileSagaStore(evidence_dir / "sagas")
        controller = RemediationController(
            settings,
            adapter=adapter,
            runtime_observer=runtime_observer,
            target_lock=KubernetesLeaseTargetLock("m22"),
            verifier=measured_verifier(traffic, verification_runs),
            saga_store=saga_store,
        )
        await controller.handle_incident(incident)
        saga = await saga_store.get_by_incident(incident.incident_id)
        if saga is None:
            raise RuntimeError("forced-wrong saga was not persisted")

        wait_for_application(
            context,
            expected_env=fault_env,
            remediation_id=None,
        )
        runtime = await runtime_observer.observe_deployment("product-reviews")
        git(repository.work, "fetch", "origin")
        main_sha = git(repository.work, "rev-parse", "origin/main")
        current, _ = adapter._show_yaml(
            main_sha,
            "environments/production/app-values.yaml",
        )
        current_hash = structured_hash(component(current, "product-reviews"))
        original_hash = (
            saga.remediation.before_hash if saga.remediation is not None else None
        )
        compensation_hash = (
            saga.compensation.after_hash if saga.compensation is not None else None
        )
        evidence = {
            "schema_version": 1,
            "scenario": "forced-wrong-compensation",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "kind_context": context,
            "argo_version": "v3.4.2",
            "repository": "disposable-local-git",
            "known_good_sha": repository.known_good_sha,
            "fault_sha": fault_sha,
            "forced_wrong_policy_sha": forced_policy_sha,
            "healthy_baseline_ms": [round(value, 3) for value in healthy_baseline],
            "fault_samples_ms": [round(value, 3) for value in fault_samples],
            "incident": incident.model_dump(mode="json"),
            "verification_runs": verification_runs,
            "runtime_observation": runtime,
            "argo": argo_snapshot(context),
            "saga": saga.public_evidence(),
            "restoration": {
                "original_target_hash": original_hash,
                "compensation_target_hash": compensation_hash,
                "current_target_hash": current_hash,
                "original_identity_restored": (
                    original_hash == compensation_hash == current_hash
                ),
                "fault_still_active": set(runtime["managed_env_present"]) == fault_env,
                "remediation_annotation_removed": (
                    runtime.get("remediation_id") is None
                ),
            },
            "transaction_counts": {
                "remediation_prs": 1 if saga.remediation else 0,
                "compensation_prs": 1 if saga.compensation else 0,
            },
            "claim_boundary": (
                "Kind/Argo runtime evidence level 5 in a disposable sandbox. "
                "The signed forced-wrong profile and local PR/check boundary do "
                "not prove GitHub App/rulesets or production behavior."
            ),
        }
        evidence["passed"] = (
            incident.status == IncidentStatus.ESCALATED
            and incident.mutation_blocked
            and saga.phase == SagaPhase.TERMINAL
            and saga.outcome is not None
            and saga.outcome.value == "compensated_escalated"
            and evidence["restoration"]["original_identity_restored"]
            and evidence["restoration"]["fault_still_active"]
            and evidence["restoration"]["remediation_annotation_removed"]
            and evidence["transaction_counts"]
            == {"remediation_prs": 1, "compensation_prs": 1}
            and len(verification_runs) == 3
            and not any(item["healthy"] for item in verification_runs)
            and evidence["argo"]["self_heal"] is True
        )
        if not evidence["passed"]:
            raise RuntimeError("forced-wrong drill did not meet its pass boundary")
        return evidence
    finally:
        traffic.stop()


async def run_restart_recovery_drill(
    *,
    context: str,
    repository: DisposableRepository,
    evidence_dir: Path,
) -> dict[str, Any]:
    fault_env = set(MANAGED_ENV_NAMES)
    repository_url = repository.git_url
    apply_application(context, repository_url)
    wait_for_application(context, expected_env=set(), remediation_id=None)
    traffic = ServiceTraffic(context, "m22")
    traffic.start()
    try:
        healthy_baseline = traffic.sample(6)
        fault_sha = repository.inject_fault()
        simulate_git_webhook(context, "techx-corp")
        wait_for_application(
            context,
            expected_env=fault_env,
            remediation_id=None,
        )
        traffic.restart()
        fault_samples = traffic.sample(3)
        settings = sandbox_settings(evidence_dir)
        incident = incident_from_samples(
            settings,
            [*healthy_baseline, *fault_samples],
            incident_id="inc-restartrace",
        )
        saga_store = FileSagaStore(evidence_dir / "sagas")
        lock = KubernetesLeaseTargetLock("m22")
        runtime_observer = KubernetesRuntimeObserver("m22")
        verification_runs: list[dict[str, Any]] = []

        first_adapter = LocalPullRequestAdapter(
            repository,
            context=context,
            application="techx-corp",
        )
        first_controller = RemediationController(
            settings,
            adapter=first_adapter,
            runtime_observer=runtime_observer,
            target_lock=lock,
            verifier=measured_verifier(traffic, verification_runs),
            saga_store=saga_store,
        )
        first_controller.authorize_by_policy(incident)
        saga = RemediationSaga(
            incident_id=incident.incident_id,
            incident_type=incident.incident_type,
            target="product-reviews",
            policy_version=settings.remediation_policy_version,
        )
        saga.note("gitops_preflight_started", mode=settings.remediation_mode)
        if not await lock.acquire(
            "product-reviews",
            incident.incident_id,
            settings.remediation_lock_ttl_seconds,
        ):
            raise RuntimeError("restart drill could not acquire target Lease")
        saga.lock_held = True
        transaction = await first_adapter.prepare(incident)
        saga.remediation = transaction
        saga.base_sha = transaction.base_sha
        saga.known_good_sha = transaction.known_good_sha
        saga.policy_sha = transaction.policy_sha
        saga.expected_runtime_identity = {
            "remediation_id": incident.incident_id,
            "managed_env_present": [],
            "target_hash": transaction.after_hash,
        }
        saga.advance(SagaPhase.PR_OPEN)
        await saga_store.save(saga)

        recovery_events: list[dict[str, Any]] = []
        lost_pr_response = copy.deepcopy(transaction)
        await first_adapter.submit(lost_pr_response)
        recovery_events.append(
            {
                "fault": "api_timeout_after_branch_and_pr_write",
                "remote_head_sha": lost_pr_response.head_sha,
                "persisted_phase": saga.phase.value,
                "persisted_pr_number": saga.remediation.pr_number,
            }
        )

        second_adapter = LocalPullRequestAdapter(
            repository,
            context=context,
            application="techx-corp",
        )
        second_saga = await saga_store.get(saga.saga_id)
        if second_saga is None or second_saga.remediation is None:
            raise RuntimeError("restart could not reload PR_OPEN saga")
        rediscovered = await second_adapter.submit(second_saga.remediation)
        second_saga.remediation = rediscovered
        second_saga.advance(SagaPhase.CHECKS_PENDING)
        observation = await second_adapter.observe(rediscovered)
        rediscovered.checks = dict(observation.checks)
        await saga_store.save(second_saga)
        recovery_events.append(
            {
                "recovery": "branch_and_pr_rediscovered",
                "head_sha": rediscovered.head_sha,
                "pr_number": rediscovered.pr_number,
                "checks": rediscovered.checks,
            }
        )

        lost_merge_response = copy.deepcopy(rediscovered)
        await second_adapter.submit(lost_merge_response, queue_merge=True)
        recovery_events.append(
            {
                "fault": "api_timeout_after_merge_write",
                "actual_merge_sha": lost_merge_response.merge_sha,
                "persisted_phase": second_saga.phase.value,
                "persisted_merge_sha": second_saga.remediation.merge_sha,
            }
        )

        third_adapter = LocalPullRequestAdapter(
            repository,
            context=context,
            application="techx-corp",
        )
        third_controller = RemediationController(
            settings,
            adapter=third_adapter,
            runtime_observer=runtime_observer,
            target_lock=KubernetesLeaseTargetLock("m22"),
            verifier=measured_verifier(traffic, verification_runs),
            saga_store=saga_store,
        )
        third_saga = await saga_store.get(saga.saga_id)
        if third_saga is None:
            raise RuntimeError("restart could not reload CHECKS_PENDING saga")
        resume_result = await third_controller.resume_saga(third_saga)
        terminal = await saga_store.get(saga.saga_id)
        if terminal is None or terminal.remediation is None:
            raise RuntimeError("restart recovery did not persist terminal saga")

        wait_for_application(
            context,
            expected_env=set(),
            remediation_id=incident.incident_id,
        )
        runtime = await runtime_observer.observe_deployment("product-reviews")
        git(repository.work, "fetch", "origin")
        branches = [
            item.strip()
            for item in git(
                repository.work,
                "branch",
                "-r",
                "--list",
                f"origin/aiops/remediation/{incident.incident_id}",
            ).splitlines()
            if item.strip()
        ]
        main_sha = git(repository.work, "rev-parse", "origin/main")
        recovery_events.append(
            {
                "recovery": "merge_rediscovered_then_runtime_verified",
                "resume_result": resume_result,
                "observed_main_sha": main_sha,
            }
        )
        evidence = {
            "schema_version": 1,
            "scenario": "restart-api-timeout-merge-race",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "kind_context": context,
            "argo_version": "v3.4.2",
            "repository": "disposable-local-git",
            "known_good_sha": repository.known_good_sha,
            "fault_sha": fault_sha,
            "healthy_baseline_ms": [round(value, 3) for value in healthy_baseline],
            "fault_samples_ms": [round(value, 3) for value in fault_samples],
            "incident": incident.model_dump(mode="json"),
            "recovery_events": recovery_events,
            "controller_restarts": 2,
            "verification_runs": verification_runs,
            "runtime_observation": runtime,
            "argo": argo_snapshot(context),
            "saga": terminal.public_evidence(),
            "idempotency": {
                "remediation_branches": branches,
                "remediation_branch_count": len(branches),
                "synthetic_pr_numbers": [terminal.remediation.pr_number],
                "pr_count": 1 if terminal.remediation.pr_number == 1 else 0,
                "compensation_pr_count": 1 if terminal.compensation else 0,
                "merge_sha_matches_main": (terminal.remediation.merge_sha == main_sha),
            },
            "claim_boundary": (
                "Kind/Argo runtime evidence level 5 in a disposable sandbox. "
                "Lost API responses are injected after real branch and merge "
                "writes; the local PR identity models, but does not prove, "
                "GitHub App/ruleset behavior."
            ),
        }
        evidence["passed"] = (
            terminal.phase == SagaPhase.TERMINAL
            and terminal.outcome is not None
            and terminal.outcome.value == "resolved"
            and runtime.get("managed_env_present") == []
            and runtime.get("remediation_id") == incident.incident_id
            and evidence["idempotency"]["remediation_branch_count"] == 1
            and evidence["idempotency"]["pr_count"] == 1
            and evidence["idempotency"]["compensation_pr_count"] == 0
            and evidence["idempotency"]["merge_sha_matches_main"]
            and len(verification_runs) == 3
            and all(item["healthy"] for item in verification_runs)
            and evidence["argo"]["self_heal"] is True
        )
        if not evidence["passed"]:
            raise RuntimeError("restart recovery drill did not meet its pass boundary")
        return evidence
    finally:
        traffic.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=("success", "forced-wrong", "restart-recovery"),
        default="success",
    )
    parser.add_argument(
        "--context",
        default="kind-m22-gitops-sandbox",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Disposable runtime directory; a fresh temp directory is used by default.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = args.workspace or Path(tempfile.mkdtemp(prefix="m22-gitops-sandbox-"))
    workspace.mkdir(parents=True, exist_ok=True)
    evidence_dir = args.evidence_dir.resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    repository = DisposableRepository(workspace)
    try:
        repository.initialize()
        repository.start_server()
        runners = {
            "success": run_success_drill,
            "forced-wrong": run_forced_wrong_drill,
            "restart-recovery": run_restart_recovery_drill,
        }
        report = asyncio.run(
            runners[args.scenario](
                context=args.context,
                repository=repository,
                evidence_dir=evidence_dir,
            )
        )
        report["workspace"] = (
            "caller-provided-workspace"
            if args.workspace
            else "disposable-temp-workspace"
        )
        report_path = evidence_dir / f"{args.scenario}.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "passed": report["passed"],
                    "scenario": args.scenario,
                    "incident_id": (
                        report.get("detector_incident") or report["incident"]
                    )["incident_id"],
                    "merge_sha": report["saga"]["remediation"]["merge_sha"],
                    "saga_outcome": report["saga"]["outcome"],
                    "evidence": str(report_path),
                },
                indent=2,
            )
        )
        return 0
    finally:
        repository.stop_server()


if __name__ == "__main__":
    raise SystemExit(main())
