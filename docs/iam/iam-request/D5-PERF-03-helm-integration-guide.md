# Hướng dẫn Tích hợp Quyền RBAC CDO-04 vào Helm Chart (`techx-corp-chart`)

Tài liệu này hướng dẫn cách đưa cấu hình Kubernetes RBAC của yêu cầu **D5-PERF-03** trực tiếp vào file template [team-rbac.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/templates/team-rbac.yaml) trong Helm Chart của hệ thống để quản trị đồng bộ qua GitOps.

---

## 1. Các bước thực hiện

1. Mở file [techx-corp-chart/templates/team-rbac.yaml](file:///d:/xbrain/tf4-phase3-repo/techx-corp-chart/templates/team-rbac.yaml).
2. Tích hợp cấu hình YAML tương ứng vào các khối điều kiện `{{- if eq .Release.Namespace "..." }}` như hướng dẫn chi tiết dưới đây.
3. Commit thay đổi lên Git branch và chạy pipeline deploy Helm Chart.

---

## 2. Chi tiết cấu hình YAML cần thêm vào `team-rbac.yaml`

### BƯỚC A: Thêm vào khối namespace `"techx-observability"`
*Tìm dòng `{{- if eq .Release.Namespace "techx-observability" }}` ở đầu file, cuộn xuống trước từ khóa `{{- end }}` của khối này (khoảng dòng 57) và dán nội dung sau:*

```yaml
---
# === RBAC cho nhóm Cost & Performance CDO-04 (cost-perf-readonly-alerting-users) ===
# 1. ClusterRole & ClusterRoleBinding để đọc Node allocatable và Metrics (kubectl top)
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cdo04-runtime-capacity-readonly
rules:
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["metrics.k8s.io"]
    resources: ["pods", "nodes"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: cdo04-runtime-capacity-readonly-binding
subjects:
  - kind: Group
    name: "cost-perf-readonly-alerting-users"
    apiGroup: rbac.authorization.k8s.io
  - kind: Group
    name: "base-readonly-users"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: cdo04-runtime-capacity-readonly
  apiGroup: rbac.authorization.k8s.io
---
# 2. Role & RoleBinding phục vụ Helm Rollout/Rollback trong techx-observability
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: cdo04-controlled-change-role
  namespace: techx-observability
rules:
  - apiGroups: [""]
    resources: ["pods", "events", "services", "endpoints", "resourcequotas", "limitranges", "persistentvolumeclaims"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
  - apiGroups: ["apps"]
    resources: ["replicasets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets"]
    verbs: ["get", "list", "watch", "patch", "update"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch", "patch", "update"]
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list", "create", "patch", "update", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: cdo04-controlled-change-binding
  namespace: techx-observability
subjects:
  - kind: Group
    name: "cost-perf-readonly-alerting-users"
    apiGroup: rbac.authorization.k8s.io
  - kind: Group
    name: "base-readonly-users"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: cdo04-controlled-change-role
  apiGroup: rbac.authorization.k8s.io
```

---

### BƯỚC B: Thêm vào khối namespace `"techx-tf4"`
*Tìm dòng `{{- if eq .Release.Namespace "techx-tf4" }}` (khoảng dòng 59), cuộn xuống trước từ khóa `{{- end }}` cuối file (khoảng dòng 123) và dán nội dung sau:*

```yaml
---
# === RBAC cho nhóm Cost & Performance CDO-04 (cost-perf-readonly-alerting-users) ===
# Role & RoleBinding phục vụ Helm Rollout/Rollback trong techx-tf4
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: cdo04-controlled-change-role
  namespace: techx-tf4
rules:
  - apiGroups: [""]
    resources: ["pods", "events", "services", "endpoints", "resourcequotas", "limitranges", "persistentvolumeclaims"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
  - apiGroups: ["apps"]
    resources: ["replicasets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets"]
    verbs: ["get", "list", "watch", "patch", "update"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch", "patch", "update"]
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list", "create", "patch", "update", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: cdo04-controlled-change-binding
  namespace: techx-tf4
subjects:
  - kind: Group
    name: "cost-perf-readonly-alerting-users"
    apiGroup: rbac.authorization.k8s.io
  - kind: Group
    name: "base-readonly-users"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: cdo04-controlled-change-role
  apiGroup: rbac.authorization.k8s.io
```

---

### BƯỚC C: Thêm khối mới cho `"techx-admission-test"`
*Dán đoạn code điều kiện này vào cuối file (sau block của `techx-tf4`):*

```yaml
{{- if eq .Release.Namespace "techx-admission-test" }}
# === RBAC cho nhóm Cost & Performance CDO-04 (cost-perf-readonly-alerting-users) ===
# Role & RoleBinding để tạo/xóa test workloads trong techx-admission-test namespace
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: cdo04-admission-test-role
  namespace: techx-admission-test
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "create", "delete"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "create", "delete"]
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: cdo04-admission-test-binding
  namespace: techx-admission-test
subjects:
  - kind: Group
    name: "cost-perf-readonly-alerting-users"
    apiGroup: rbac.authorization.k8s.io
  - kind: Group
    name: "base-readonly-users"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: cdo04-admission-test-role
  apiGroup: rbac.authorization.k8s.io
{{- end }}
```
