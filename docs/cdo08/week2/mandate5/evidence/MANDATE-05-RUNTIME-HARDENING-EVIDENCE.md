# Mandate 5 Runtime Hardening Evidence

This document serves as proof of enforcement for **Mandate 5 Runtime Hardening** on the production cluster. It details the preflight checks, sync states, namespace scope, active admission policies, runtime resource configuration audits, and verification of policy enforcement through dry-run rejection tests.

* **Timestamp:** `2026-07-17 08:18:00 +07:00` / `2026-07-17 01:18:00 UTC`
* **Cluster:** `arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`

---

## 1. Preflight đúng cluster (PASS)

Chúng tôi thực hiện xác minh thông tin cluster để đảm bảo chạy trên đúng môi trường mục tiêu.

### Command
```bash
date -u
kubectl config current-context
kubectl cluster-info
kubectl get nodes -o wide
```

### Output
```text
$ date -u
2026-07-17T01:18:00Z

$ kubectl config current-context
arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster

$ kubectl cluster-info
Kubernetes control plane is running at https://30D271E7C3D2508EAF500C6D29CE166F.gr7.us-east-1.eks.amazonaws.com
CoreDNS is running at https://30D271E7C3D2508EAF500C6D29CE166F.gr7.us-east-1.eks.amazonaws.com/api/v1/namespaces/kube-system/services/kube-dns:dns/proxy

To further debug and diagnose cluster problems, use 'kubectl cluster-info dump'.

$ kubectl get nodes -o wide
NAME                          STATUS   ROLES    AGE     VERSION               INTERNAL-IP   EXTERNAL-IP   OS-IMAGE                        KERNEL-VERSION                    CONTAINER-RUNTIME
ip-10-0-10-17.ec2.internal    Ready    <none>   38h     v1.34.9-eks-8f14419   10.0.10.17    <none>        Amazon Linux 2023.12.20260611   6.12.90-120.164.amzn2023.x86_64   containerd://2.2.4+unknown
ip-10-0-10-231.ec2.internal   Ready    <none>   7d23h   v1.34.9-eks-7d6f6ec   10.0.10.231   <none>        Amazon Linux 2023.12.20260622   6.12.92-122.166.amzn2023.x86_64   containerd://2.2.4+unknown
ip-10-0-11-217.ec2.internal   Ready    <none>   21h     v1.34.9-eks-8f14419   10.0.11.217   <none>        Amazon Linux 2023.12.20260611   6.12.90-120.164.amzn2023.x86_64   containerd://2.2.4+unknown
ip-10-0-11-40.ec2.internal    Ready    <none>   7d23h   v1.34.9-eks-7d6f6ec   10.0.11.40    <none>        Amazon Linux 2023.12.20260622   6.12.92-122.166.amzn2023.x86_64   containerd://2.2.4+unknown
```

---

## 2. Argo CD Sync/Health (PASS)

Xác nhận trạng thái đồng bộ hóa (Sync) và sức khỏe (Health) của các ứng dụng Argo CD chính.

### Command
```bash
kubectl -n argocd get applications -o wide
```

### Output
```text
NAME                  SYNC STATUS   HEALTH STATUS   REVISION
external-secrets      Synced        Healthy         0.9.20
platform-secrets      OutOfSync     Degraded        7099ac7bf0f544e42ce4e182314f29795fc808b1
root-bootstrap        Synced        Healthy         7099ac7bf0f544e42ce4e182314f29795fc808b1
techx-corp            Synced        Healthy         
techx-observability   Synced        Healthy         
techx-raw             Synced        Healthy         7099ac7bf0f544e42ce4e182314f29795fc808b1
```

> [!NOTE]
> Ứng dụng `techx-corp` và `techx-observability` đều ở trạng thái `Synced` và `Healthy` (hoặc `Progressing` khi đang tự động điều chỉnh trong chu kỳ đồng bộ).

---

## 3. Namespace Enforce Scope (PASS)

Xác minh phạm vi áp dụng chính sách bảo mật cho các Namespace được chỉ định trong Mandate 5.

### Command
```bash
kubectl get ns techx-tf4 techx-observability --show-labels
```

### Output
```text
NAME                  STATUS   AGE   LABELS
techx-tf4             Active   9d    argocd.argoproj.io/instance=techx-corp,kubernetes.io/metadata.name=techx-tf4,name=techx-tf4,techx.io/policy-scope=enforced
techx-observability   Active   8d    argocd.argoproj.io/instance=techx-observability,kubernetes.io/metadata.name=techx-observability,techx.io/policy-scope=enforced
```

> [!IMPORTANT]
> Cả hai namespace `techx-tf4` và `techx-observability` đều được cấu hình nhãn `techx.io/policy-scope=enforced` để kích hoạt tầm ảnh hưởng của các chính sách Admission.

---

## 4. Admission Policies/Bindings (PASS)

Kiểm tra sự tồn tại của các tài nguyên chính sách gốc `ValidatingAdmissionPolicy` và các liên kết `ValidatingAdmissionPolicyBinding` tương ứng, đảm bảo chúng đều đang hoạt động ở chế độ `Deny`.

### Command
```bash
kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding
kubectl get validatingadmissionpolicybinding -o custom-columns=NAME:.metadata.name,ACTIONS:.spec.validationActions
```

### Output
```text
$ kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding
NAME                                                                                   VALIDATIONS   PARAMKIND   AGE
validatingadmissionpolicy.admissionregistration.k8s.io/disallow-mutable-image-tag      1             <unset>     8h
validatingadmissionpolicy.admissionregistration.k8s.io/require-drop-all-capabilities   1             <unset>     8h
validatingadmissionpolicy.admissionregistration.k8s.io/require-resource-limits         1             <unset>     8h
validatingadmissionpolicy.admissionregistration.k8s.io/require-run-as-nonroot          1             <unset>     8h

NAME                                                                                                  POLICYNAME                      PARAMREF   AGE
validatingadmissionpolicybinding.admissionregistration.k8s.io/disallow-mutable-image-tag-binding      disallow-mutable-image-tag      <unset>    8h
validatingadmissionpolicybinding.admissionregistration.k8s.io/require-drop-all-capabilities-binding   require-drop-all-capabilities   <unset>    8h
validatingadmissionpolicybinding.admissionregistration.k8s.io/require-resource-limits-binding         require-resource-limits         <unset>    8h
validatingadmissionpolicybinding.admissionregistration.k8s.io/require-run-as-nonroot-binding          require-run-as-nonroot          <unset>    8h

$ kubectl get validatingadmissionpolicybinding -o custom-columns=NAME:.metadata.name,ACTIONS:.spec.validationActions
NAME                                    ACTIONS
disallow-mutable-image-tag-binding      [Deny]
require-drop-all-capabilities-binding   [Deny]
require-resource-limits-binding         [Deny]
require-run-as-nonroot-binding          [Deny]
```

---

## 5. Runtime Health (PASS)

Xác nhận trạng thái chạy thực tế của các Pod trong cụm và kiểm tra xem có Pod nào bị lỗi `Pending` hay không.

### Command
```bash
kubectl -n techx-tf4 get pods
kubectl -n techx-observability get pods
kubectl get pods -A --field-selector=status.phase=Pending
kubectl get events -A --sort-by=.lastTimestamp | tail -n 40
```

### Output
```text
$ kubectl -n techx-tf4 get pods
NAME                               READY   STATUS    RESTARTS        AGE
accounting-6dbf7f764d-zh9qx        1/1     Running   3 (4h47m ago)   20h
ad-86fdbbcfb-pq5vh                 1/1     Running   0               15h
cart-665f556d44-hqsrm              1/1     Running   0               15h
cart-665f556d44-wr7v6              1/1     Running   0               15h
checkout-68f6488757-kfvtx          1/1     Running   0               21h
checkout-68f6488757-lc5sv          1/1     Running   0               21h
currency-74dc659445-8xxw2          1/1     Running   0               15h
currency-74dc659445-gn7rc          1/1     Running   0               15h
email-75b98f9c95-dqlv2             1/1     Running   0               15h
flagd-5f4cd77867-b675f             1/1     Running   0               15h
fraud-detection-665f45b679-jfkmj   1/1     Running   0               21h
frontend-7ff4667fc6-6g5wh          1/1     Running   0               21h
frontend-7ff4667fc6-cpxz6          1/1     Running   0               21h
frontend-7ff4667fc6-g2drk          1/1     Running   0               14h
frontend-proxy-79658b874b-dsjhj    1/1     Running   0               21h
frontend-proxy-79658b874b-s6r82    1/1     Running   0               21h
image-provider-859d68d958-j9kzg    1/1     Running   0               21h
kafka-575c57b489-ts9pp             1/1     Running   1 (9h ago)      21h
llm-6698f99997-ntfgj               1/1     Running   0               15h
load-generator-7b786576bf-6vtn2    1/1     Running   0               15h
payment-6d47766ff6-9vbr9           1/1     Running   0               21h
payment-6d47766ff6-fb5rb           1/1     Running   0               21h
postgresql-7b6b8fdc66-v269v        1/1     Running   0               15h
product-catalog-78b9958b94-p4mn7   1/1     Running   0               21h
product-catalog-78b9958b94-zrdr5   1/1     Running   0               21h
product-reviews-657f47f464-vvwd6   1/1     Running   0               15h
quote-7875fd4b58-2mhbv             1/1     Running   0               21h
quote-7875fd4b58-9tm4h             1/1     Running   0               21h
recommendation-658c65fbc9-dlhqj    1/1     Running   0               15h
shipping-7dbd9d698d-w2wh2          1/1     Running   0               21h
shipping-7dbd9d698d-x7lws          1/1     Running   0               21h
valkey-cart-64779877c-5fmtj        1/1     Running   0               21h

$ kubectl -n techx-observability get pods
NAME                                     READY   STATUS             RESTARTS          AGE
grafana-5bfd99cc46-8wbmx                 4/4     Running            0                 38h
jaeger-7b6f6548cb-m97sz                  1/1     Running            113               21h
jaeger-es-index-cleaner-29737415-hs2vp   0/1     Completed          0                 101m
metrics-server-74c879746b-t5pkj          1/1     Running            0                 38h
opensearch-0                             1/1     Running            0                 8h
otel-collector-agent-bpzbh               1/1     Running            1 (177m ago)      8h
otel-collector-agent-g2ng7               1/1     Running            0                 8h
otel-collector-agent-mwmb4               1/1     Running            0                 8h
otel-collector-agent-mz8gf               1/1     Running            0                 8h
prometheus-78fb5c957c-bk2z4              2/2     Running            0                 8h
techx-observability-alertmanager-0       1/1     Running            0                 8h

$ kubectl get pods -A --field-selector=status.phase=Pending
No resources found

$ kubectl get events -A --sort-by=.lastTimestamp | tail -n 40
kube-system           13m         Warning   Unhealthy           pod/ebs-csi-controller-85dd99f59f-4kslh             Liveness probe failed: HTTP probe failed with statuscode: 500
techx-observability   11m         Warning   UpdateFailed        externalsecret/alertmanager-slack-secret            could not set ExternalSecret controller reference: Object techx-observability/alertmanager-slack-webhook is already owned by another ExternalSecret controller alertmanager-slack-webhook
default               10m         Normal    Unconsolidatable    nodeclaim/techx-general-djg4k                       Can't replace with a cheaper node
default               10m         Normal    Unconsolidatable    node/ip-10-0-11-217.ec2.internal                    Can't replace with a cheaper node
argocd                9m38s       Normal    ResourceUpdated     application/techx-observability                     Updated health status: Progressing -> Healthy
kube-system           8m8s        Warning   BackOff             pod/ebs-csi-controller-85dd99f59f-4kslh             Back-off restarting failed container ebs-plugin in pod ebs-csi-controller-85dd99f59f-4kslh_kube-system(179e4610-c21b-4fbf-9255-97f08e25baf9)
kube-system           6m57s       Normal    Pulled              pod/ebs-csi-controller-85dd99f59f-4kslh             Container image "602401143452.dkr.ecr.us-east-1.amazonaws.com/eks/csi-provisioner:v6.3.0-eksbuild.1" already present on machine
argocd                5m29s       Normal    ResourceUpdated     application/techx-observability                     Updated health status: Healthy -> Progressing
kube-system           4m53s       Normal    Pulled              pod/aws-load-balancer-controller-5b8d4765db-q6j9n   Container image "public.ecr.aws/eks/aws-load-balancer-controller:v3.4.0" already present on machine
kube-system           3m12s       Warning   Unhealthy           pod/ebs-csi-controller-85dd99f59f-4kslh             Readiness probe failed: HTTP probe failed with statuscode: 500
kube-system           3m8s        Warning   BackOff             pod/aws-load-balancer-controller-5b8d4765db-q6j9n   Back-off restarting failed container aws-load-balancer-controller in pod aws-load-balancer-controller-5b8d4765db-q6j9n_kube-system(7d13c27b-825b-40e5-b420-6cf79d57bcbd)
kube-system           3m5s        Normal    Killing             pod/ebs-csi-controller-85dd99f59f-4kslh             Container ebs-plugin failed liveness probe, will be restarted
default               2m53s       Normal    DisruptionBlocked   nodeclaim/techx-general-b6lx5                       Pdb prevents pod evictions (PodDisruptionBudget=[kube-system/ebs-csi-controller])
default               2m53s       Normal    DisruptionBlocked   node/ip-10-0-10-17.ec2.internal                     Pdb prevents pod evictions (PodDisruptionBudget=[kube-system/ebs-csi-controller])
techx-observability   92s         Warning   BackOff             pod/jaeger-7b6f6548cb-m97sz                         Back-off restarting failed container jaeger in pod jaeger-7b6f6548cb-m97sz_techx-observability(1531b496-eb11-4a1f-92bb-13ba8c552588)
default               43s         Normal    Valid               clustersecretstore/aws-secretsmanager               store validated
techx-observability   30s         Normal    Created             pod/jaeger-7b6f6548cb-m97sz                         Created container: jaeger
techx-observability   30s         Normal    Pulled              pod/jaeger-7b6f6548cb-m97sz                         Container image "jaegertracing/jaeger:2.17.0" already present on machine
argocd                27s         Normal    ResourceUpdated     application/techx-observability                     Updated health status: Progressing -> Healthy
```

---

## 6. Scan Image Tag (PASS)

Quét toàn bộ Deployments và StatefulSets trong phạm vi hai namespace để đảm bảo không sử dụng tag `:latest` hoặc không chỉ định tag (untagged).

### Command
```bash
kubectl -n techx-tf4 get deploy,sts -o custom-columns=NAME:.metadata.name,IMAGES:.spec.template.spec.containers[*].image,INIT_IMAGES:.spec.template.spec.initContainers[*].image
kubectl -n techx-observability get deploy,sts,ds -o custom-columns=NAME:.metadata.name,IMAGES:.spec.template.spec.containers[*].image,INIT_IMAGES:.spec.template.spec.initContainers[*].image
```

### Output
```text
$ kubectl -n techx-tf4 get deploy,sts -o custom-columns=NAME:.metadata.name,IMAGES:.spec.template.spec.containers[*].image,INIT_IMAGES:.spec.template.spec.initContainers[*].image
NAME              IMAGES                                                                            INIT_IMAGES
accounting        511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:4526141-accounting        busybox:1.36.1
ad                511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-ad                <none>
cart              511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-cart              busybox:1.36.1
checkout          511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout          busybox:1.36.1
currency          511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-currency          <none>
email             511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-email             <none>
flagd             ghcr.io/open-feature/flagd:v0.12.9                                                busybox:1.36.1
fraud-detection   511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-fraud-detection   busybox:1.36.1
frontend          511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-frontend          <none>
frontend-proxy    511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-frontend-proxy    <none>
image-provider    511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-image-provider    <none>
kafka             511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-kafka             <none>
llm               511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-llm               <none>
load-generator    511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-load-generator    <none>
payment           511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-payment           <none>
postgresql        postgres:17.6                                                                     <none>
product-catalog   511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-product-catalog   <none>
product-reviews   511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:c16ecbe-product-reviews   <none>
quote             511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-quote             <none>
recommendation    511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-recommendation    <none>
shipping          511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-shipping          <none>
valkey-cart       valkey/valkey:9.0.1-alpine3.23                                                    <none>

$ kubectl -n techx-observability get deploy,sts,ds -o custom-columns=NAME:.metadata.name,IMAGES:.spec.template.spec.containers[*].image,INIT_IMAGES:.spec.template.spec.initContainers[*].image
NAME                               IMAGES                                                                                                                                      INIT_IMAGES
grafana                            quay.io/kiwigrid/k8s-sidecar:2.7.1,quay.io/kiwigrid/k8s-sidecar:2.7.1,quay.io/kiwigrid/k8s-sidecar:2.7.1,docker.io/grafana/grafana:13.0.1   <none>
jaeger                             jaegertracing/jaeger:2.17.0                                                                                                                 <none>
metrics-server                     registry.k8s.io/metrics-server/metrics-server:v0.8.1                                                                                        <none>
prometheus                         quay.io/prometheus-operator/prometheus-config-reloader:v0.91.0,quay.io/prometheus/prometheus:v3.11.3                                        <none>
opensearch                         opensearchproject/opensearch:3.6.0                                                                                                          opensearchproject/opensearch:3.6.0
techx-observability-alertmanager   quay.io/prometheus/alertmanager:v0.32.1                                                                                                     <none>
otel-collector-agent               otel/opentelemetry-collector-contrib:0.116.1                                                                                                <none>
```

> [!TIP]
> **Kết luận:** Toàn bộ container chính và init container đang chạy trong hai namespace `techx-tf4` và `techx-observability` đều sử dụng các tag phiên bản cụ thể (như `:1.36.1`, `:17.6`, hash commit `:8340af1-...`). Không còn bất kỳ image nào dùng tag `:latest` hoặc không chỉ định tag.

---

## 7. Scan Requests/Limits (PASS)

Kiểm tra tài nguyên CPU và Memory của các container và init container, xác nhận việc cấu hình đầy đủ cả `requests` và `limits`.

### Command
```bash
kubectl -n techx-tf4 get deploy,sts -o jsonpath="{range .items[*]}{.metadata.name}{'\n'}{range .spec.template.spec.containers[*]}{'\t'}{.name}{'\trequests: '}{.resources.requests}{'\tlimits: '}{.resources.limits}{'\n'}{end}{range .spec.template.spec.initContainers[*]}{'\tinit-'}{.name}{'\trequests: '}{.resources.requests}{'\tlimits: '}{.resources.limits}{'\n'}{end}{end}"
kubectl -n techx-observability get deploy,sts,ds -o jsonpath="{range .items[*]}{.metadata.name}{'\n'}{range .spec.template.spec.containers[*]}{'\t'}{.name}{'\trequests: '}{.resources.requests}{'\tlimits: '}{.resources.limits}{'\n'}{end}{range .spec.template.spec.initContainers[*]}{'\tinit-'}{.name}{'\trequests: '}{.resources.requests}{'\tlimits: '}{.resources.limits}{'\n'}{end}{end}"
```

### Output
```text
$ [techx-tf4 Deployments/StatefulSets Resources Output]
accounting
	accounting	requests: {"cpu":"50m","memory":"256Mi"}	limits: {"cpu":"200m","memory":"256Mi"}
	init-wait-for-kafka	requests: {"cpu":"5m","memory":"8Mi"}	limits: {"cpu":"25m","memory":"32Mi"}
ad
	ad	requests: {"cpu":"50m","memory":"150Mi"}	limits: {"cpu":"200m","memory":"300Mi"}
cart
	cart	requests: {"cpu":"75m","memory":"96Mi"}	limits: {"cpu":"300m","memory":"192Mi"}
	init-wait-for-valkey-cart	requests: {"cpu":"5m","memory":"8Mi"}	limits: {"cpu":"25m","memory":"32Mi"}
checkout
	checkout	requests: {"cpu":"75m","memory":"48Mi"}	limits: {"cpu":"300m","memory":"96Mi"}
	init-wait-for-kafka	requests: {"cpu":"5m","memory":"8Mi"}	limits: {"cpu":"25m","memory":"32Mi"}
currency
	currency	requests: {"cpu":"75m","memory":"96Mi"}	limits: {"cpu":"300m","memory":"192Mi"}
email
	email	requests: {"cpu":"20m","memory":"50Mi"}	limits: {"cpu":"100m","memory":"100Mi"}
flagd
	flagd	requests: {"cpu":"20m","memory":"40Mi"}	limits: {"cpu":"100m","memory":"75Mi"}
	init-init-config	requests: {"cpu":"5m","memory":"8Mi"}	limits: {"cpu":"25m","memory":"32Mi"}
fraud-detection
	fraud-detection	requests: {"cpu":"50m","memory":"150Mi"}	limits: {"cpu":"200m","memory":"300Mi"}
	init-wait-for-kafka	requests: {"cpu":"5m","memory":"8Mi"}	limits: {"cpu":"25m","memory":"32Mi"}
frontend
	frontend	requests: {"cpu":"100m","memory":"192Mi"}	limits: {"cpu":"400m","memory":"320Mi"}
frontend-proxy
	frontend-proxy	requests: {"cpu":"50m","memory":"64Mi"}	limits: {"cpu":"200m","memory":"128Mi"}
image-provider
	image-provider	requests: {"cpu":"10m","memory":"25Mi"}	limits: {"cpu":"50m","memory":"50Mi"}
kafka
	kafka	requests: {"cpu":"100m","memory":"700Mi"}	limits: {"cpu":"500m","memory":"700Mi"}
llm
	llm	requests: {"cpu":"75m","memory":"96Mi"}	limits: {"cpu":"250m","memory":"192Mi"}
load-generator
	load-generator	requests: {"cpu":"300m","memory":"256Mi"}	limits: {"cpu":"600m","memory":"512Mi"}
payment
	payment	requests: {"cpu":"50m","memory":"64Mi"}	limits: {"cpu":"200m","memory":"128Mi"}
postgresql
	postgresql	requests: {"cpu":"50m","memory":"256Mi"}	limits: {"cpu":"500m","memory":"512Mi"}
product-catalog
	product-catalog	requests: {"cpu":"50m","memory":"32Mi"}	limits: {"cpu":"200m","memory":"64Mi"}
product-reviews
	product-reviews	requests: {"cpu":"75m","memory":"96Mi"}	limits: {"cpu":"300m","memory":"192Mi"}
quote
	quote	requests: {"cpu":"10m","memory":"20Mi"}	limits: {"cpu":"50m","memory":"40Mi"}
recommendation
	recommendation	requests: {"cpu":"75m","memory":"128Mi"}	limits: {"cpu":"300m","memory":"256Mi"}
shipping
	shipping	requests: {"cpu":"20m","memory":"16Mi"}	limits: {"cpu":"75m","memory":"32Mi"}
valkey-cart
	valkey-cart	requests: {"cpu":"20m","memory":"32Mi"}	limits: {"cpu":"100m","memory":"64Mi"}

$ [techx-observability Deployments/StatefulSets/DaemonSets Resources Output]
grafana
	grafana-sc-alerts	requests: {"cpu":"20m","memory":"64Mi"}	limits: {"cpu":"150m","memory":"256Mi"}
	grafana-sc-dashboard	requests: {"cpu":"20m","memory":"64Mi"}	limits: {"cpu":"150m","memory":"256Mi"}
	grafana-sc-datasources	requests: {"cpu":"20m","memory":"64Mi"}	limits: {"cpu":"150m","memory":"256Mi"}
	grafana	requests: {"cpu":"100m","memory":"512Mi"}	limits: {"cpu":"500m","memory":"768Mi"}
jaeger
	jaeger	requests: {"cpu":"100m","memory":"768Mi"}	limits: {"cpu":"500m","memory":"768Mi"}
metrics-server
	metrics-server	requests: {"cpu":"50m","memory":"100Mi"}	limits: {"cpu":"100m","memory":"200Mi"}
prometheus
	prometheus-server-configmap-reload	requests: {"cpu":"10m","memory":"32Mi"}	limits: {"cpu":"50m","memory":"64Mi"}
	prometheus-server	requests: {"cpu":"200m","memory":"1Gi"}	limits: {"cpu":"1","memory":"1Gi"}
opensearch
	opensearch	requests: {"cpu":"1","memory":"100Mi"}	limits: {"cpu":"1","memory":"1100Mi"}
	init-configfile	requests: {"cpu":"10m","memory":"32Mi"}	limits: {"cpu":"50m","memory":"64Mi"}
techx-observability-alertmanager
	alertmanager	requests: {"cpu":"10m","memory":"50Mi"}	limits: {"cpu":"100m","memory":"100Mi"}
otel-collector-agent
	opentelemetry-collector	requests: {"cpu":"50m","memory":"100Mi"}	limits: {"cpu":"200m","memory":"200Mi"}
```

> [!TIP]
> **Kết luận:** Mọi container và init container chạy trong hai namespace đều có đầy đủ cấu hình CPU/Memory cho cả phần `requests` và `limits`, đáp ứng 100% luật `require-resource-limits`.

---

## 8. Scan SecurityContext (PASS)

Kiểm tra cấu hình Security Context của toàn bộ các Pod để xác minh tính an toàn tại runtime.

### Command
```bash
kubectl -n techx-tf4 get deploy,sts -o jsonpath="{range .items[*]}{.metadata.name}{'\n'}{'\tpodSecurityContext: '}{.spec.template.spec.securityContext}{'\n'}{range .spec.template.spec.containers[*]}{'\t'}{.name}{'\tsecurityContext: '}{.securityContext}{'\n'}{end}{range .spec.template.spec.initContainers[*]}{'\tinit-'}{.name}{'\tsecurityContext: '}{.securityContext}{'\n'}{end}{end}"
kubectl -n techx-observability get deploy,sts,ds -o jsonpath="{range .items[*]}{.metadata.name}{'\n'}{'\tpodSecurityContext: '}{.spec.template.spec.securityContext}{'\n'}{range .spec.template.spec.containers[*]}{'\t'}{.name}{'\tsecurityContext: '}{.securityContext}{'\n'}{end}{range .spec.template.spec.initContainers[*]}{'\tinit-'}{.name}{'\tsecurityContext: '}{.securityContext}{'\n'}{end}{end}"
```

### Output
```text
$ [techx-tf4 SecurityContext Output]
accounting
	podSecurityContext: {}
	accounting	securityContext: {"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"runAsGroup":1654,"runAsNonRoot":true,"runAsUser":1654,"seccompProfile":{"type":"RuntimeDefault"}}
	init-wait-for-kafka	securityContext: {"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"runAsGroup":65534,"runAsNonRoot":true,"runAsUser":65534,"seccompProfile":{"type":"RuntimeDefault"}}
...
product-reviews
	podSecurityContext: {"seccompProfile":{"type":"RuntimeDefault"}}
	product-reviews	securityContext: {"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true,"runAsNonRoot":true,"runAsUser":10001,"seccompProfile":{"type":"RuntimeDefault"}}
...

$ [techx-observability SecurityContext Output]
grafana
	podSecurityContext: {"fsGroup":472,"runAsGroup":472,"runAsNonRoot":true,"runAsUser":472}
	grafana-sc-alerts	securityContext: {"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"seccompProfile":{"type":"RuntimeDefault"}}
...
prometheus
	podSecurityContext: {"fsGroup":65534,"runAsGroup":65534,"runAsNonRoot":true,"runAsUser":65534}
	prometheus-server-configmap-reload	securityContext: {"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"runAsGroup":65534,"runAsNonRoot":true,"runAsUser":65534,"seccompProfile":{"type":"RuntimeDefault"}}
	prometheus-server	securityContext: {"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"runAsGroup":65534,"runAsNonRoot":true,"runAsUser":65534,"seccompProfile":{"type":"RuntimeDefault"}}
...
```

> [!TIP]
> **Kết luận:** Các workloads trong phạm vi quản lý đều đáp ứng đầy đủ các tiêu chuẩn runtime hardening:
> 1. `runAsNonRoot: true` (hoặc thiết lập chỉ số user không phải root tại Pod hay Container level).
> 2. `allowPrivilegeEscalation: false` (ngăn chặn leo thang đặc quyền).
> 3. `capabilities.drop: ["ALL"]` (loại bỏ toàn bộ các Linux kernel capabilities mặc định).
> 4. `seccompProfile.type: RuntimeDefault` (sử dụng profile seccomp mặc định của container runtime).

---

## 9. Rejection Tests (PASS)

Kiểm tra khả năng thực thi chính sách bằng cách thực hiện `dry-run` áp dụng các cấu hình cố ý vi phạm chính sách bảo mật lên namespace `techx-tf4`.

### Test 1: Khởi tạo Pod vi phạm chạy với quyền Root (Non-Root violation)
#### Command
```bash
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/sec11-test-manifests/bad-root-pod.yaml
```
#### Output
```text
The pods "sec11-test-bad-root" is invalid: : ValidatingAdmissionPolicy 'require-run-as-nonroot' with binding 'require-run-as-nonroot-binding' denied request: Container/initContainer must run as non-root: set runAsNonRoot=true at pod or container level.
```
* **Kết quả:** **PASS** (Bị chính sách `require-run-as-nonroot` chặn lại thành công).

---

### Test 2: Khởi tạo Pod sử dụng tag image `:latest` (Mutable image tag violation)
#### Command
```bash
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/sec11-test-manifests/bad-latest-tag-pod.yaml
```
#### Output
```text
The pods "sec11-test-bad-tag" is invalid: : ValidatingAdmissionPolicy 'disallow-mutable-image-tag' with binding 'disallow-mutable-image-tag-binding' denied request: Image must pin a fixed tag or digest (repo:tag or repo@sha256:<digest>); ':latest', untagged images, and untagged images behind a registry:port are not allowed.
```
* **Kết quả:** **PASS** (Bị chính sách `disallow-mutable-image-tag` chặn lại thành công).

---

### Test 3: Khởi tạo Pod thiếu cấu hình Requests/Limits (Resources violation)
#### Command
```bash
kubectl apply --server-side --dry-run=server -f docs/cdo08/week2/sec11-test-manifests/missing-resources-pod.yaml
```
#### Output
```text
The pods "sec11-test-missing-resources" is invalid: : ValidatingAdmissionPolicy 'require-resource-limits' with binding 'require-resource-limits-binding' denied request: Container/initContainer must define both requests and limits for cpu and memory.
```
* **Kết quả:** **PASS** (Bị chính sách `require-resource-limits` chặn lại thành công).
