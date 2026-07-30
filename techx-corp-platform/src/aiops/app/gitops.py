"""GitHub/Argo adapters for Mandate 22 GitOps-native remediation."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx
import yaml

from .models import Incident, utcnow
from .saga import GitTransaction, RemediationSaga

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
INCIDENT_ID = re.compile(r"^inc-[a-z0-9-]{1,48}$")
CORRELATION_ANNOTATION = "aiops.techx.io/remediation-id"


class GitOpsError(RuntimeError):
    pass


class StaleBaseError(GitOpsError):
    pass


class ChecksFailedError(GitOpsError):
    pass


class PullRequestClosedError(GitOpsError):
    pass


@dataclass(frozen=True)
class GitObservation:
    state: str
    checks: dict[str, str]
    head_sha: str | None = None
    merge_sha: str | None = None
    merge_queued: bool = False
    base_sha: str | None = None
    reason: str | None = None


class GitOpsRemediationAdapter(Protocol):
    async def prepare(
        self,
        incident: Incident,
        *,
        compensation_for: RemediationSaga | None = None,
    ) -> GitTransaction: ...

    async def submit(
        self, transaction: GitTransaction, *, queue_merge: bool = False
    ) -> GitTransaction: ...

    async def observe(self, transaction: GitTransaction) -> GitObservation: ...

    async def cancel(self, transaction: GitTransaction, reason: str) -> None: ...


class RuntimeObserver(Protocol):
    async def observe_deployment(self, deployment: str) -> dict[str, Any]: ...


class TargetLock(Protocol):
    async def acquire(self, target: str, incident_id: str, ttl: int) -> bool: ...

    async def renew(self, target: str, incident_id: str, ttl: int) -> bool: ...

    async def release(self, target: str, incident_id: str) -> None: ...


class TokenProvider(Protocol):
    def token(self) -> str: ...


def structured_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def component(document: dict[str, Any], name: str) -> dict[str, Any]:
    try:
        value = document["components"][name]
    except (KeyError, TypeError) as exc:
        raise GitOpsError(f"component {name!r} is absent from target values") from exc
    if not isinstance(value, dict):
        raise GitOpsError(f"component {name!r} must be a mapping")
    return value


def build_remediation_document(
    current: dict[str, Any],
    known_good: dict[str, Any],
    *,
    component_name: str,
    managed_env_names: tuple[str, ...],
    incident_id: str,
) -> dict[str, Any]:
    """Restore only managed env entries and add the rollout correlation marker."""

    result = copy.deepcopy(current)
    target = component(result, component_name)
    known_target = component(known_good, component_name)
    managed = set(managed_env_names)
    current_env = list(target.get("envOverrides") or [])
    known_env = list(known_target.get("envOverrides") or [])
    known_by_name = {
        item.get("name"): copy.deepcopy(item)
        for item in known_env
        if isinstance(item, dict) and item.get("name") in managed
    }
    replaced: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in current_env:
        if not isinstance(item, dict):
            raise GitOpsError("product-reviews envOverrides entries must be mappings")
        name = item.get("name")
        if name not in managed:
            output.append(copy.deepcopy(item))
        elif name in known_by_name:
            output.append(known_by_name[name])
            replaced.add(name)
    for item in known_env:
        name = item.get("name") if isinstance(item, dict) else None
        if name in managed and name not in replaced:
            output.append(copy.deepcopy(item))
            replaced.add(name)
    if output:
        target["envOverrides"] = output
    else:
        target.pop("envOverrides", None)
    annotations = dict(target.get("podAnnotations") or {})
    annotations[CORRELATION_ANNOTATION] = incident_id
    target["podAnnotations"] = annotations
    return result


def build_forced_wrong_document(
    current: dict[str, Any], *, component_name: str, incident_id: str
) -> dict[str, Any]:
    result = copy.deepcopy(current)
    target = component(result, component_name)
    annotations = dict(target.get("podAnnotations") or {})
    annotations[CORRELATION_ANNOTATION] = incident_id
    target["podAnnotations"] = annotations
    return result


def forced_wrong_active(policy: dict[str, Any], incident_id: str) -> bool:
    profile = policy.get("forcedWrongProfile") or {}
    if not profile.get("enabled"):
        return False
    if profile.get("allowedDelta") != "correlation_annotation_only":
        raise GitOpsError("forced-wrong profile has an unsupported delta")
    if profile.get("incidentId") != incident_id:
        raise GitOpsError("forced-wrong profile incident does not match")
    try:
        expiry = datetime.fromisoformat(
            str(profile["expiresAt"]).replace("Z", "+00:00")
        )
    except (KeyError, ValueError) as exc:
        raise GitOpsError("forced-wrong profile expiry is invalid") from exc
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise GitOpsError("forced-wrong profile is expired")
    return True


def build_compensation_document(
    current: dict[str, Any],
    saga: RemediationSaga,
    *,
    component_name: str,
) -> dict[str, Any]:
    transaction = saga.remediation
    if transaction is None or transaction.before_document is None:
        raise GitOpsError("compensation requires the exact pre-action document")
    result = copy.deepcopy(current)
    original_target = copy.deepcopy(
        component(transaction.before_document, component_name)
    )
    result.setdefault("components", {})[component_name] = original_target
    return result


def managed_env_map(
    document: dict[str, Any], component_name: str, managed_env_names: tuple[str, ...]
) -> dict[str, Any]:
    managed = set(managed_env_names)
    return {
        item.get("name"): item
        for item in component(document, component_name).get("envOverrides") or []
        if isinstance(item, dict) and item.get("name") in managed
    }


class GitHubAppTokenProvider:
    def __init__(
        self,
        *,
        app_id: str,
        installation_id: str,
        private_key_path: str,
        api_url: str = "https://api.github.com",
        proxy_url: str | None = None,
    ):
        self.app_id = app_id
        self.installation_id = installation_id
        self.private_key_path = Path(private_key_path)
        self.api_url = api_url.rstrip("/")
        self.proxy_url = proxy_url
        self._token = ""
        self._expires_at = 0.0

    def token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        if not self.app_id or not self.installation_id:
            raise GitOpsError("GitHub App id and installation id are required")
        if not self.private_key_path.is_file():
            raise GitOpsError("GitHub App private key mount is unavailable")
        try:
            import jwt
        except ImportError as exc:  # pragma: no cover - packaging gate
            raise GitOpsError("PyJWT[crypto] is required for GitHub App auth") from exc
        now = int(time.time())
        signed = jwt.encode(
            {"iat": now - 30, "exp": now + 540, "iss": self.app_id},
            self.private_key_path.read_text(encoding="utf-8"),
            algorithm="RS256",
        )
        with httpx.Client(
            proxy=self.proxy_url, timeout=15, follow_redirects=False
        ) as client:
            response = client.post(
                (
                    f"{self.api_url}/app/installations/"
                    f"{self.installation_id}/access_tokens"
                ),
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {signed}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        if response.status_code != 201:
            raise GitOpsError(
                f"GitHub App authentication failed ({response.status_code})"
            )
        data = response.json()
        self._token = str(data["token"])
        # Installation tokens last one hour. Avoid parsing a timestamp here.
        self._expires_at = time.time() + 3300
        return self._token


class FileTokenProvider:
    """Read a short-lived credential from a read-only Secret/file mount."""

    def __init__(
        self,
        *,
        token_path: str,
        expected_login: str = "",
        api_url: str = "https://api.github.com",
        proxy_url: str | None = None,
    ):
        self.token_path = Path(token_path)
        self.expected_login = expected_login
        self.api_url = api_url.rstrip("/")
        self.proxy_url = proxy_url
        self._login = ""

    def token(self) -> str:
        if not self.token_path.is_file():
            raise GitOpsError("GitHub token file mount is unavailable")
        token = self.token_path.read_text(encoding="utf-8").strip()
        if not token:
            raise GitOpsError("GitHub token file is empty")
        return token

    def login(self) -> str:
        if self._login:
            return self._login
        with httpx.Client(
            proxy=self.proxy_url, timeout=15, follow_redirects=False
        ) as client:
            response = client.get(
                f"{self.api_url}/user",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.token()}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        if response.status_code != 200:
            raise GitOpsError(
                f"GitHub token identity check failed ({response.status_code})"
            )
        self._login = str(response.json()["login"])
        if self.expected_login and self._login != self.expected_login:
            raise GitOpsError("GitHub token identity does not match configured login")
        return self._login


class GitHubGitOpsRemediationAdapter:
    """Idempotent GitHub transaction adapter.

    Every ambiguous write is followed by branch/PR rediscovery before a retry.
    The adapter never writes main directly and auto-merge is enabled only after
    the required checks are observed successful.
    """

    def __init__(
        self,
        *,
        repository: str,
        base_branch: str,
        policy_path: str,
        token_provider: TokenProvider,
        reviewer_token_provider: FileTokenProvider | None = None,
        merge_strategy: str = "auto",
        api_url: str = "https://api.github.com",
        proxy_url: str | None = None,
    ):
        self.repository = repository
        self.base_branch = base_branch
        self.policy_path = policy_path
        self.token_provider = token_provider
        self.reviewer_token_provider = reviewer_token_provider
        self.merge_strategy = merge_strategy
        self.api_url = api_url.rstrip("/")
        self.proxy_url = proxy_url

    def _headers(self, *, reviewer: bool = False) -> dict[str, str]:
        provider = (
            self.reviewer_token_provider
            if reviewer and self.reviewer_token_provider is not None
            else self.token_provider
        )
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {provider.token()}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @staticmethod
    def _metadata(transaction: GitTransaction) -> dict[str, Any]:
        return {
            "schemaVersion": 2,
            "kind": transaction.kind,
            "incidentId": transaction.branch.rsplit("/", 1)[-1],
            "component": "product-reviews",
            "targetFile": transaction.target_file,
            "baseSha": transaction.base_sha,
            "knownGoodSha": transaction.known_good_sha,
            "beforeHash": transaction.before_hash,
            "afterHash": transaction.after_hash,
            "mergeStrategy": transaction.merge_strategy,
        }

    @classmethod
    def _pr_body(cls, transaction: GitTransaction) -> str:
        return (
            "Mandate #22 bounded GitOps transaction.\n\n"
            "```json\n"
            f"{json.dumps(cls._metadata(transaction), sort_keys=True)}\n"
            "```"
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected: tuple[int, ...] = (200,),
        reviewer: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        with httpx.Client(
            proxy=self.proxy_url, timeout=20, follow_redirects=False
        ) as client:
            response = client.request(
                method,
                f"{self.api_url}{path}",
                headers=self._headers(reviewer=reviewer),
                **kwargs,
            )
        if response.status_code not in expected:
            raise GitOpsError(f"GitHub {method} {path} failed ({response.status_code})")
        return response

    def _contents(self, path: str, ref: str) -> tuple[dict[str, Any], str]:
        response = self._request(
            "GET",
            f"/repos/{self.repository}/contents/{path}",
            params={"ref": ref},
        ).json()
        raw = base64.b64decode(response["content"]).decode("utf-8")
        document = yaml.safe_load(raw)
        if not isinstance(document, dict):
            raise GitOpsError(f"{path} at {ref} is not a YAML mapping")
        return document, str(response["sha"])

    def _policy(self, base_sha: str) -> tuple[dict[str, Any], str]:
        policy, blob_sha = self._contents(self.policy_path, base_sha)
        required = {
            "policyVersion",
            "incidentType",
            "runbook",
            "repository",
            "baseBranch",
            "targetFile",
            "component",
            "managedEnvNames",
            "knownGoodCommit",
            "requiredChecks",
        }
        missing = sorted(required - set(policy))
        if missing:
            raise GitOpsError("GitOps policy missing: " + ", ".join(missing))
        if policy["repository"] != self.repository:
            raise GitOpsError("policy repository does not match configured repository")
        if policy["baseBranch"] != self.base_branch:
            raise GitOpsError("policy base branch does not match configured branch")
        if not FULL_SHA.fullmatch(str(policy["knownGoodCommit"])):
            raise GitOpsError("knownGoodCommit must be a full 40-character SHA")
        compare = self._request(
            "GET",
            (
                f"/repos/{self.repository}/compare/"
                f"{policy['knownGoodCommit']}...{base_sha}"
            ),
        ).json()
        if compare.get("status") not in {"ahead", "identical"}:
            raise GitOpsError("known-good commit is not an ancestor of base")
        return policy, blob_sha

    def _base_sha(self) -> str:
        data = self._request(
            "GET",
            f"/repos/{self.repository}/git/ref/heads/{self.base_branch}",
        ).json()
        return str(data["object"]["sha"])

    async def prepare(
        self,
        incident: Incident,
        *,
        compensation_for: RemediationSaga | None = None,
    ) -> GitTransaction:
        import asyncio

        return await asyncio.to_thread(
            self._prepare_sync, incident, compensation_for=compensation_for
        )

    def _prepare_sync(
        self,
        incident: Incident,
        *,
        compensation_for: RemediationSaga | None,
    ) -> GitTransaction:
        if not INCIDENT_ID.fullmatch(incident.incident_id):
            raise GitOpsError("incident id is not safe for a Git branch")
        base_sha = self._base_sha()
        policy, policy_sha = self._policy(base_sha)
        if incident.incident_type != policy["incidentType"]:
            raise GitOpsError("incident type is outside GitOps policy")
        if incident.runbook_id != policy["runbook"]:
            raise GitOpsError("runbook is outside GitOps policy")
        if incident.affected_service != policy["component"]:
            raise GitOpsError("target is outside GitOps policy")
        target_file = str(policy["targetFile"])
        current, current_blob_sha = self._contents(target_file, base_sha)
        kind = "compensation" if compensation_for else "remediation"
        if compensation_for:
            after = build_compensation_document(
                current,
                compensation_for,
                component_name=str(policy["component"]),
            )
        else:
            if forced_wrong_active(policy, incident.incident_id):
                after = build_forced_wrong_document(
                    current,
                    component_name=str(policy["component"]),
                    incident_id=incident.incident_id,
                )
            else:
                known_good, _ = self._contents(
                    target_file, str(policy["knownGoodCommit"])
                )
                after = build_remediation_document(
                    current,
                    known_good,
                    component_name=str(policy["component"]),
                    managed_env_names=tuple(policy["managedEnvNames"]),
                    incident_id=incident.incident_id,
                )
        before_hash = structured_hash(component(current, str(policy["component"])))
        after_hash = structured_hash(component(after, str(policy["component"])))
        if before_hash == after_hash:
            raise GitOpsError("prepared transaction has no semantic target change")
        branch = f"aiops/{kind}/{incident.incident_id}"
        transaction = GitTransaction(
            kind=kind,
            merge_strategy=self.merge_strategy,
            branch=branch,
            base_sha=base_sha,
            policy_sha=policy_sha,
            known_good_sha=str(policy["knownGoodCommit"]),
            target_file=target_file,
            before_hash=before_hash,
            after_hash=after_hash,
            before_file_sha=current_blob_sha,
            before_document=current,
            after_document=after,
            state="prepared",
        )
        return transaction

    async def submit(
        self, transaction: GitTransaction, *, queue_merge: bool = False
    ) -> GitTransaction:
        import asyncio

        return await asyncio.to_thread(
            self._submit_sync, transaction, queue_merge=queue_merge
        )

    def _submit_sync(
        self, transaction: GitTransaction, *, queue_merge: bool
    ) -> GitTransaction:
        discovered = self._discover(transaction)
        if discovered is not None:
            transaction = discovered
        elif queue_merge:
            raise GitOpsError("cannot queue merge before the PR exists")
        else:
            try:
                self._request(
                    "POST",
                    f"/repos/{self.repository}/git/refs",
                    expected=(201,),
                    json={
                        "ref": f"refs/heads/{transaction.branch}",
                        "sha": transaction.base_sha,
                    },
                )
            except (httpx.TimeoutException, httpx.TransportError):
                discovered = self._discover(transaction)
                if discovered is None:
                    raise
                transaction = discovered

        if not queue_merge and transaction.pr_number is None:
            if transaction.head_sha in {None, transaction.base_sha}:
                if transaction.after_document is None:
                    raise GitOpsError("prepared document is unavailable")
                rendered = yaml.safe_dump(
                    transaction.after_document,
                    sort_keys=False,
                    allow_unicode=True,
                )
                try:
                    response = self._request(
                        "PUT",
                        (
                            f"/repos/{self.repository}/contents/"
                            f"{transaction.target_file}"
                        ),
                        expected=(200, 201),
                        json={
                            "message": (
                                f"fix(aiops): {transaction.kind} "
                                f"{transaction.branch.rsplit('/', 1)[-1]}"
                            ),
                            "content": base64.b64encode(rendered.encode()).decode(),
                            "sha": transaction.before_file_sha,
                            "branch": transaction.branch,
                        },
                    ).json()
                    transaction.head_sha = str(response["commit"]["sha"])
                    transaction.after_file_sha = str(response["content"]["sha"])
                except (httpx.TimeoutException, httpx.TransportError):
                    discovered = self._discover(transaction)
                    if discovered is None or discovered.head_sha in {
                        None,
                        transaction.base_sha,
                    }:
                        raise
                    transaction = discovered

            # Rediscover immediately before PR creation. A timeout from a
            # previous attempt may have created it after the branch read.
            discovered = self._discover(transaction)
            if discovered is not None:
                transaction = discovered
            if transaction.pr_number is None:
                metadata = self._metadata(transaction)
                try:
                    pr = self._request(
                        "POST",
                        f"/repos/{self.repository}/pulls",
                        expected=(201,),
                        json={
                            "title": (
                                f"[AIOps] {transaction.kind} {metadata['incidentId']}"
                            ),
                            "head": transaction.branch,
                            "base": self.base_branch,
                            "body": self._pr_body(transaction),
                        },
                    ).json()
                    transaction.pr_number = int(pr["number"])
                    transaction.pr_node_id = str(pr["node_id"])
                    transaction.pr_url = str(pr["html_url"])
                    transaction.state = "open"
                except (httpx.TimeoutException, httpx.TransportError):
                    discovered = self._discover(transaction)
                    if discovered is None or discovered.pr_number is None:
                        raise
                    transaction = discovered

        if queue_merge and not transaction.merge_queued:
            if self.merge_strategy == "human":
                raise GitOpsError("human merge strategy cannot queue an automatic merge")
            if self.merge_strategy == "dual-token":
                return self._review_and_merge_sync(transaction)
            if not transaction.pr_node_id:
                raise GitOpsError("PR node id is required for auto-merge")
            mutation = """
            mutation($id: ID!) {
              enablePullRequestAutoMerge(input: {
                pullRequestId: $id,
                mergeMethod: SQUASH
              }) { pullRequest { autoMergeRequest { enabledAt } } }
            }
            """
            try:
                result = self._request(
                    "POST",
                    "/graphql",
                    json={
                        "query": mutation,
                        "variables": {"id": transaction.pr_node_id},
                    },
                ).json()
            except (httpx.TimeoutException, httpx.TransportError):
                discovered = self._discover(transaction)
                if discovered is None:
                    raise
                transaction = discovered
                if transaction.merge_sha or transaction.merge_queued:
                    return transaction
                # Explicit rediscovery proved the first write did not commit.
                result = self._request(
                    "POST",
                    "/graphql",
                    json={
                        "query": mutation,
                        "variables": {"id": transaction.pr_node_id},
                    },
                ).json()
            if result.get("errors"):
                raise GitOpsError("GitHub rules rejected auto-merge")
            transaction.merge_queued = True
            transaction.state = "merge_queued"
        return transaction

    def _discover(self, transaction: GitTransaction) -> GitTransaction | None:
        with httpx.Client(
            proxy=self.proxy_url, timeout=15, follow_redirects=False
        ) as client:
            branch = client.get(
                (
                    f"{self.api_url}/repos/{self.repository}/git/ref/heads/"
                    f"{transaction.branch}"
                ),
                headers=self._headers(),
            )
        if branch.status_code == 404:
            return None
        if branch.status_code != 200:
            raise GitOpsError(f"branch rediscovery failed ({branch.status_code})")
        transaction.head_sha = str(branch.json()["object"]["sha"])
        pulls = self._request(
            "GET",
            f"/repos/{self.repository}/pulls",
            params={
                "state": "all",
                "head": transaction.branch,
                "base": self.base_branch,
            },
        ).json()
        if len(pulls) > 1:
            raise GitOpsError("more than one PR exists for the idempotent branch")
        if pulls:
            pr = pulls[0]
            transaction.pr_number = int(pr["number"])
            transaction.pr_node_id = str(pr["node_id"])
            transaction.pr_url = str(pr["html_url"])
            transaction.merge_sha = (
                pr.get("merge_commit_sha") if pr.get("merged_at") else None
            )
            transaction.merge_queued = bool(pr.get("auto_merge")) or bool(
                transaction.merge_queued
            )
            transaction.state = "merged" if pr.get("merged_at") else "open"
            if pr.get("state") == "closed" and not pr.get("merged_at"):
                transaction.state = "closed"
        return transaction

    async def observe(self, transaction: GitTransaction) -> GitObservation:
        import asyncio

        return await asyncio.to_thread(self._observe_sync, transaction)

    def _observe_sync(self, transaction: GitTransaction) -> GitObservation:
        discovered = self._discover(transaction)
        if discovered is None or discovered.pr_number is None:
            return GitObservation(
                state="missing", checks={}, reason="branch_or_pr_missing"
            )
        transaction = discovered
        if transaction.merge_sha:
            return GitObservation(
                state="merged",
                checks=transaction.checks,
                head_sha=transaction.head_sha,
                merge_sha=transaction.merge_sha,
                merge_queued=transaction.merge_queued,
            )
        if transaction.state == "closed":
            return GitObservation(
                state="closed_unmerged",
                checks=transaction.checks,
                head_sha=transaction.head_sha,
                reason="pull request was closed without merge",
            )
        current_base = self._base_sha()
        if current_base != transaction.base_sha:
            return self._rebase_sync(transaction, current_base)
        if self.merge_strategy == "human":
            return GitObservation(
                state="awaiting_human_merge",
                checks=transaction.checks,
                head_sha=transaction.head_sha,
            )
        runs = self._request(
            "GET",
            f"/repos/{self.repository}/commits/{transaction.head_sha}/check-runs",
            reviewer=self.merge_strategy == "dual-token",
        ).json()
        checks = {
            str(item["name"]): str(item.get("conclusion") or item.get("status"))
            for item in runs.get("check_runs", [])
        }
        transaction.checks = checks
        return GitObservation(
            state="checks",
            checks=checks,
            head_sha=transaction.head_sha,
            merge_queued=transaction.merge_queued,
        )

    def _review_and_merge_sync(self, transaction: GitTransaction) -> GitTransaction:
        if self.reviewer_token_provider is None:
            raise GitOpsError("dual-token merge requires a reviewer token")
        if transaction.pr_number is None or not transaction.head_sha:
            raise GitOpsError("dual-token merge requires a PR and head SHA")
        reviewer_login = self.reviewer_token_provider.login()
        reviews = self._request(
            "GET",
            f"/repos/{self.repository}/pulls/{transaction.pr_number}/reviews",
            reviewer=True,
        ).json()
        approved = any(
            str((item.get("user") or {}).get("login", "")) == reviewer_login
            and item.get("state") == "APPROVED"
            and item.get("commit_id") == transaction.head_sha
            for item in reviews
        )
        if not approved:
            try:
                self._request(
                    "POST",
                    f"/repos/{self.repository}/pulls/{transaction.pr_number}/reviews",
                    expected=(200,),
                    reviewer=True,
                    json={
                        "event": "APPROVE",
                        "commit_id": transaction.head_sha,
                        "body": (
                            "Time-boxed Mandate 22 demo reviewer: all protected "
                            "checks were observed successful."
                        ),
                    },
                )
            except (httpx.TimeoutException, httpx.TransportError):
                reviews = self._request(
                    "GET",
                    f"/repos/{self.repository}/pulls/{transaction.pr_number}/reviews",
                    reviewer=True,
                ).json()
                if not any(
                    str((item.get("user") or {}).get("login", "")) == reviewer_login
                    and item.get("state") == "APPROVED"
                    and item.get("commit_id") == transaction.head_sha
                    for item in reviews
                ):
                    raise
        try:
            response = self._request(
                "PUT",
                f"/repos/{self.repository}/pulls/{transaction.pr_number}/merge",
                expected=(200,),
                reviewer=True,
                json={
                    "sha": transaction.head_sha,
                    "merge_method": "squash",
                    "commit_title": (
                        f"[AIOps demo] {transaction.kind} "
                        f"{transaction.branch.rsplit('/', 1)[-1]}"
                    ),
                },
            ).json()
        except (httpx.TimeoutException, httpx.TransportError):
            discovered = self._discover(transaction)
            if discovered is None or not discovered.merge_sha:
                raise
            return discovered
        if not response.get("merged"):
            raise GitOpsError("reviewer token could not merge the pull request")
        transaction.merge_queued = True
        transaction.merge_sha = str(response["sha"])
        transaction.state = "merged"
        return transaction

    def _rebase_sync(
        self, transaction: GitTransaction, current_base: str
    ) -> GitObservation:
        """Recompute the same PR branch when only non-managed base fields moved."""

        policy, policy_sha = self._policy(current_base)
        if transaction.policy_sha and policy_sha != transaction.policy_sha:
            return GitObservation(
                state="stale_managed",
                checks=transaction.checks,
                reason="protected policy changed on base",
                base_sha=current_base,
            )
        component_name = str(policy["component"])
        managed_names = tuple(policy["managedEnvNames"])
        current, current_blob_sha = self._contents(
            transaction.target_file, current_base
        )
        if transaction.before_document is None or transaction.after_document is None:
            return GitObservation(
                state="stale_managed",
                checks=transaction.checks,
                reason="durable documents unavailable for safe recompute",
                base_sha=current_base,
            )
        if managed_env_map(current, component_name, managed_names) != managed_env_map(
            transaction.before_document, component_name, managed_names
        ):
            return GitObservation(
                state="stale_managed",
                checks=transaction.checks,
                reason="managed fields changed on base",
                base_sha=current_base,
            )
        incident_id = transaction.branch.rsplit("/", 1)[-1]
        if transaction.kind == "remediation":
            if forced_wrong_active(policy, incident_id):
                after = build_forced_wrong_document(
                    current,
                    component_name=component_name,
                    incident_id=incident_id,
                )
            else:
                known_good, _ = self._contents(
                    transaction.target_file, str(policy["knownGoodCommit"])
                )
                after = build_remediation_document(
                    current,
                    known_good,
                    component_name=component_name,
                    managed_env_names=managed_names,
                    incident_id=incident_id,
                )
        else:
            after = copy.deepcopy(current)
            after.setdefault("components", {})[component_name] = copy.deepcopy(
                component(transaction.after_document, component_name)
            )
        self._request(
            "PATCH",
            (f"/repos/{self.repository}/git/refs/heads/{transaction.branch}"),
            json={"sha": current_base, "force": True},
        )
        rendered = yaml.safe_dump(after, sort_keys=False, allow_unicode=True)
        response = self._request(
            "PUT",
            f"/repos/{self.repository}/contents/{transaction.target_file}",
            expected=(200, 201),
            json={
                "message": f"fix(aiops): recompute {incident_id} on current base",
                "content": base64.b64encode(rendered.encode()).decode(),
                "sha": current_blob_sha,
                "branch": transaction.branch,
            },
        ).json()
        transaction.base_sha = current_base
        transaction.before_file_sha = current_blob_sha
        transaction.after_file_sha = str(response["content"]["sha"])
        transaction.head_sha = str(response["commit"]["sha"])
        transaction.before_document = current
        transaction.after_document = after
        transaction.before_hash = structured_hash(component(current, component_name))
        transaction.after_hash = structured_hash(component(after, component_name))
        transaction.checks = {}
        transaction.merge_queued = False
        transaction.state = "open"
        if transaction.pr_number is not None:
            self._request(
                "PATCH",
                f"/repos/{self.repository}/pulls/{transaction.pr_number}",
                json={"body": self._pr_body(transaction)},
            )
        return GitObservation(
            state="rebased",
            checks={},
            head_sha=transaction.head_sha,
            base_sha=current_base,
            reason="base advanced outside managed fields; PR branch recomputed",
        )

    async def cancel(self, transaction: GitTransaction, reason: str) -> None:
        import asyncio

        await asyncio.to_thread(self._cancel_sync, transaction, reason)

    def _cancel_sync(self, transaction: GitTransaction, reason: str) -> None:
        discovered = self._discover(transaction)
        if discovered is None or discovered.pr_number is None:
            return
        self._request(
            "PATCH",
            f"/repos/{self.repository}/pulls/{discovered.pr_number}",
            json={"state": "closed"},
        )


class KubernetesRuntimeObserver:
    """Read-only Deployment observer used after Argo sync."""

    def __init__(self, namespace: str):
        from kubernetes import client as kube_client, config as kube_config

        try:
            kube_config.load_incluster_config()
        except kube_config.ConfigException:
            kube_config.load_kube_config()
        self.api = kube_client.AppsV1Api()
        self.serializer = kube_client.ApiClient()
        self.namespace = namespace

    async def observe_deployment(self, deployment: str) -> dict[str, Any]:
        import asyncio

        return await asyncio.to_thread(self._observe, deployment)

    def _observe(self, deployment: str) -> dict[str, Any]:
        obj = self.api.read_namespaced_deployment_status(deployment, self.namespace)
        desired = obj.spec.replicas or 1
        template = self.serializer.sanitize_for_serialization(obj.spec.template)
        annotations = (template.get("metadata") or {}).get("annotations") or {}
        env: list[dict[str, Any]] = []
        container_found = False
        for container in (template.get("spec") or {}).get("containers") or []:
            if container.get("name") == deployment:
                container_found = True
                env = list(container.get("env") or [])
                break
        return {
            "observed_at": utcnow().isoformat(),
            "deployment": deployment,
            "generation": obj.metadata.generation,
            "observed_generation": obj.status.observed_generation,
            "ready": (
                (obj.status.replicas or 0) == desired
                and (obj.status.ready_replicas or 0) == desired
                and (obj.status.updated_replicas or 0) == desired
                and (obj.status.available_replicas or 0) == desired
                and obj.status.observed_generation == obj.metadata.generation
            ),
            "container_found": container_found,
            "remediation_id": annotations.get(CORRELATION_ANNOTATION),
            "managed_env_present": sorted(
                item.get("name")
                for item in env
                if item.get("name", "").startswith("MANDATE22_REVIEW_DELAY_")
            ),
            "template_hash": structured_hash(template),
        }


class KubernetesLeaseTargetLock:
    """The only Kubernetes write path: a target-scoped coordination Lease."""

    def __init__(self, namespace: str):
        from kubernetes import client as kube_client, config as kube_config

        try:
            kube_config.load_incluster_config()
        except kube_config.ConfigException:
            kube_config.load_kube_config()
        self.client = kube_client
        self.api = kube_client.CoordinationV1Api()
        self.namespace = namespace

    @staticmethod
    def _name(target: str) -> str:
        safe = re.sub(r"[^a-z0-9-]", "-", target.lower()).strip("-")
        return f"aiops-gitops-{safe}"[:63].rstrip("-")

    async def acquire(self, target: str, incident_id: str, ttl: int) -> bool:
        import asyncio

        return await asyncio.to_thread(self._acquire, target, incident_id, ttl)

    def _acquire(self, target: str, incident_id: str, ttl: int) -> bool:
        from kubernetes.client.exceptions import ApiException

        name = self._name(target)
        now = utcnow()
        try:
            lease = self.api.read_namespaced_lease(name, self.namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise
            body = self.client.V1Lease(
                metadata=self.client.V1ObjectMeta(
                    name=name,
                    annotations={"aiops.techx.io/incident-id": incident_id},
                ),
                spec=self.client.V1LeaseSpec(
                    holder_identity=incident_id,
                    acquire_time=now,
                    renew_time=now,
                    lease_duration_seconds=ttl,
                ),
            )
            try:
                self.api.create_namespaced_lease(self.namespace, body)
                return True
            except ApiException as create_exc:
                if create_exc.status == 409:
                    return False
                raise
        renewed = lease.spec.renew_time or lease.spec.acquire_time
        active = (
            lease.spec.holder_identity
            and renewed
            and (now - renewed).total_seconds() < ttl
        )
        if active and lease.spec.holder_identity != incident_id:
            return False
        lease.spec.holder_identity = incident_id
        lease.spec.renew_time = now
        lease.spec.lease_duration_seconds = ttl
        self.api.replace_namespaced_lease(name, self.namespace, lease)
        return True

    async def renew(self, target: str, incident_id: str, ttl: int) -> bool:
        return await self.acquire(target, incident_id, ttl)

    async def release(self, target: str, incident_id: str) -> None:
        import asyncio

        await asyncio.to_thread(self._release, target, incident_id)

    def _release(self, target: str, incident_id: str) -> None:
        lease = self.api.read_namespaced_lease(self._name(target), self.namespace)
        if lease.spec.holder_identity != incident_id:
            return
        lease.spec.holder_identity = None
        lease.spec.renew_time = utcnow()
        self.api.replace_namespaced_lease(self._name(target), self.namespace, lease)
