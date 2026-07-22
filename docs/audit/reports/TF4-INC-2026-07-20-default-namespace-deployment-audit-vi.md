# Báo cáo sự cố / kiểm toán TF4

## Triển khai Kubernetes sai namespace `default`

**Mã vụ việc:** `TF4-INC-2026-07-20-DEFAULT-DEPLOY`  
**Cluster:** `techx-tf4-cluster` / `us-east-1`  
**Đơn vị nhận báo cáo:** TF4 Audit / CDO-07  
**Phương thức thu thập:** Chỉ đọc  
**Ngày sự cố:** 20/07/2026

## Kết luận điều hành

Năm cảnh báo AlertManager xuất phát từ một bản sao đầy đủ của workload TechX được apply nhầm vào namespace `default`, không phải do toàn bộ production trong `techx-tf4` bị sập.

Nhật ký audit Kubernetes của EKS xác định actor trực tiếp là **SSO session `quyet`**, sử dụng role **`TF4-SecurityIAMSSOManager`**, client `kubectl.exe` và IP nguồn **`14.245.185.195`**. Bằng chứng xác định phiên đã thực hiện API action; chưa đủ để kết luận ý định, tình trạng phê duyệt hay câu lệnh shell chính xác.

## 1. Nguồn bằng chứng và độ tin cậy

| Nguồn | Nội dung xác minh | Độ tin cậy |
|---|---|---|
| EKS Kubernetes audit log | Principal, API verb, namespace, resource, thời điểm, IP nguồn, user-agent và audit ID | Trực tiếp / Cao |
| AWS CloudTrail | SSO identity hoạt động trong cùng cửa sổ thời gian | Đối chứng / Cao |
| Trạng thái Kubernetes | Kiểu lỗi và phạm vi ảnh hưởng ở `default` so với `techx-tf4` | Trực tiếp / Cao |
| Log Argo CD controller | Production trỏ tới `techx-tf4`; create bản sao không do Argo thực hiện | Trực tiếp / Cao |
| Ảnh chụp chat do người dùng cung cấp | Bối cảnh con người; không phải bằng chứng định danh | Chỉ bối cảnh |

## 2. Danh tính người tạo đã được xác minh

| Trường | Giá trị |
|---|---|
| Người dùng / session | `quyet` |
| AWS assumed-role ARN | `arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10/quyet` |
| IAM canonical role | `arn:aws:iam::511825856493:role/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10` |
| Tên session | `quyet` |
| IP nguồn | `14.245.185.195` |
| Client | `kubectl.exe/v1.34.1 (windows/amd64) kubernetes/93248f9` |
| Authenticator principal | `AROAXOKZSY7WVF3EPHAKY` |
| Kết luận về đường truy cập | Xác thực trực tiếp tới Kubernetes API bằng SSO session; không phải service account của Argo |

## 3. Timeline đã xác minh

Tất cả thời gian dưới đây là UTC; ICT = UTC+07.

| UTC | ICT | Sự kiện |
|---|---|---|
| `04:44:57` | `11:44:57` | Thao tác create trực tiếp đầu tiên ở `default`: PDB `cart` |
| `04:45:19–04:45:29` | `11:45:19–11:45:29` | Tạo 21 Deployment ở `default` |
| `04:45:30–04:45:31` | `11:45:30–11:45:31` | Tạo HPA `checkout`, `currency`, `frontend` |
| `04:48:01–04:48:05` | `11:48:01–11:48:05` | User trên patch 9 PDB |
| `04:48:24–04:48:34` | `11:48:24–11:48:34` | User trên patch các Deployment |

## 4. Bằng chứng audit đại diện

Sự kiện đại diện: tạo `default/frontend`.

- **Audit ID:** `c5827909-7e22-4052-98cd-3c80f6c1a4f8`
- **Thời điểm:** `2026-07-20T04:45:23.693654Z`
- **Request URI:**

  ```text
  /apis/apps/v1/namespaces/default/deployments?fieldManager=kubectl-client-side-apply&fieldValidation=Strict
  ```

- **Verb / response:** `create` / HTTP `201`
- **Đối tượng:** `Deployment/frontend`
- **Namespace:** `default`
- **User-agent:** `kubectl.exe/v1.34.1 (windows/amd64) kubernetes/93248f9`
- **IP nguồn:** `14.245.185.195`
- **Dấu hiệu trong manifest:** `namespace: default`, annotation `kubectl.kubernetes.io/last-applied-configuration`, các Helm chart label.

### Diễn giải

Request URI và field manager chứng minh thao tác kiểu `kubectl apply` client-side. Audit log không lưu toàn bộ câu lệnh shell, nên chưa thể khẳng định wrapper chính xác, ví dụ `helm template | kubectl apply -f -` hay apply từ file manifest đã render.

## 5. Tài nguyên người dùng trực tiếp tạo

Trong cửa sổ audit đã rà soát có **50 thao tác create/patch trực tiếp**, không tính các lệnh `get` chỉ đọc. ReplicaSet, Pod, EndpointSlice và Event do Kubernetes controller sinh ra là hành động downstream, không quy cho người dùng.

| Nhóm tài nguyên | Đối tượng | Số lượng |
|---|---|---:|
| Deployment | `accounting`, `ad`, `cart`, `checkout`, `currency`, `email`, `flagd`, `fraud-detection`, `frontend`, `frontend-proxy`, `image-provider`, `kafka`, `llm`, `load-generator`, `payment`, `postgresql`, `product-catalog`, `product-reviews`, `quote`, `recommendation`, `shipping`, `valkey-cart` | 21 |
| HPA | `checkout`, `currency`, `frontend` | 3 |
| PDB | `cart`, `checkout`, `currency`, `frontend`, `frontend-proxy`, `payment`, `product-catalog`, `quote`, `shipping` | 9 |
| ServiceAccount | `product-reviews-bedrock`, `techx-corp` | 2 |
| Service | `ad`, `cart`, `checkout`, `currency`, `email`, `flagd`, `frontend`, `frontend-proxy`, `image-provider`, `kafka`, `llm`, `load-generator`, `payment`, `postgresql`, `product-catalog`, `product-reviews`, `quote`, `recommendation`, `shipping`, `valkey-cart` | 20 |

## 6. Xác minh ảnh hưởng runtime

| Khu vực | Bản sao ở `default` | Production ở `techx-tf4` |
|---|---|---|
| Frontend / checkout / cart | Frontend 2/2; cart và checkout kẹt ở init; dependency path không dùng được | Frontend 3/3; checkout 2/2; cart 2/2 |
| Product catalog | 2 Pod `CrashLoopBackOff`; quan sát 81 lần restart mỗi Pod | 2/2 Ready |
| PostgreSQL / Kafka / Valkey | Không có Pod khả dụng; thiếu `postgresql-pvc`, `kafka-pvc`, `valkey-cart-pvc` | Tất cả Ready |
| flagd / product reviews | Thiếu ConfigMap `flagd-config` và Secret `product-reviews-bedrock-canary` | Ready |
| Load generator | Ready với `LOCUST_AUTOSTART=true`, 10 user | Cũng đang `AUTOSTART=true`; là rủi ro kiểm soát riêng |

## 7. Chuỗi nguyên nhân của alert

- **`BrowseSuccessRateLow`** — `default/product-catalog` không có endpoint dùng được; `flagd` cũng không khả dụng.
- **`CartSuccessRateLow`** — `default/cart` chờ `valkey-cart:6379`; Valkey không schedule được vì thiếu PVC.
- **`CheckoutSuccessRateLow`** — `default/checkout` chờ `kafka:9092`; cart và product catalog cũng không khả dụng.
- **`FrontendErrorRateHigh`** — tổng hợp các lỗi customer-facing từ dependency graph bị hỏng.
- **`LoadGeneratorTrafficOutsideTestWindow`** — load-generator bản sao có `LOCUST_AUTOSTART=true` ngoài cửa sổ test được phê duyệt.
- **Lỗ hổng giám sát** — SLO expression không giới hạn `k8s_namespace_name` vào `techx-tf4`, làm telemetry từ `default` nhiễm vào alert production.

## 8. Đối chiếu Argo CD và quy trách nhiệm

Log Argo CD controller xác nhận:

- Application production: `argocd/techx-corp`
- Namespace đích: `techx-tf4`
- Repository chart: `https://github.com/TF4-Phase3-TechX/tf4-phase3-repo.git`
- Revision: `fccea0c14a4f60b38b394e3eec7f75c7b76a7287`
- Actor của Argo: `system:serviceaccount:argocd:argocd-application-controller`

Các object bản sao trong `default` lại có metadata `kubectl` client-side apply và SSO identity của `quyet`. Vì vậy Argo CD không phải actor trực tiếp tạo bản sao.

## 9. Kết luận và giới hạn

### Kết luận đã xác lập

1. SSO session **`quyet`**, dùng role `TF4-SecurityIAMSSOManager` từ IP `14.245.185.195`, trực tiếp tạo bản sao TechX trong `default` bằng `kubectl.exe`.
2. Bản sao làm hỏng dependency chain và nhiễm telemetry vào năm SLO alert. Production `techx-tf4` vẫn khỏe trong thời gian kiểm tra.

### Giới hạn chưa thể kết luận

Bằng chứng hiện chưa cho biết:

- ý định của người vận hành;
- có change ticket hoặc approval hay không;
- câu lệnh shell đầy đủ;
- máy trạm có do chính người sở hữu session sử dụng hay do người khác dùng session đó.

Cần bổ sung IAM Identity Center sign-in/device log, EDR/endpoint correlation, Git/CI record và change-management evidence.

## 10. Việc audit cần làm tiếp

1. Lưu giữ toàn bộ EKS audit record của `04:44:57Z–04:48:34Z`, gồm `requestObject` và `responseObject`, vào kho evidence bất biến.
2. Đối chiếu session `quyet` và IP `14.245.185.195` với log IAM Identity Center, thiết bị và change đã phê duyệt.
3. Kiểm tra hoạt động Git/CI/CD trong cùng cửa sổ thời gian để xác định manifest được render/export/apply như thế nào.
4. Tìm bằng chứng phê duyệt việc deploy vào `default`; nếu không có, phân loại là hành động deploy sai phạm vi/chưa được phê duyệt.
5. Chỉ xóa hoặc cô lập workload bản sao qua change được phê duyệt; sau đó xác minh không còn telemetry từ `default` và alert đã resolved.
6. Sửa alert rule để bắt buộc `k8s_namespace_name="techx-tf4"`.
7. Thêm admission guardrail chặn TechX workload trong `default`.
8. Rà soát `LOCUST_AUTOSTART=true` ở cả hai namespace và bắt buộc test window có thời hạn rõ ràng.

## 11. Danh mục evidence

| Evidence ID | Nguồn / locator | Mục đích |
|---|---|---|
| `EKS-AUDIT-01` | CloudWatch `/aws/eks/techx-tf4-cluster/cluster`; lọc `objectRef.namespace=default`; `2026-07-20T04:40Z–05:00Z` | Quy trách nhiệm identity và API |
| `EKS-AUDIT-02` | Audit ID `c5827909-7e22-4052-98cd-3c80f6c1a4f8` | Bản ghi tạo `frontend` đại diện |
| `ARGO-01` | Log `argocd-application-controller`; application `techx-corp` | Đối chiếu namespace và loại trừ Argo |
| `K8S-LIVE-01` | Snapshot chỉ đọc của `default` và `techx-tf4` | So sánh runtime và phạm vi ảnh hưởng |
| `CLOUDTRAIL-01` | CloudTrail `LookupEvents`, user `quyet`, cùng cửa sổ | Đối chứng SSO |
| `CHAT-CONTEXT-01` | Ảnh chụp chat do người yêu cầu cung cấp | Chỉ bối cảnh, không phải bằng chứng định danh |

## Phụ lục A — Kết luận ngắn cho hồ sơ sự cố

Trong khoảng **11:44:57–11:48:34 ICT ngày 20/07/2026**, SSO session `quyet` (`TF4-SecurityIAMSSOManager`) dùng `kubectl.exe` từ `14.245.185.195` để apply workload TechX có Helm label vào namespace `default`. Bản sao thiếu PVC, ConfigMap và Secret bắt buộc, trong khi load-generator được autostart. Năm alert phản ánh lỗi thật của bản sao cộng với lỗ hổng tách namespace trong monitoring; chúng không chứng minh production khỏe trong `techx-tf4` đã chết toàn bộ.
