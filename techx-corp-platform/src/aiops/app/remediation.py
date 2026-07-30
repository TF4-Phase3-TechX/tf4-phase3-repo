"""Policy-gated GitOps-native remediation controller for Mandate 22."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any, Awaitable, Callable

from .config import Settings
from .gitops import (
    ChecksFailedError,
    GitOpsError,
    GitOpsRemediationAdapter,
    PullRequestClosedError,
    RuntimeObserver,
    StaleBaseError,
    TargetLock,
    component,
)
from .models import AuditEvent, Evidence, Incident, IncidentStatus, utcnow
from .runbooks import RunbookCatalog
from .saga import (
    GitTransaction,
    RemediationSaga,
    SagaOutcome,
    SagaPersistenceError,
    SagaPhase,
    SagaStore,
    build_saga_store,
    decide_restart_action,
)

log = logging.getLogger("aiops.remediation")

TARGET = "product-reviews"
INCIDENT_TYPE = "service_latency_spike"
RUNBOOK = "product-reviews-config-rollback"
ACTION = "gitops_restore_managed_env"
MANAGED_ENV = frozenset(
    {
        "MANDATE22_REVIEW_DELAY_MS",
        "MANDATE22_REVIEW_DELAY_TTL_SECONDS",
        "MANDATE22_REVIEW_DELAY_MAX_REQUESTS",
    }
)
FAILED_CHECK_STATES = frozenset(
    {"failure", "cancelled", "timed_out", "action_required", "stale"}
)


class PolicyDenied(RuntimeError):
    pass


def usable_prometheus_evidence(evidence: list[Any]) -> bool:
    return any(
        getattr(item, "source", None) == "prometheus"
        and getattr(item, "value", None) not in {None, "unavailable", ""}
        for item in evidence
    )


class RemediationController:
    """Drive one idempotent PR -> checks -> merge -> Argo -> verify saga."""

    def __init__(
        self,
        settings: Settings,
        adapter: GitOpsRemediationAdapter | None = None,
        runtime_observer: RuntimeObserver | None = None,
        target_lock: TargetLock | None = None,
        verifier: Callable[[str], Awaitable[dict[str, Any]]] | None = None,
        catalog: RunbookCatalog | None = None,
        saga_store: SagaStore | None = None,
    ):
        self.settings = settings
        self.adapter = adapter
        self.runtime_observer = runtime_observer
        self.target_lock = target_lock
        self.verifier = verifier
        self.catalog = catalog or RunbookCatalog()
        self.saga_store: SagaStore = saga_store or build_saga_store(
            settings.saga_backend, settings.saga_path or None
        )
        self._locks: set[str] = set()

    async def _checkpoint(self, saga: RemediationSaga) -> None:
        try:
            await self.saga_store.save(saga)
        except SagaPersistenceError:
            raise
        except Exception as exc:
            raise SagaPersistenceError(str(exc)) from exc

    def request_approval(self, incident: Incident) -> None:
        incident.status = IncidentStatus.AWAITING_APPROVAL
        incident.approval_status = "pending"
        incident.approval_expires_at = utcnow() + timedelta(
            seconds=self.settings.approval_ttl_seconds
        )
        incident.audit_events.append(
            AuditEvent(
                event="approval_requested",
                detail={"action": incident.recommended_action},
            )
        )

    def approve(self, incident: Incident) -> None:
        if incident.status != IncidentStatus.AWAITING_APPROVAL:
            raise PolicyDenied("Incident is not awaiting approval")
        if not incident.approval_expires_at or utcnow() > incident.approval_expires_at:
            raise PolicyDenied("Approval request expired")
        incident.approval_status = "approved"
        incident.status = IncidentStatus.APPROVED
        incident.audit_events.append(AuditEvent(event="action_approved_enqueued"))

    def reject(self, incident: Incident) -> None:
        incident.approval_status = "rejected"
        incident.status = IncidentStatus.REJECTED
        incident.audit_events.append(AuditEvent(event="action_rejected"))

    def authorize_by_policy(self, incident: Incident) -> None:
        checks = {
            "autonomous_enabled": self.settings.autonomous_remediation_enabled,
            "exact_incident_type": incident.incident_type == INCIDENT_TYPE,
            "exact_target": incident.affected_service == TARGET,
            "exact_runbook": incident.runbook_id == RUNBOOK,
            "runbook_authorized": RUNBOOK in self.settings.autonomous_runbooks,
            "target_allowlisted": tuple(self.settings.allowed_deployments) == (TARGET,),
            "severity_high": incident.severity == "high",
            "confidence_sufficient": (
                incident.confidence >= self.settings.remediation_confidence_threshold
            ),
            "evidence_present": usable_prometheus_evidence(incident.evidence),
            "mutation_not_blocked": not incident.mutation_blocked,
        }
        incident.audit_events.append(
            AuditEvent(
                event="autonomous_gitops_policy_evaluated",
                detail={
                    "policy_version": self.settings.remediation_policy_version,
                    "checks": checks,
                },
            )
        )
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            raise PolicyDenied("Autonomous policy denied: " + ", ".join(failed))
        try:
            action = self.catalog.action_for(incident.runbook_id)
        except ValueError as exc:
            raise PolicyDenied(str(exc)) from exc
        if action != ACTION:
            raise PolicyDenied("Runbook has no pre-authorized GitOps action")
        incident.policy_version = self.settings.remediation_policy_version
        incident.approval_status = "preauthorized_policy"
        incident.status = IncidentStatus.APPROVED
        incident.audit_events.append(
            AuditEvent(
                event="gitops_action_preauthorized",
                detail={"policy_version": incident.policy_version, "action": action},
            )
        )

    async def handle_incident(self, incident: Incident) -> None:
        if not self.settings.autonomous_remediation_enabled:
            self.request_approval(incident)
            return
        try:
            self.authorize_by_policy(incident)
            await self.execute(incident)
        except PolicyDenied as exc:
            incident.status = IncidentStatus.ESCALATED
            incident.escalation_reason = str(exc)
            incident.audit_events.append(
                AuditEvent(
                    event="autonomous_policy_denied_escalation",
                    detail={"reason": str(exc)},
                )
            )

    def _preflight(self, incident: Incident) -> None:
        if incident.incident_type != INCIDENT_TYPE:
            raise PolicyDenied("Only service_latency_spike is supported")
        if incident.affected_service != TARGET:
            raise PolicyDenied("Only product-reviews is supported")
        if incident.runbook_id != RUNBOOK:
            raise PolicyDenied("Only product-reviews-config-rollback is supported")
        if incident.approval_status not in {"approved", "preauthorized_policy"}:
            raise PolicyDenied("Approval or the signed autonomous policy is required")
        if incident.execution_attempts > 0:
            raise PolicyDenied("Only one transaction is allowed per incident")
        if incident.mutation_blocked:
            raise PolicyDenied("Further mutation is blocked for this incident")

    async def execute(self, incident: Incident) -> None:
        self._preflight(incident)
        target = incident.affected_service
        if target in self._locks:
            raise PolicyDenied("Another transaction is running for this target")
        open_for_target = await self.saga_store.list_open_for_target(target)
        if open_for_target:
            raise PolicyDenied(
                "Open remediation saga already exists for product-reviews"
            )

        incident.execution_attempts += 1
        saga = RemediationSaga(
            incident_id=incident.incident_id,
            incident_type=incident.incident_type,
            target=target,
            policy_version=self.settings.remediation_policy_version,
        )
        self._locks.add(target)
        try:
            saga.note("gitops_preflight_started", mode=self.settings.remediation_mode)
            await self._checkpoint(saga)
            if self.settings.remediation_mode != "gitops/live":
                incident.status = IncidentStatus.ESCALATED
                incident.escalation_reason = (
                    "GitOps dry-run eligible; no branch or PR was written"
                )
                incident.verification_result = {
                    "mode": "dry-run",
                    "eligible": True,
                    "target": TARGET,
                    "policy_version": saga.policy_version,
                    "saga_id": saga.saga_id,
                }
                saga.terminate(
                    SagaOutcome.ABANDONED_PRE_MERGE,
                    "dry-run completed without a Git write",
                )
                await self._checkpoint(saga)
                return
            if self.adapter is None or self.runtime_observer is None:
                raise PolicyDenied(
                    "GitOps and runtime adapters are required in live mode"
                )
            if self.target_lock is None:
                raise PolicyDenied("A durable target Lease is required in live mode")
            if any(
                item.schema_version == 1 and item.is_open
                for item in await self.saga_store.list_all()
            ):
                raise PolicyDenied(
                    "Live activation refused while a non-terminal saga V1 exists"
                )

            acquired = await self.target_lock.acquire(
                target,
                incident.incident_id,
                self.settings.remediation_lock_ttl_seconds,
            )
            if not acquired:
                raise PolicyDenied("The product-reviews target Lease is already held")
            saga.lock_held = True
            saga.note("target_lease_acquired")
            await self._checkpoint(saga)

            transaction = await self.adapter.prepare(incident)
            saga.remediation = transaction
            saga.base_sha = transaction.base_sha
            saga.known_good_sha = transaction.known_good_sha
            saga.policy_sha = transaction.policy_sha
            after_target = (
                component(transaction.after_document, TARGET)
                if transaction.after_document
                else {}
            )
            expected_managed_env = sorted(
                item.get("name")
                for item in after_target.get("envOverrides") or []
                if isinstance(item, dict) and item.get("name") in MANAGED_ENV
            )
            saga.expected_runtime_identity = {
                "remediation_id": incident.incident_id,
                "managed_env_present": expected_managed_env,
                "target_hash": transaction.after_hash,
            }
            saga.advance(SagaPhase.PR_OPEN)
            await self._checkpoint(saga)

            incident.status = IncidentStatus.EXECUTING
            await self._merge_transaction(saga, transaction)
            saga.expected_runtime_identity["merge_sha"] = transaction.merge_sha
            incident.audit_events.append(
                AuditEvent(
                    event="gitops_remediation_merged",
                    detail={
                        "pr_url": transaction.pr_url,
                        "merge_sha": transaction.merge_sha,
                    },
                )
            )
            saga.advance(SagaPhase.RUNTIME_PENDING)
            await self._checkpoint(saga)
            runtime = await self._wait_runtime(
                saga, compensation=False, expected=saga.expected_runtime_identity
            )
            saga.runtime_observation = runtime
            saga.advance(SagaPhase.VERIFYING)
            await self._checkpoint(saga)

            verification = await self._verification_window(target)
            saga.verification_samples = list(verification["samples"])
            incident.verification_result = verification
            await self._checkpoint(saga)
            if verification["healthy"]:
                incident.status = IncidentStatus.RESOLVED
                incident.audit_events.append(
                    AuditEvent(
                        event="gitops_remediation_verified",
                        detail={
                            "pr_url": transaction.pr_url,
                            "merge_sha": transaction.merge_sha,
                        },
                    )
                )
                saga.terminate(SagaOutcome.RESOLVED, "three-poll verification healthy")
                await self._checkpoint(saga)
                return

            await self._compensate(
                saga,
                incident,
                "post-remediation verification was unhealthy or under-volume",
            )
        except PolicyDenied:
            if saga.phase != SagaPhase.TERMINAL:
                saga.terminate(
                    SagaOutcome.ABANDONED_PRE_MERGE,
                    "pre-merge policy denied",
                )
                await self._checkpoint(saga)
            raise
        except SagaPersistenceError as exc:
            incident.status = IncidentStatus.ESCALATED
            incident.mutation_blocked = True
            incident.escalation_reason = f"Saga persistence failed: {exc}"
            saga.mutation_blocked = True
            try:
                saga.terminate(SagaOutcome.PERSISTENCE_FAILED, str(exc))
                await self.saga_store.save(saga)
            except Exception:
                pass
        except Exception as exc:
            await self._handle_failure(saga, incident, exc)
        finally:
            await self._release(saga)
            self._locks.discard(target)

    async def _merge_transaction(
        self, saga: RemediationSaga, transaction: GitTransaction
    ) -> None:
        if self.adapter is None:
            raise GitOpsError("GitOps adapter unavailable")
        if transaction.pr_number is None:
            updated = await self.adapter.submit(transaction)
            self._copy_transaction(transaction, updated)
            phase = (
                SagaPhase.AWAITING_HUMAN_MERGE
                if self.settings.gitops_merge_strategy == "human"
                else SagaPhase.CHECKS_PENDING
            )
            saga.advance(phase)
            await self._checkpoint(saga)

        deadline = time.monotonic() + self.settings.gitops_merge_timeout_seconds
        required = set(self.settings.gitops_required_checks)
        while time.monotonic() <= deadline:
            observation = await self.adapter.observe(transaction)
            transaction.checks = dict(observation.checks)
            transaction.head_sha = observation.head_sha or transaction.head_sha
            transaction.merge_sha = observation.merge_sha or transaction.merge_sha
            await self._checkpoint(saga)
            if observation.state == "stale_managed":
                await self.adapter.cancel(
                    transaction,
                    observation.reason
                    or "managed fields or protected policy changed on base",
                )
                raise StaleBaseError(
                    observation.reason
                    or "managed fields or protected policy changed on base"
                )
            if observation.state == "closed_unmerged":
                raise PullRequestClosedError(
                    observation.reason or "pull request closed without merge"
                )
            failed = {
                name: state
                for name, state in observation.checks.items()
                if name in required and state in FAILED_CHECK_STATES
            }
            if failed:
                await self.adapter.cancel(
                    transaction, f"required checks failed: {failed}"
                )
                raise ChecksFailedError(f"required checks failed: {failed}")
            if observation.state == "merged" and observation.merge_sha:
                transaction.state = "merged"
                transaction.merge_sha = observation.merge_sha
                saga.advance(SagaPhase.MERGED, merge_sha=observation.merge_sha)
                await self._checkpoint(saga)
                return
            if self.settings.gitops_merge_strategy == "human":
                saga.note(
                    "awaiting_human_gitops_merge",
                    pr_url=transaction.pr_url,
                )
                await self._checkpoint(saga)
                if saga.lock_held and self.target_lock is not None:
                    renewed = await self.target_lock.renew(
                        saga.target,
                        saga.incident_id,
                        self.settings.remediation_lock_ttl_seconds,
                    )
                    if not renewed:
                        raise GitOpsError(
                            "target Lease was lost while awaiting human merge"
                        )
                await self._sleep(self.settings.gitops_observe_interval_seconds)
                continue
            successful = {
                name
                for name, state in observation.checks.items()
                if state in {"success", "neutral", "skipped"}
            }
            if required <= successful and not transaction.merge_queued:
                updated = await self.adapter.submit(transaction, queue_merge=True)
                self._copy_transaction(transaction, updated)
                saga.advance(SagaPhase.MERGE_QUEUED)
                await self._checkpoint(saga)
            if saga.lock_held and self.target_lock is not None:
                renewed = await self.target_lock.renew(
                    saga.target,
                    saga.incident_id,
                    self.settings.remediation_lock_ttl_seconds,
                )
                if not renewed:
                    raise GitOpsError("target Lease was lost while awaiting merge")
            await self._sleep(self.settings.gitops_observe_interval_seconds)
        raise GitOpsError("GitHub checks/merge timed out")

    async def _wait_runtime(
        self,
        saga: RemediationSaga,
        *,
        compensation: bool,
        expected: dict[str, Any],
    ) -> dict[str, Any]:
        if self.runtime_observer is None:
            raise GitOpsError("runtime observer unavailable")
        deadline = time.monotonic() + self.settings.gitops_runtime_timeout_seconds
        last: dict[str, Any] = {}
        samples: list[dict[str, Any]] = []
        while time.monotonic() <= deadline:
            last = await self.runtime_observer.observe_deployment(saga.target)
            samples.append(last)
            saga.runtime_observation = last
            if compensation:
                saga.compensation_verification_samples = list(samples)
            await self._checkpoint(saga)
            if self._runtime_matches(last, expected):
                return last
            if saga.lock_held and self.target_lock is not None:
                renewed = await self.target_lock.renew(
                    saga.target,
                    saga.incident_id,
                    self.settings.remediation_lock_ttl_seconds,
                )
                if not renewed:
                    raise GitOpsError("target Lease was lost during Argo convergence")
            await self._sleep(self.settings.gitops_observe_interval_seconds)
        label = "compensation" if compensation else "remediation"
        raise GitOpsError(f"Argo {label} runtime convergence timed out: {last}")

    @staticmethod
    def _runtime_matches(observed: dict[str, Any], expected: dict[str, Any]) -> bool:
        if not observed.get("ready") or not observed.get("container_found", True):
            return False
        if observed.get("remediation_id") != expected.get("remediation_id"):
            return False
        actual_env = sorted(observed.get("managed_env_present") or [])
        expected_env = sorted(expected.get("managed_env_present") or [])
        return actual_env == expected_env

    async def _verification_window(self, target: str) -> dict[str, Any]:
        samples: list[dict[str, Any]] = []
        required = max(self.settings.verification_polls, 1)
        if self.settings.verification_settle_seconds:
            await asyncio.sleep(self.settings.verification_settle_seconds)
        for index in range(required):
            runtime = (
                await self.runtime_observer.observe_deployment(target)
                if self.runtime_observer
                else {"ready": False}
            )
            slo = (
                await self.verifier(target)
                if runtime.get("ready") and self.verifier
                else {
                    "healthy": False,
                    "reason": "runtime_not_ready_or_verifier_missing",
                }
            )
            sample = {
                "poll": index + 1,
                "sampled_at": utcnow().isoformat(),
                "runtime": runtime,
                "slo": slo,
            }
            samples.append(sample)
            if index + 1 < required:
                await self._sleep(self.settings.verification_interval_seconds)
        consecutive = min(
            max(self.settings.verification_consecutive_healthy_polls, 1), required
        )
        healthy = [
            bool(item["runtime"].get("ready") and item["slo"].get("healthy"))
            for item in samples
        ]
        return {
            "healthy": all(healthy[-consecutive:]),
            "observed_entire_window": len(samples) == required,
            "consecutive_required": consecutive,
            "poll_healthy": healthy,
            "samples": samples,
            "target": target,
        }

    async def _compensate(
        self, saga: RemediationSaga, incident: Incident, reason: str
    ) -> None:
        if self.adapter is None:
            raise GitOpsError("GitOps adapter unavailable for compensation")
        saga.advance(SagaPhase.COMPENSATING, reason=reason)
        await self._checkpoint(saga)
        transaction = await self.adapter.prepare(incident, compensation_for=saga)
        saga.compensation = transaction
        await self._checkpoint(saga)
        try:
            await self._merge_transaction(saga, transaction)
            original_target = (
                component(saga.remediation.before_document, TARGET)
                if saga.remediation and saga.remediation.before_document
                else {}
            )
            annotations = original_target.get("podAnnotations") or {}
            original_env = {
                item.get("name")
                for item in original_target.get("envOverrides") or []
                if isinstance(item, dict) and item.get("name") in MANAGED_ENV
            }
            expected = {
                "remediation_id": annotations.get("aiops.techx.io/remediation-id"),
                "managed_env_present": sorted(original_env),
                "target_hash": transaction.after_hash,
            }
            await self._wait_runtime(saga, compensation=True, expected=expected)
            # Compensation restores state; it does not resolve the still-active
            # forced-wrong incident. Keep a durable quarantine until operator clear.
            incident.status = IncidentStatus.ESCALATED
            incident.mutation_blocked = True
            incident.escalation_reason = (
                f"{reason}; compensation restored the pre-action Git/runtime "
                "identity; operator investigation required"
            )
            saga.mutation_blocked = True
            saga.terminate(
                SagaOutcome.COMPENSATED_ESCALATED,
                incident.escalation_reason,
            )
            await self._checkpoint(saga)
        except Exception as exc:
            incident.status = IncidentStatus.ESCALATED
            incident.mutation_blocked = True
            incident.escalation_reason = (
                f"Compensation failed: {type(exc).__name__}: {exc}"
            )
            saga.mutation_blocked = True
            saga.terminate(SagaOutcome.COMPENSATION_FAILED, incident.escalation_reason)
            await self._checkpoint(saga)

    async def _handle_failure(
        self, saga: RemediationSaga, incident: Incident, exc: Exception
    ) -> None:
        merged = bool(saga.remediation and saga.remediation.merge_sha)
        if merged and saga.compensation is None and self.adapter is not None:
            try:
                await self._compensate(
                    saga,
                    incident,
                    f"remediation transaction failed: {type(exc).__name__}: {exc}",
                )
                return
            except Exception:
                log.exception("compensation orchestration failed")
        if saga.remediation and not merged and self.adapter is not None:
            try:
                await self.adapter.cancel(saga.remediation, str(exc))
            except Exception:
                log.exception("failed to cancel pre-merge transaction")
        incident.status = IncidentStatus.ESCALATED
        incident.escalation_reason = f"{type(exc).__name__}: {exc}"
        saga.mutation_blocked = merged
        incident.mutation_blocked = merged
        outcome = (
            SagaOutcome.CHECKS_FAILED
            if isinstance(exc, ChecksFailedError)
            else SagaOutcome.ESCALATED
        )
        saga.terminate(outcome, incident.escalation_reason)
        await self._checkpoint(saga)

    async def _release(self, saga: RemediationSaga) -> None:
        if not saga.lock_held or self.target_lock is None:
            return
        try:
            await self.target_lock.release(saga.target, saga.incident_id)
            saga.lock_held = False
            saga.note("target_lease_released")
            await self._checkpoint(saga)
        except Exception:
            log.exception("failed to release GitOps target Lease")

    async def reconcile_open_sagas(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for saga in await self.saga_store.list_open():
            if (
                saga.schema_version == 1
                and self.settings.remediation_mode != "gitops/live"
            ):
                results.append(
                    {
                        "saga_id": saga.saga_id,
                        "incident_id": saga.incident_id,
                        "action": "legacy_v1_retained_dry_run",
                    }
                )
                continue
            results.append(await self.resume_saga(saga))
        return results

    async def resume_saga(self, saga: RemediationSaga) -> dict[str, Any]:
        action = decide_restart_action(saga)
        detail = {
            "saga_id": saga.saga_id,
            "incident_id": saga.incident_id,
            "phase": saga.phase.value,
            "action": action,
        }
        if action == "block_legacy_v1":
            raise RuntimeError(
                "non-terminal saga V1 blocks GitOps live activation; "
                "operator reconciliation is required"
            )
        if action == "noop_terminal":
            await self._release(saga)
            return detail
        if action == "abandon_pre_merge":
            saga.terminate(
                SagaOutcome.ABANDONED_PRE_MERGE,
                "restart before PR submission; abandoned without Git write",
            )
            await self._release(saga)
            await self._checkpoint(saga)
            detail["outcome"] = saga.outcome.value
            return detail
        if self.adapter is None or self.runtime_observer is None:
            raise RuntimeError("open GitOps saga requires GitHub and runtime adapters")
        incident = Incident(
            incident_id=saga.incident_id,
            incident_type=saga.incident_type,
            severity="high",
            affected_service=saga.target,
            confidence=1.0,
            suspected_root_cause="durable saga recovery",
            evidence=[
                Evidence(
                    source="prometheus",
                    query="recovery",
                    window="durable",
                    value=1,
                )
            ],
            runbook_id=RUNBOOK,
            recommended_action=ACTION,
            approval_status="preauthorized_policy",
            policy_version=saga.policy_version,
        )
        try:
            if saga.compensation is not None:
                await self._merge_transaction(saga, saga.compensation)
                original_target = (
                    component(saga.remediation.before_document, TARGET)
                    if saga.remediation and saga.remediation.before_document
                    else {}
                )
                annotations = original_target.get("podAnnotations") or {}
                original_env = {
                    item.get("name")
                    for item in original_target.get("envOverrides") or []
                    if isinstance(item, dict) and item.get("name") in MANAGED_ENV
                }
                await self._wait_runtime(
                    saga,
                    compensation=True,
                    expected={
                        "remediation_id": annotations.get(
                            "aiops.techx.io/remediation-id"
                        ),
                        "managed_env_present": sorted(original_env),
                        "target_hash": saga.compensation.after_hash,
                    },
                )
                saga.mutation_blocked = True
                saga.terminate(
                    SagaOutcome.COMPENSATED_ESCALATED,
                    "compensation merge and runtime identity rediscovered after "
                    "restart; operator investigation required",
                )
            elif saga.remediation:
                await self._merge_transaction(saga, saga.remediation)
                saga.advance(SagaPhase.RUNTIME_PENDING)
                await self._checkpoint(saga)
                await self._wait_runtime(
                    saga,
                    compensation=False,
                    expected=saga.expected_runtime_identity,
                )
                saga.advance(SagaPhase.VERIFYING)
                verification = await self._verification_window(saga.target)
                saga.verification_samples = verification["samples"]
                if verification["healthy"]:
                    saga.terminate(
                        SagaOutcome.RESOLVED,
                        "restart rediscovery and verification healthy",
                    )
                else:
                    await self._compensate(
                        saga, incident, "restart verification unhealthy"
                    )
            await self._checkpoint(saga)
            detail["outcome"] = saga.outcome.value
            return detail
        finally:
            await self._release(saga)

    @staticmethod
    async def _sleep(seconds: float) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)

    @staticmethod
    def _copy_transaction(target: GitTransaction, source: GitTransaction) -> None:
        for name, value in source.model_dump().items():
            setattr(target, name, value)
