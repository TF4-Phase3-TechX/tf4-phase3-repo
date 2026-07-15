Please grant the CD deploy identity temporary Kubernetes RBAC in namespace techx-observability for OpenSearch PVC migration:

- apps/statefulsets: get, list, watch, delete
- core/pods: get, list, watch, delete
- core/persistentvolumeclaims: get, list, watch

Scope delete permissions to:

- statefulsets.apps/opensearch
- pods/opensearch-0

Reason:
OpenSearch StatefulSet was created without volumeClaimTemplates. Enabling opensearch.persistence.enabled=true requires recreating the StatefulSet because Kubernetes forbids patching
volumeClaimTemplates on an existing StatefulSet. CD needs to orphan-delete sts/opensearch before helm upgrade, then recreate opensearch-0 after Helm creates the new StatefulSet with PVC.
