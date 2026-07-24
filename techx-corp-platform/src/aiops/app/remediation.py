from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from typing import Any, Awaitable, Callable

from .config import Settings
from .models import AuditEvent, Incident, IncidentStatus, utcnow
from .runbooks import RunbookCatalog


class PolicyDenied(RuntimeError):
    pass


class KubernetesRollbackAdapter:
    """Bounded adapter: Deployment template rollback only, never free-form commands."""

    def __init__(self, namespace: str, deployment_recency_hours: int = 24):
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
        serializer = self.kube_client.ApiClient()
        return (
            serializer.sanitize_for_serialization(current.spec.template),
            serializer.sanitize_for_serialization(owned[1].spec.template),
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


class RemediationController:
    """Policy-gated detect -> act -> verify -> rollback/escalate controller."""

    def __init__(
        self,
        settings: Settings,
        adapter: KubernetesRollbackAdapter | None = None,
        verifier: Callable[[str], Awaitable[dict[str, Any]]] | None = None,
        catalog: RunbookCatalog | None = None,
    ):
        self.settings = settings
        self.adapter = adapter
        self.verifier = verifier
        self.catalog = catalog or RunbookCatalog()
        self._locks: set[str] = set()

    async def _retry(self, function: Callable[..., Any], *args: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return await asyncio.to_thread(function, *args)
            except PolicyDenied:
                raise
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(1.0)
        raise RuntimeError(
            f"Kubernetes action failed after two attempts: {last_error}"
        ) from last_error

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
            "evidence_present": bool(incident.evidence),
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
            incident.status = IncidentStatus.ESCALATED
            incident.escalation_reason = str(exc)
            incident.mutation_blocked = True
            incident.audit_events.append(
                AuditEvent(event="autonomous_policy_denied_escalation", detail={"reason": str(exc)})
            )

    async def _verification_window(
        self,
        adapter: KubernetesRollbackAdapter,
        target: str,
        polls: int,
    ) -> dict[str, Any]:
        samples: list[dict[str, Any]] = []
        required = max(polls, 1)
        for index in range(required):
            ready = bool(await self._retry(adapter.rollout_ready, target))
            slo = (
                await self.verifier(target)
                if ready and self.verifier
                else {"healthy": False, "reason": "rollout_not_ready_or_verifier_missing"}
            )
            samples.append({"poll": index + 1, "rollout_ready": ready, "slo": slo})
            if index + 1 < required and self.settings.verification_interval_seconds > 0:
                await asyncio.sleep(self.settings.verification_interval_seconds)
        return {
            "healthy": all(
                sample["rollout_ready"] and sample["slo"].get("healthy", False)
                for sample in samples
            ),
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
        await self._retry(adapter.patch_template, target, original)
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

        self._locks.add(target)
        adapter: KubernetesRollbackAdapter | None = None
        original: dict[str, Any] | None = None
        mutated = False
        external_lock = False
        try:
            incident.execution_attempts += 1
            incident.status = IncidentStatus.EXECUTING
            incident.audit_events.append(
                AuditEvent(
                    event="action_preflight_started",
                    detail={"target": target, "mode": self.settings.remediation_mode},
                )
            )
            if self.settings.remediation_mode != "live":
                incident.verification_result = {
                    "mode": "dry-run",
                    "eligible": True,
                    "target": target,
                    "policy_version": incident.policy_version,
                }
                incident.status = IncidentStatus.ESCALATED
                incident.escalation_reason = "Dry-run completed; no mutation performed"
                incident.audit_events.append(AuditEvent(event="dry_run_completed"))
                return

            adapter = self.adapter or KubernetesRollbackAdapter(
                self.settings.namespace, self.settings.deployment_recency_hours
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
                incident.audit_events.append(AuditEvent(event="target_lease_acquired"))
            original, previous = await self._retry(adapter.previous_template, target)
            incident.before_snapshot = (
                await self.verifier(target)
                if self.verifier
                else {"healthy": False, "reason": "verifier_missing"}
            )
            incident.audit_events.append(
                AuditEvent(event="action_preflight_passed", detail={"target": target})
            )
            dry_run = getattr(adapter, "dry_run_patch_template", None)
            if dry_run:
                await self._retry(dry_run, target, previous)
                incident.audit_events.append(
                    AuditEvent(event="kubernetes_server_dry_run_passed")
                )
            await self._retry(adapter.patch_template, target, previous)
            mutated = True
            incident.audit_events.append(AuditEvent(event="action_executed"))
            incident.status = IncidentStatus.VERIFYING
            verification = await self._verification_window(
                adapter, target, self.settings.verification_polls
            )
            incident.verification_result = verification
            if verification["healthy"]:
                incident.status = IncidentStatus.RESOLVED
                incident.audit_events.append(AuditEvent(event="remediation_verified"))
                return
            incident.escalation_reason = "Remediation did not recover during the stabilization window"
            await self._rollback_and_verify(
                incident, adapter, target, original, incident.escalation_reason
            )
        except PolicyDenied as exc:
            if not mutated:
                incident.status = IncidentStatus.ESCALATED
                incident.mutation_blocked = True
                incident.escalation_reason = str(exc)
                incident.audit_events.append(
                    AuditEvent(
                        event="pre_mutation_policy_denied_escalation",
                        detail={"reason": str(exc)},
                    )
                )
            raise
        except Exception as exc:
            incident.escalation_reason = f"Remediation failed: {type(exc).__name__}: {exc}"
            if mutated and adapter and original:
                try:
                    await self._rollback_and_verify(
                        incident, adapter, target, original, incident.escalation_reason
                    )
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
            else:
                incident.status = IncidentStatus.ESCALATED
                incident.mutation_blocked = True
                incident.audit_events.append(
                    AuditEvent(event="execution_failed_before_mutation")
                )
        finally:
            if external_lock and adapter:
                release_lock = getattr(adapter, "release_lock", None)
                if release_lock:
                    try:
                        await self._retry(release_lock, target, incident.incident_id)
                        incident.audit_events.append(AuditEvent(event="target_lease_released"))
                    except Exception as exc:
                        incident.audit_events.append(
                            AuditEvent(
                                event="target_lease_release_failed",
                                detail={"error": str(exc)},
                            )
                        )
            self._locks.discard(target)
