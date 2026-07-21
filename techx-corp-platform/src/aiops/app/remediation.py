from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import timedelta
from typing import Any, Awaitable, Callable

from .config import Settings
from .models import AuditEvent, Incident, IncidentStatus, utcnow
from .runbooks import RunbookCatalog


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
