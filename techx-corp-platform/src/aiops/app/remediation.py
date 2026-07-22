from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from .config import Settings
from .models import AuditEvent, Incident, IncidentStatus, utcnow
from .runbooks import RunbookCatalog

# Incident types that are pre-authorized for autonomous execution.
# Expanding this set requires an explicit CDO policy update in runbooks.yaml
# AND a deployment with REMEDIATION_MODE=live. Arbitrary types are not added here.
AUTONOMOUS_INCIDENT_TYPES: frozenset[str] = frozenset({
    "service_latency_spike",
})


class PolicyDenied(RuntimeError):
    pass


class KubernetesRollbackAdapter:
    def __init__(self, namespace: str, deployment_recency_hours: int = 24):
        from kubernetes import client as kube_client, config as kube_config

        try:
            kube_config.load_incluster_config()
        except kube_config.ConfigException:
            kube_config.load_kube_config()
        self.kube_client = kube_client
        self.api = kube_client.AppsV1Api()
        self.namespace = namespace
        self.deployment_recency_hours = deployment_recency_hours

    def previous_template(
        self, deployment: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        current = self.api.read_namespaced_deployment(deployment, self.namespace)
        replicasets = self.api.list_namespaced_replica_set(
            self.namespace,
            label_selector=",".join(
                f"{k}={v}" for k, v in current.spec.selector.match_labels.items()
            ),
        ).items
        owned = [
            rs
            for rs in replicasets
            if any(
                o.uid == current.metadata.uid
                for o in (rs.metadata.owner_references or [])
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
        return serializer.sanitize_for_serialization(
            current.spec.template
        ), serializer.sanitize_for_serialization(owned[1].spec.template)

    def patch_template(self, deployment: str, template: dict[str, Any]) -> None:
        self.api.patch_namespaced_deployment(
            deployment, self.namespace, {"spec": {"template": template}}
        )

    def rollout_ready(self, deployment: str) -> bool:
        obj = self.api.read_namespaced_deployment_status(deployment, self.namespace)
        desired = obj.spec.replicas or 1
        return (obj.status.updated_replicas or 0) >= desired and (
            obj.status.available_replicas or 0
        ) >= desired


class RemediationController:
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
        # Tracks the UTC time after which a target is eligible for autonomous action again.
        self._cooldowns: dict[str, datetime] = {}

    def should_auto_execute(self, incident: Incident) -> tuple[bool, str]:
        """Pre-authorized policy gate — no per-incident human input required.

        Returns (True, "") when the incident may be auto-executed, or
        (False, reason) when it is blocked by policy.

        Gate checks (all must pass):
        1. Incident type is in the pre-authorized autonomous allowlist.
        2. A runbook with a concrete automatic_action exists.
        3. Target service is in the CDO-approved deployment allowlist.
        4. Detector confidence ≥ remediation_confidence_threshold.
        5. Target is not in cooldown window from a previous autonomous action.
        6. Target is not currently locked (another action running).
        7. execution_attempts == 0 (blast-radius: no retry loop).
        """
        if incident.incident_type not in AUTONOMOUS_INCIDENT_TYPES:
            return False, f"incident_type '{incident.incident_type}' is not pre-authorized for autonomous execution"

        try:
            action = self.catalog.action_for(incident.runbook_id)
        except ValueError as exc:
            return False, f"runbook lookup failed: {exc}"
        if not action:
            return False, f"runbook '{incident.runbook_id}' has no automatic_action defined"

        target = incident.affected_service
        if target not in self.settings.allowed_deployments:
            return False, f"service '{target}' is not in the CDO-approved allowlist"

        if incident.confidence < self.settings.remediation_confidence_threshold:
            return False, (
                f"confidence {incident.confidence:.3f} < threshold "
                f"{self.settings.remediation_confidence_threshold}"
            )

        now = utcnow()
        cooldown_until = self._cooldowns.get(target)
        if cooldown_until and now < cooldown_until:
            remaining = int((cooldown_until - now).total_seconds())
            return False, f"'{target}' is in cooldown for {remaining}s more"

        if target in self._locks:
            return False, f"'{target}' is locked — another action is already running"

        if incident.execution_attempts > 0:
            return False, "blast-radius guard: execution_attempts > 0; no autonomous retry loop"

        return True, ""

    async def autonomous_execute(self, incident: Incident) -> None:
        """Execute the pre-authorized autonomous mitigation path.

        Uses the same Kubernetes rollback + verify + rollback-on-fail
        logic as execute(), but records auto_approved=True in the audit chain
        and bypasses the per-incident approval_status check.
        """
        eligible, reason = self.should_auto_execute(incident)
        if not eligible:
            incident.status = IncidentStatus.ESCALATED
            incident.escalation_reason = f"Autonomous policy gate denied: {reason}"
            incident.audit_events.append(
                AuditEvent(event="autonomous_policy_denied", detail={"reason": reason})
            )
            return

        incident.auto_approved = True
        incident.approval_status = "auto_approved"
        incident.audit_events.append(
            AuditEvent(
                event="autonomous_policy_approved",
                detail={
                    "incident_type": incident.incident_type,
                    "service": incident.affected_service,
                    "confidence": round(incident.confidence, 3),
                    "runbook_id": incident.runbook_id,
                },
            )
        )

        target = incident.affected_service

        # Dry-run fast path — same guard as human-approval path
        if self.settings.remediation_mode != "live":
            incident.verification_result = {
                "mode": "dry-run",
                "eligible": True,
                "target": target,
                "policy": "autonomous",
            }
            incident.status = IncidentStatus.ESCALATED
            incident.escalation_reason = "Autonomous dry-run completed; no production mutation performed"
            incident.audit_events.append(AuditEvent(event="autonomous_dry_run_completed"))
            return

        # Acquire target lock and set cooldown immediately to prevent race conditions
        self._locks.add(target)
        self._cooldowns[target] = utcnow() + timedelta(seconds=self.settings.cooldown_seconds)
        adapter: KubernetesRollbackAdapter | None = None
        original: dict[str, Any] | None = None
        mutated = False
        try:
            incident.execution_attempts += 1
            incident.status = IncidentStatus.AUTO_EXECUTING
            incident.audit_events.append(
                AuditEvent(event="autonomous_execution_started", detail={"target": target})
            )
            adapter = self.adapter or KubernetesRollbackAdapter(
                self.settings.namespace, self.settings.deployment_recency_hours
            )
            original, previous = await self._retry(adapter.previous_template, target)
            await self._retry(adapter.patch_template, target, previous)
            mutated = True
            incident.status = IncidentStatus.VERIFYING
            ready = False
            for _ in range(12):
                await asyncio.sleep(5)
                if await self._retry(adapter.rollout_ready, target):
                    ready = True
                    break
            slo = (
                await self.verifier(target)
                if ready and self.verifier
                else {"healthy": ready, "reason": "rollout-only verification"}
            )
            incident.verification_result = {
                "rollout_ready": ready,
                "target": target,
                "slo": slo,
                "policy": "autonomous",
            }
            if ready and slo.get("healthy", False):
                incident.status = IncidentStatus.RESOLVED
                incident.audit_events.append(
                    AuditEvent(event="autonomous_remediation_verified", detail={"slo": slo})
                )
            else:
                await self._retry(adapter.patch_template, target, original)
                incident.rollback_result = {"restored_original_template": True, "policy": "autonomous"}
                incident.status = IncidentStatus.ROLLED_BACK
                incident.escalation_reason = "Autonomous remediation: rollout did not become ready or SLO unhealthy"
                incident.audit_events.append(
                    AuditEvent(
                        event="autonomous_remediation_rolled_back",
                        detail={"rollout_ready": ready, "slo": slo},
                    )
                )
        except PolicyDenied:
            raise
        except Exception as exc:
            incident.escalation_reason = f"Autonomous remediation failed: {type(exc).__name__}: {exc}"
            if mutated and adapter and original:
                try:
                    await self._retry(adapter.patch_template, target, original)
                    incident.rollback_result = {
                        "restored_original_template": True,
                        "reason": str(exc),
                        "policy": "autonomous",
                    }
                    incident.status = IncidentStatus.ROLLED_BACK
                    incident.audit_events.append(
                        AuditEvent(event="autonomous_rollback_after_error", detail={"error": str(exc)})
                    )
                except Exception as rollback_exc:
                    incident.status = IncidentStatus.ESCALATED
                    incident.rollback_result = {
                        "restored_original_template": False,
                        "error": str(rollback_exc),
                        "policy": "autonomous",
                    }
                    incident.audit_events.append(
                        AuditEvent(
                            event="autonomous_rollback_failed_escalation",
                            detail={"error": str(rollback_exc)},
                        )
                    )
            else:
                incident.status = IncidentStatus.ESCALATED
                incident.audit_events.append(
                    AuditEvent(
                        event="autonomous_execution_failed_before_mutation",
                        detail={"error": str(exc)},
                    )
                )
        finally:
            self._locks.discard(target)

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
        if incident.approval_status != "approved":
            raise PolicyDenied("Per-incident approval is required")
        if incident.confidence < self.settings.remediation_confidence_threshold:
            raise PolicyDenied("RCA confidence is below the remediation threshold")
        if target in self._locks:
            raise PolicyDenied("Another action is already running for this target")
        self._locks.add(target)
        adapter: KubernetesRollbackAdapter | None = None
        original: dict[str, Any] | None = None
        mutated = False
        try:
            incident.execution_attempts += 1
            incident.status = IncidentStatus.EXECUTING
            if self.settings.remediation_mode != "live":
                incident.verification_result = {
                    "mode": "dry-run",
                    "eligible": True,
                    "target": target,
                }
                incident.status = IncidentStatus.ESCALATED
                incident.escalation_reason = (
                    "Dry-run completed; no production mutation was performed"
                )
                incident.audit_events.append(AuditEvent(event="dry_run_completed"))
                return
            adapter = self.adapter or KubernetesRollbackAdapter(
                self.settings.namespace, self.settings.deployment_recency_hours
            )
            original, previous = await self._retry(adapter.previous_template, target)
            await self._retry(adapter.patch_template, target, previous)
            mutated = True
            incident.status = IncidentStatus.VERIFYING
            ready = False
            for _ in range(12):
                await asyncio.sleep(5)
                if await self._retry(adapter.rollout_ready, target):
                    ready = True
                    break
            slo = (
                await self.verifier(target)
                if ready and self.verifier
                else {"healthy": ready, "reason": "rollout-only verification"}
            )
            incident.verification_result = {
                "rollout_ready": ready,
                "target": target,
                "slo": slo,
            }
            if ready and slo.get("healthy", False):
                incident.status = IncidentStatus.RESOLVED
                incident.audit_events.append(AuditEvent(event="remediation_verified"))
            else:
                await self._retry(adapter.patch_template, target, original)
                incident.rollback_result = {"restored_original_template": True}
                incident.status = IncidentStatus.ROLLED_BACK
                incident.escalation_reason = "Remediation rollout did not become ready"
                incident.audit_events.append(
                    AuditEvent(event="remediation_rolled_back")
                )
        except PolicyDenied:
            raise
        except Exception as exc:
            incident.escalation_reason = f"Remediation failed: {type(exc).__name__}"
            if mutated and adapter and original:
                try:
                    await self._retry(adapter.patch_template, target, original)
                    incident.rollback_result = {
                        "restored_original_template": True,
                        "reason": str(exc),
                    }
                    incident.status = IncidentStatus.ROLLED_BACK
                    incident.audit_events.append(
                        AuditEvent(event="remediation_rolled_back_after_error")
                    )
                except Exception as rollback_exc:
                    incident.status = IncidentStatus.ESCALATED
                    incident.rollback_result = {
                        "restored_original_template": False,
                        "error": str(rollback_exc),
                    }
                    incident.audit_events.append(
                        AuditEvent(event="rollback_failed_escalation")
                    )
            else:
                incident.status = IncidentStatus.ESCALATED
                incident.audit_events.append(
                    AuditEvent(event="execution_failed_before_mutation")
                )
        finally:
            self._locks.discard(target)
