from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import Any, Awaitable, Callable

from .config import Settings
from .models import AuditEvent, Incident, IncidentStatus, utcnow
from .runbooks import RunbookCatalog
from .saga import (
    RemediationSaga,
    SagaOutcome,
    SagaPersistenceError,
    SagaPhase,
    SagaStore,
    argo_window_annotations,
    build_saga_store,
    decide_restart_action,
    templates_equivalent,
)

log = logging.getLogger("aiops.remediation")


class PolicyDenied(RuntimeError):
    pass


def usable_prometheus_evidence(evidence: list[Any]) -> bool:
    """Autonomous action requires at least one concrete Prometheus observation."""

    for item in evidence:
        source = getattr(item, "source", None)
        value = getattr(item, "value", None)
        if source != "prometheus":
            continue
        if value in {None, "unavailable", ""}:
            continue
        return True
    return False


class KubernetesRollbackAdapter:
    """Bounded adapter: Deployment template rollback only, never free-form commands."""

    def __init__(
        self,
        namespace: str,
        deployment_recency_hours: int = 24,
        known_good_revisions: dict[str, str] | None = None,
    ):
        from kubernetes import client as kube_client, config as kube_config

        try:
            kube_config.load_incluster_config()
        except kube_config.ConfigException:
            kube_config.load_kube_config()
        self.kube_client = kube_client
        self.api = kube_client.AppsV1Api()
        self.coordination_api = kube_client.CoordinationV1Api()
        self.namespace = namespace
        self.deployment_recency_hours = deployment_recency_hours
        self.known_good_revisions = known_good_revisions or {}

    def previous_template(
        self, deployment: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        current = self.api.read_namespaced_deployment(deployment, self.namespace)
        replicasets = self.api.list_namespaced_replica_set(
            self.namespace,
            label_selector=",".join(
                f"{key}={value}"
                for key, value in current.spec.selector.match_labels.items()
            ),
        ).items
        owned = [
            rs
            for rs in replicasets
            if any(
                owner.uid == current.metadata.uid
                for owner in (rs.metadata.owner_references or [])
            )
        ]
        owned.sort(
            key=lambda rs: int(
                (rs.metadata.annotations or {}).get(
                    "deployment.kubernetes.io/revision", "0"
                )
            ),
            reverse=True,
        )
        if len(owned) < 2:
            raise PolicyDenied("No previous ReplicaSet revision is retained")
        latest_created = owned[0].metadata.creation_timestamp
        if not latest_created or utcnow() - latest_created > timedelta(
            hours=self.deployment_recency_hours
        ):
            raise PolicyDenied(
                "No sufficiently recent Deployment revision is correlated with the incident"
            )

        pinned = self.known_good_revisions.get(deployment)
        if pinned:
            selected = next(
                (
                    rs
                    for rs in owned[1:]
                    if (rs.metadata.annotations or {}).get(
                        "deployment.kubernetes.io/revision"
                    )
                    == pinned
                ),
                None,
            )
            if selected is None:
                raise PolicyDenied(
                    f"Pinned known-good revision {pinned!r} for {deployment} "
                    "is not retained among previous ReplicaSets"
                )
            previous_rs = selected
        else:
            # Without a CDO pin, owned[1] is only "previous", not proven known-good.
            previous_rs = owned[1]

        serializer = self.kube_client.ApiClient()
        return (
            serializer.sanitize_for_serialization(current.spec.template),
            serializer.sanitize_for_serialization(previous_rs.spec.template),
        )

    def patch_template(self, deployment: str, template: dict[str, Any]) -> None:
        self.api.patch_namespaced_deployment(
            deployment, self.namespace, {"spec": {"template": template}}
        )

    def dry_run_patch_template(
        self, deployment: str, template: dict[str, Any]
    ) -> None:
        self.api.patch_namespaced_deployment(
            deployment,
            self.namespace,
            {"spec": {"template": template}},
            dry_run="All",
        )

    def rollout_ready(self, deployment: str) -> bool:
        obj = self.api.read_namespaced_deployment_status(deployment, self.namespace)
        desired = obj.spec.replicas or 1
        return (obj.status.updated_replicas or 0) >= desired and (
            obj.status.available_replicas or 0
        ) >= desired

    def _lease_name(self, deployment: str) -> str:
        safe = re.sub(r"[^a-z0-9-]", "-", deployment.lower()).strip("-")
        return f"aiops-remediation-{safe}"[:63].rstrip("-")

    def acquire_lock(self, deployment: str, incident_id: str, ttl: int) -> bool:
        """Acquire a Kubernetes Lease so restarts/replicas cannot duplicate action."""

        from kubernetes.client.exceptions import ApiException

        name = self._lease_name(deployment)
        now = utcnow()
        try:
            lease = self.coordination_api.read_namespaced_lease(name, self.namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise
            body = self.kube_client.V1Lease(
                metadata=self.kube_client.V1ObjectMeta(
                    name=name,
                    annotations={"aiops.techx/incident-id": incident_id},
                ),
                spec=self.kube_client.V1LeaseSpec(
                    holder_identity=incident_id,
                    acquire_time=now,
                    renew_time=now,
                    lease_duration_seconds=ttl,
                ),
            )
            try:
                self.coordination_api.create_namespaced_lease(self.namespace, body)
                return True
            except ApiException as create_exc:
                if create_exc.status == 409:
                    return False
                raise

        holder = lease.spec.holder_identity
        renewed = lease.spec.renew_time or lease.spec.acquire_time
        active = holder and renewed and (now - renewed).total_seconds() < ttl
        if active and holder != incident_id:
            return False
        lease.spec.holder_identity = incident_id
        lease.spec.acquire_time = now
        lease.spec.renew_time = now
        lease.spec.lease_duration_seconds = ttl
        lease.metadata.annotations = {
            **(lease.metadata.annotations or {}),
            "aiops.techx/incident-id": incident_id,
        }
        self.coordination_api.replace_namespaced_lease(name, self.namespace, lease)
        return True

    def release_lock(self, deployment: str, incident_id: str) -> None:
        name = self._lease_name(deployment)
        lease = self.coordination_api.read_namespaced_lease(name, self.namespace)
        if lease.spec.holder_identity != incident_id:
            return
        lease.spec.holder_identity = None
        lease.spec.renew_time = utcnow()
        self.coordination_api.replace_namespaced_lease(name, self.namespace, lease)

    def read_template(self, deployment: str) -> dict[str, Any]:
        current = self.api.read_namespaced_deployment(deployment, self.namespace)
        serializer = self.kube_client.ApiClient()
        return serializer.sanitize_for_serialization(current.spec.template)

    def begin_argo_window(self, deployment: str, incident_id: str, ttl: int) -> dict[str, str]:
        """Mark Deployment ownership for the bounded mutation/verification window.

        Application-level ignoreDifferences for /spec/template remain a CDO
        GitOps contract; these annotations let AIOps detect Argo overwrite.
        """

        until = (utcnow() + timedelta(seconds=ttl)).isoformat()
        annotations = argo_window_annotations(incident_id, until)
        self.api.patch_namespaced_deployment(
            deployment,
            self.namespace,
            {"metadata": {"annotations": annotations}},
        )
        return annotations

    def end_argo_window(self, deployment: str, incident_id: str) -> None:
        """Clear AIOps ownership annotations when we still own the window."""

        from .saga import (
            ARGO_COMPARE_OPTIONS_ANNOTATION,
            ARGO_OWNER_ANNOTATION,
            ARGO_WINDOW_ANNOTATION,
            ARGO_WINDOW_UNTIL_ANNOTATION,
        )

        current = self.api.read_namespaced_deployment(deployment, self.namespace)
        annotations = dict(current.metadata.annotations or {})
        owner = annotations.get(ARGO_WINDOW_ANNOTATION)
        if owner not in {None, incident_id}:
            return
        for key in (
            ARGO_WINDOW_ANNOTATION,
            ARGO_WINDOW_UNTIL_ANNOTATION,
            ARGO_OWNER_ANNOTATION,
            ARGO_COMPARE_OPTIONS_ANNOTATION,
        ):
            annotations[key] = None
        self.api.patch_namespaced_deployment(
            deployment,
            self.namespace,
            {"metadata": {"annotations": annotations}},
        )


class RemediationController:
    """Policy-gated detect -> act -> verify -> rollback/escalate controller."""

    def __init__(
        self,
        settings: Settings,
        adapter: KubernetesRollbackAdapter | None = None,
        verifier: Callable[[str], Awaitable[dict[str, Any]]] | None = None,
        catalog: RunbookCatalog | None = None,
        saga_store: SagaStore | None = None,
    ):
        self.settings = settings
        self.adapter = adapter
        self.verifier = verifier
        self.catalog = catalog or RunbookCatalog()
        self.saga_store: SagaStore = saga_store or build_saga_store(
            getattr(settings, "saga_backend", "memory"),
            getattr(settings, "saga_path", "") or None,
        )
        self._locks: set[str] = set()

    async def _retry(
        self,
        function: Callable[..., Any],
        *args: Any,
        allow_retry: bool = True,
    ) -> Any:
        last_error: Exception | None = None
        attempts = 2 if allow_retry else 1
        for attempt in range(attempts):
            try:
                return await asyncio.to_thread(function, *args)
            except PolicyDenied:
                raise
            except Exception as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(1.0)
        raise RuntimeError(
            f"Kubernetes action failed after {attempts} attempt(s): {last_error}"
        ) from last_error

    async def _checkpoint(self, saga: RemediationSaga) -> RemediationSaga:
        try:
            return await self.saga_store.save(saga)
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
        incident.audit_events.append(AuditEvent(event="action_approved"))

    def reject(self, incident: Incident) -> None:
        incident.approval_status = "rejected"
        incident.status = IncidentStatus.REJECTED
        incident.audit_events.append(AuditEvent(event="action_rejected"))

    def authorize_by_policy(self, incident: Incident) -> None:
        """Authorize one exact action using a deployment-time signed policy envelope."""

        checks = {
            "autonomous_enabled": self.settings.autonomous_remediation_enabled,
            "runbook_authorized": incident.runbook_id
            in self.settings.autonomous_runbooks,
            "target_allowlisted": incident.affected_service
            in self.settings.allowed_deployments,
            "severity_high": incident.severity == "high",
            "confidence_sufficient": incident.confidence
            >= self.settings.remediation_confidence_threshold,
            # Presence of empty/unavailable evidence must not authorize mutation.
            "evidence_present": usable_prometheus_evidence(incident.evidence),
            "mutation_not_blocked": not incident.mutation_blocked,
        }
        incident.audit_events.append(
            AuditEvent(
                event="autonomous_policy_evaluated",
                detail={
                    "policy_version": self.settings.remediation_policy_version,
                    "checks": checks,
                },
            )
        )
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise PolicyDenied(
                "Autonomous policy denied: " + ", ".join(sorted(failed))
            )
        try:
            action = self.catalog.action_for(incident.runbook_id)
        except ValueError as exc:
            raise PolicyDenied(str(exc)) from exc
        if action != "rollback_previous_replicaset":
            raise PolicyDenied("Runbook has no pre-authorized bounded action")
        incident.policy_version = self.settings.remediation_policy_version
        incident.approval_status = "preauthorized_policy"
        incident.status = IncidentStatus.APPROVED
        incident.audit_events.append(
            AuditEvent(
                event="action_preauthorized",
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
            # Pre-mutation policy denials must NOT set mutation_blocked.
            # That flag is reserved for post-mutation safety failures so a
            # temporary deny (missing evidence, lease held, low confidence)
            # can still auto-resolve and re-attempt on a later incident cycle.
            incident.status = IncidentStatus.ESCALATED
            incident.escalation_reason = str(exc)
            incident.audit_events.append(
                AuditEvent(
                    event="autonomous_policy_denied_escalation",
                    detail={"reason": str(exc)},
                )
            )

    async def _verification_window(
        self,
        adapter: KubernetesRollbackAdapter,
        target: str,
        polls: int,
    ) -> dict[str, Any]:
        samples: list[dict[str, Any]] = []
        required = max(polls, 1)
        if self.settings.verification_settle_seconds > 0:
            await asyncio.sleep(self.settings.verification_settle_seconds)
        for index in range(required):
            ready = bool(await self._retry(adapter.rollout_ready, target))
            slo = (
                await self.verifier(target)
                if ready and self.verifier
                else {"healthy": False, "reason": "rollout_not_ready_or_verifier_missing"}
            )
            samples.append({"poll": index + 1, "sampled_at": utcnow().isoformat(), "rollout_ready": ready, "slo": slo})
            if index + 1 < required and self.settings.verification_interval_seconds > 0:
                await asyncio.sleep(self.settings.verification_interval_seconds)
        poll_healthy = [
            bool(sample["rollout_ready"] and sample["slo"].get("healthy", False))
            for sample in samples
        ]
        consecutive = min(
            max(self.settings.verification_consecutive_healthy_polls, 1),
            required,
        )
        # Require the trailing consecutive polls only. A single stale first
        # sample after settle (observed in the 2026-07-25 live drill) must not
        # veto an otherwise recovered window.
        trailing = poll_healthy[-consecutive:]
        return {
            "healthy": len(trailing) == consecutive and all(trailing),
            "consecutive_required": consecutive,
            "poll_healthy": poll_healthy,
            "observed_entire_window": len(samples) == required,
            "samples": samples,
            "target": target,
        }

    async def _rollback_and_verify(
        self,
        incident: Incident,
        adapter: KubernetesRollbackAdapter,
        target: str,
        original: dict[str, Any],
        reason: str,
    ) -> bool:
        await self._retry(
            adapter.patch_template, target, original, allow_retry=False
        )
        incident.audit_events.append(
            AuditEvent(event="rollback_applied", detail={"reason": reason})
        )
        verification = await self._verification_window(
            adapter, target, self.settings.rollback_verification_polls
        )
        incident.rollback_verification_result = verification
        if verification["healthy"]:
            incident.rollback_result = {
                "restored_original_template": True,
                "verified": True,
                "reason": reason,
            }
            incident.status = IncidentStatus.ROLLED_BACK
            incident.audit_events.append(AuditEvent(event="rollback_verified"))
            return True
        incident.rollback_result = {
            "restored_original_template": True,
            "verified": False,
            "reason": reason,
        }
        incident.status = IncidentStatus.ESCALATED
        incident.mutation_blocked = True
        incident.escalation_reason = "Rollback applied but recovery could not be verified"
        incident.audit_events.append(
            AuditEvent(event="rollback_unverified_escalation")
        )
        return False

    async def execute(self, incident: Incident) -> None:
        target = incident.affected_service
        try:
            action = self.catalog.action_for(incident.runbook_id)
        except ValueError as exc:
            raise PolicyDenied(str(exc)) from exc
        if action != "rollback_previous_replicaset":
            incident.status = IncidentStatus.ESCALATED
            incident.escalation_reason = "Runbook has no approved automatic action"
            incident.audit_events.append(AuditEvent(event="incident_escalated"))
            return
        if target not in self.settings.allowed_deployments:
            raise PolicyDenied(f"Deployment {target} is outside the allowlist")
        if incident.approval_status not in {"approved", "preauthorized_policy"}:
            raise PolicyDenied("Manual approval or a signed pre-authorized policy is required")
        if incident.confidence < self.settings.remediation_confidence_threshold:
            raise PolicyDenied("RCA confidence is below the remediation threshold")
        if incident.mutation_blocked:
            raise PolicyDenied("Further mutation is blocked for this incident")
        if incident.execution_attempts > 0:
            raise PolicyDenied("Only one mutation attempt is allowed per incident")
        if target in self._locks:
            raise PolicyDenied("Another action is already running for this target")
        open_for_target = await self.saga_store.list_open_for_target(target)
        if open_for_target:
            raise PolicyDenied(
                f"Open remediation saga already exists for {target}; "
                "never start a second mutation while a saga is non-terminal"
            )
        # Live mutation requires an explicit CDO pin. owned[1] alone is not
        # known-good and must not be the only rollback target in live mode.
        if (
            self.settings.remediation_mode == "live"
            and target not in self.settings.known_good_revisions
        ):
            raise PolicyDenied(
                f"Live mutation requires AIOPS_KNOWN_GOOD_REVISIONS pin for {target}"
            )

        self._locks.add(target)
        adapter: KubernetesRollbackAdapter | None = None
        original: dict[str, Any] | None = None
        previous: dict[str, Any] | None = None
        mutation_attempted = False
        mutated = False
        external_lock = False
        argo_window = False
        saga = RemediationSaga(incident_id=incident.incident_id, target=target)
        try:
            saga.advance(SagaPhase.PREFLIGHT)
            await self._checkpoint(saga)

            incident.execution_attempts += 1
            incident.status = IncidentStatus.EXECUTING
            incident.audit_events.append(
                AuditEvent(
                    event="action_preflight_started",
                    detail={
                        "target": target,
                        "mode": self.settings.remediation_mode,
                        "saga_id": saga.saga_id,
                    },
                )
            )
            if self.settings.remediation_mode != "live":
                incident.verification_result = {
                    "mode": "dry-run",
                    "eligible": True,
                    "target": target,
                    "policy_version": incident.policy_version,
                    "saga_id": saga.saga_id,
                }
                incident.status = IncidentStatus.ESCALATED
                incident.escalation_reason = "Dry-run completed; no mutation performed"
                incident.audit_events.append(AuditEvent(event="dry_run_completed"))
                saga.terminate(
                    SagaOutcome.ABANDONED_PRE_MUTATION,
                    "dry-run completed; no mutation performed",
                )
                await self._checkpoint(saga)
                return

            adapter = self.adapter or KubernetesRollbackAdapter(
                self.settings.namespace,
                self.settings.deployment_recency_hours,
                known_good_revisions=self.settings.known_good_revisions,
            )
            acquire_lock = getattr(adapter, "acquire_lock", None)
            if acquire_lock:
                external_lock = bool(
                    await self._retry(
                        acquire_lock,
                        target,
                        incident.incident_id,
                        self.settings.remediation_lock_ttl_seconds,
                    )
                )
                if not external_lock:
                    raise PolicyDenied("A Kubernetes target Lease is already held")
                saga.lease_held = True
                saga.advance(SagaPhase.LEASE_ACQUIRED)
                await self._checkpoint(saga)
                incident.audit_events.append(AuditEvent(event="target_lease_acquired"))
            original, previous = await self._retry(adapter.previous_template, target)
            saga.original_template = original
            saga.selected_template = previous
            known_good = getattr(self.settings, "known_good_revisions", None) or {}
            if isinstance(known_good, dict):
                saga.known_good_revision = known_good.get(target)
            incident.before_snapshot = (
                await self.verifier(target)
                if self.verifier
                else {"healthy": False, "reason": "verifier_missing"}
            )
            incident.audit_events.append(
                AuditEvent(
                    event="action_preflight_passed",
                    detail={
                        "target": target,
                        "saga_id": saga.saga_id,
                        "known_good_revision": self.settings.known_good_revisions.get(
                            target
                        ),
                    },
                )
            )
            dry_run = getattr(adapter, "dry_run_patch_template", None)
            if dry_run:
                await self._retry(dry_run, target, previous)
                incident.audit_events.append(
                    AuditEvent(event="kubernetes_server_dry_run_passed")
                )

            if getattr(self.settings, "argo_window_enabled", True):
                begin = getattr(adapter, "begin_argo_window", None)
                if begin:
                    await self._retry(
                        begin,
                        target,
                        incident.incident_id,
                        self.settings.remediation_lock_ttl_seconds,
                    )
                    argo_window = True
                    saga.argo_window_active = True
                    saga.advance(SagaPhase.ARGO_WINDOW_OPEN)
                    await self._checkpoint(saga)
                    incident.audit_events.append(
                        AuditEvent(event="argo_mutation_window_opened")
                    )

            # Evidence freshness trade-off: authorize_by_policy checked
            # Prometheus evidence earlier in this call; we do not re-query here
            # because the bounded single-service action scope limits the window
            # to seconds, and a re-query failure should not leave us half-way
            # through mutation.  Documented as accepted in ADR-022 trade-offs.
            #
            # Persist intent before the live patch so a crash after this point
            # is treated as post-mutation risk even if the ack is lost.
            # Do not retry live mutation: a client timeout after server success
            # would otherwise re-patch a concurrent GitOps change.
            mutation_attempted = True
            saga.mutation_attempted = True
            saga.expected_template_after_action = previous
            saga.advance(SagaPhase.ACTION_ACKNOWLEDGED, pending_patch=True)
            await self._checkpoint(saga)

            await self._retry(
                adapter.patch_template, target, previous, allow_retry=False
            )
            mutated = True
            incident.audit_events.append(
                AuditEvent(
                    event="action_executed",
                    detail={"saga_id": saga.saga_id},
                )
            )
            incident.status = IncidentStatus.VERIFYING
            saga.advance(SagaPhase.VERIFYING)
            await self._checkpoint(saga)

            # Detect Argo/GitOps overwrite of the intended post-action template.
            read_template = getattr(adapter, "read_template", None)
            if read_template and previous is not None:
                current = await self._retry(read_template, target)
                if not templates_equivalent(current, previous):
                    incident.status = IncidentStatus.ESCALATED
                    incident.mutation_blocked = True
                    incident.escalation_reason = (
                        "Argo/GitOps or external actor overwrote the remediation "
                        "mutation during the ownership window"
                    )
                    incident.audit_events.append(
                        AuditEvent(event="argo_overwrite_detected")
                    )
                    saga.mutation_blocked = True
                    saga.terminate(
                        SagaOutcome.ARGO_OVERWRITE,
                        incident.escalation_reason,
                    )
                    await self._checkpoint(saga)
                    return

            verification = await self._verification_window(
                adapter, target, self.settings.verification_polls
            )
            incident.verification_result = verification
            saga.verification_samples = list(verification.get("samples") or [])
            await self._checkpoint(saga)
            if verification["healthy"]:
                incident.status = IncidentStatus.RESOLVED
                incident.audit_events.append(AuditEvent(event="remediation_verified"))
                saga.terminate(SagaOutcome.RESOLVED, "remediation verified")
                await self._checkpoint(saga)
                return
            incident.escalation_reason = (
                "Remediation did not recover during the stabilization window"
            )
            saga.advance(SagaPhase.ROLLING_BACK, reason=incident.escalation_reason)
            saga.rollback_phase = "started"
            await self._checkpoint(saga)
            ok = await self._rollback_and_verify(
                incident, adapter, target, original, incident.escalation_reason
            )
            saga.rollback_verification_samples = list(
                (incident.rollback_verification_result or {}).get("samples") or []
            )
            if ok:
                saga.terminate(SagaOutcome.ROLLED_BACK, incident.escalation_reason)
            else:
                saga.mutation_blocked = True
                saga.terminate(SagaOutcome.ESCALATED, incident.escalation_reason)
            await self._checkpoint(saga)
        except PolicyDenied as exc:
            if not mutated:
                # Pre-mutation denials (lease held, missing previous RS, pin
                # missing after race) escalate without permanent mutation block
                # so operators are not forced to unlock a never-mutated target.
                incident.status = IncidentStatus.ESCALATED
                incident.escalation_reason = str(exc)
                incident.audit_events.append(
                    AuditEvent(
                        event="pre_mutation_policy_denied_escalation",
                        detail={"reason": str(exc)},
                    )
                )
                if saga.phase != SagaPhase.TERMINAL:
                    saga.terminate(SagaOutcome.ABANDONED_PRE_MUTATION, str(exc))
                    try:
                        await self._checkpoint(saga)
                    except SagaPersistenceError:
                        pass
            raise
        except SagaPersistenceError as exc:
            incident.status = IncidentStatus.ESCALATED
            incident.mutation_blocked = True
            incident.escalation_reason = f"Saga persistence failed: {exc}"
            incident.audit_events.append(
                AuditEvent(
                    event="saga_persistence_failed",
                    detail={"error": str(exc)},
                )
            )
            # Best-effort terminal marker when store may be partially available.
            try:
                saga.mutation_blocked = True
                saga.terminate(SagaOutcome.PERSISTENCE_FAILED, str(exc))
                await self.saga_store.save(saga)
            except Exception:
                pass
        except Exception as exc:
            incident.escalation_reason = f"Remediation failed: {type(exc).__name__}: {exc}"
            if mutated and adapter and original:
                try:
                    saga.advance(SagaPhase.ROLLING_BACK, reason=str(exc))
                    await self._checkpoint(saga)
                    ok = await self._rollback_and_verify(
                        incident, adapter, target, original, incident.escalation_reason
                    )
                    if ok:
                        saga.terminate(SagaOutcome.ROLLED_BACK, incident.escalation_reason)
                    else:
                        saga.mutation_blocked = True
                        saga.terminate(SagaOutcome.ESCALATED, incident.escalation_reason)
                    await self._checkpoint(saga)
                except Exception as rollback_exc:
                    incident.status = IncidentStatus.ESCALATED
                    incident.mutation_blocked = True
                    incident.rollback_result = {
                        "restored_original_template": False,
                        "verified": False,
                        "error": str(rollback_exc),
                    }
                    incident.audit_events.append(
                        AuditEvent(event="rollback_failed_escalation")
                    )
                    saga.mutation_blocked = True
                    saga.terminate(SagaOutcome.ESCALATED, str(rollback_exc))
                    try:
                        await self._checkpoint(saga)
                    except SagaPersistenceError:
                        pass
            elif mutation_attempted or saga.mutation_attempted:
                # A transport error is ambiguous: the API server may have
                # committed the patch even though the response was lost.
                # Never retry or classify it as a pre-mutation failure.
                incident.status = IncidentStatus.ESCALATED
                incident.mutation_blocked = True
                incident.escalation_reason = (
                    "Live mutation outcome is unknown after client/API failure: "
                    f"{type(exc).__name__}: {exc}"
                )
                incident.audit_events.append(
                    AuditEvent(
                        event="action_outcome_unknown",
                        detail={
                            "target": target,
                            "error": f"{type(exc).__name__}: {exc}",
                            "operator_reconciliation_required": True,
                        },
                    )
                )
                saga.mutation_blocked = True
                saga.terminate(SagaOutcome.MUTATION_UNKNOWN, str(exc))
                try:
                    await self._checkpoint(saga)
                except SagaPersistenceError:
                    pass
            else:
                # Failure before any live patch is not a post-mutation safety
                # lock; keep the incident escalated but re-attemptable.
                incident.status = IncidentStatus.ESCALATED
                incident.audit_events.append(
                    AuditEvent(event="execution_failed_before_mutation")
                )
                saga.terminate(SagaOutcome.ABANDONED_PRE_MUTATION, str(exc))
                try:
                    await self._checkpoint(saga)
                except SagaPersistenceError:
                    pass
        finally:
            if argo_window and adapter:
                end = getattr(adapter, "end_argo_window", None)
                if end:
                    try:
                        await self._retry(end, target, incident.incident_id)
                        saga.argo_window_active = False
                        saga.note("argo_mutation_window_closed")
                        await self._checkpoint(saga)
                        incident.audit_events.append(
                            AuditEvent(event="argo_mutation_window_closed")
                        )
                    except Exception as exc:
                        incident.audit_events.append(
                            AuditEvent(
                                event="argo_mutation_window_close_failed",
                                detail={"error": str(exc)},
                            )
                        )
            if external_lock and adapter:
                release_lock = getattr(adapter, "release_lock", None)
                if release_lock:
                    try:
                        await self._retry(release_lock, target, incident.incident_id)
                        saga.lease_held = False
                        saga.note("target_lease_released")
                        await self._checkpoint(saga)
                        incident.audit_events.append(AuditEvent(event="target_lease_released"))
                    except Exception as exc:
                        incident.audit_events.append(
                            AuditEvent(
                                event="target_lease_release_failed",
                                detail={"error": str(exc)},
                            )
                        )
            self._locks.discard(target)

    async def reconcile_open_sagas(self) -> list[dict[str, Any]]:
        """Startup recovery: deterministically finish or fail closed open sagas."""

        results: list[dict[str, Any]] = []
        for saga in await self.saga_store.list_open():
            result = await self.resume_saga(saga)
            results.append(result)
        return results

    async def resume_saga(self, saga: RemediationSaga) -> dict[str, Any]:
        """Continue a durable saga after process restart (never re-mutate)."""

        action = decide_restart_action(saga)
        detail: dict[str, Any] = {
            "saga_id": saga.saga_id,
            "incident_id": saga.incident_id,
            "target": saga.target,
            "phase": saga.phase.value,
            "action": action,
        }
        adapter = self.adapter
        if action == "noop_terminal":
            if (saga.argo_window_active or saga.lease_held) and adapter is None:
                raise SagaPersistenceError(
                    "terminal saga retains external ownership but no adapter is available"
                )
            if saga.argo_window_active:
                end = getattr(adapter, "end_argo_window", None)
                if not end:
                    raise SagaPersistenceError(
                        "terminal saga retains Argo window but adapter cannot close it"
                    )
                await self._retry(end, saga.target, saga.incident_id)
                saga.argo_window_active = False
                saga.note("startup_argo_window_closed")
            if saga.lease_held:
                release_lock = getattr(adapter, "release_lock", None)
                if not release_lock:
                    raise SagaPersistenceError(
                        "terminal saga retains Lease but adapter cannot release it"
                    )
                await self._retry(release_lock, saga.target, saga.incident_id)
                saga.lease_held = False
                saga.note("startup_target_lease_released")
            await self._checkpoint(saga)
            detail["cleanup"] = "complete"
            return detail
        if action == "abandon_pre_mutation":
            saga.terminate(
                SagaOutcome.ABANDONED_PRE_MUTATION,
                "restart before live mutation; abandoned without re-mutating",
            )
            await self._checkpoint(saga)
            detail["outcome"] = saga.outcome.value
            return detail
        if action == "fail_closed_escalate":
            saga.mutation_blocked = True
            saga.terminate(
                SagaOutcome.ESCALATED,
                "restart reconcile fail-closed: incomplete durable state",
            )
            await self._checkpoint(saga)
            detail["outcome"] = saga.outcome.value
            return detail

        if adapter is None:
            saga.mutation_blocked = True
            saga.terminate(
                SagaOutcome.ESCALATED,
                "restart reconcile requires a Kubernetes adapter",
            )
            await self._checkpoint(saga)
            detail["outcome"] = saga.outcome.value
            return detail

        target = saga.target
        # Re-acquire Lease under the same incident identity when possible.
        acquire_lock = getattr(adapter, "acquire_lock", None)
        lease_ok = True
        if acquire_lock:
            lease_ok = bool(
                await self._retry(
                    acquire_lock,
                    target,
                    saga.incident_id,
                    self.settings.remediation_lock_ttl_seconds,
                )
            )
            if not lease_ok:
                saga.mutation_blocked = True
                saga.terminate(
                    SagaOutcome.ESCALATED,
                    "lost Lease on restart; refuse second mutation and escalate",
                )
                await self._checkpoint(saga)
                detail["outcome"] = saga.outcome.value
                detail["lease"] = "lost"
                return detail
            saga.lease_held = True

        try:
            if action == "continue_verification":
                expected = (
                    saga.expected_template_after_action or saga.selected_template
                )
                read_template = getattr(adapter, "read_template", None)
                if read_template and expected is not None:
                    current = await self._retry(read_template, target)
                    if not templates_equivalent(current, expected):
                        # Desired state conflict: Argo or operator changed template.
                        if saga.original_template is not None:
                            await self._retry(
                                adapter.patch_template, target, saga.original_template
                            )
                            saga.rollback_phase = "conflict_restore"
                            saga.mutation_blocked = True
                            saga.terminate(
                                SagaOutcome.CONFLICTING_DESIRED_STATE,
                                "cluster template != saga expected; restored original",
                            )
                        else:
                            saga.mutation_blocked = True
                            saga.terminate(
                                SagaOutcome.CONFLICTING_DESIRED_STATE,
                                "cluster template != saga expected; no original to restore",
                            )
                        await self._checkpoint(saga)
                        detail["outcome"] = saga.outcome.value
                        return detail
                verification = await self._verification_window(
                    adapter, target, self.settings.verification_polls
                )
                saga.verification_samples = list(verification.get("samples") or [])
                if verification["healthy"]:
                    saga.terminate(SagaOutcome.RESOLVED, "restart continued verification healthy")
                elif saga.original_template is not None:
                    await self._retry(
                        adapter.patch_template, target, saga.original_template
                    )
                    saga.rollback_phase = "restart_restore"
                    rb = await self._verification_window(
                        adapter, target, self.settings.rollback_verification_polls
                    )
                    saga.rollback_verification_samples = list(rb.get("samples") or [])
                    if rb["healthy"]:
                        saga.terminate(
                            SagaOutcome.ROLLED_BACK,
                            "restart restored original after failed verification",
                        )
                    else:
                        saga.mutation_blocked = True
                        saga.terminate(
                            SagaOutcome.ESCALATED,
                            "restart restore unverified",
                        )
                else:
                    saga.mutation_blocked = True
                    saga.terminate(
                        SagaOutcome.ESCALATED,
                        "restart verification failed without original template",
                    )
                await self._checkpoint(saga)
                detail["outcome"] = saga.outcome.value
                return detail

            if action == "restore_original":
                await self._retry(adapter.patch_template, target, saga.original_template)
                saga.rollback_phase = "restart_restore"
                rb = await self._verification_window(
                    adapter, target, self.settings.rollback_verification_polls
                )
                saga.rollback_verification_samples = list(rb.get("samples") or [])
                if rb["healthy"]:
                    saga.terminate(
                        SagaOutcome.ROLLED_BACK,
                        "restart restore original verified",
                    )
                else:
                    saga.mutation_blocked = True
                    saga.terminate(
                        SagaOutcome.ESCALATED,
                        "restart restore original unverified",
                    )
                await self._checkpoint(saga)
                detail["outcome"] = saga.outcome.value
                return detail

            saga.mutation_blocked = True
            saga.terminate(SagaOutcome.ESCALATED, f"unhandled restart action {action}")
            await self._checkpoint(saga)
            detail["outcome"] = saga.outcome.value
            return detail
        finally:
            end = getattr(adapter, "end_argo_window", None)
            if end and saga.argo_window_active:
                try:
                    await self._retry(end, target, saga.incident_id)
                    saga.argo_window_active = False
                    saga.note("startup_argo_window_closed")
                    await self._checkpoint(saga)
                except Exception:
                    log.exception("failed to close argo window on resume")
                    raise
            release_lock = getattr(adapter, "release_lock", None)
            if release_lock and lease_ok:
                try:
                    await self._retry(release_lock, target, saga.incident_id)
                    saga.lease_held = False
                    saga.note("startup_target_lease_released")
                    await self._checkpoint(saga)
                except Exception:
                    log.exception("failed to release lease on resume")
                    raise

