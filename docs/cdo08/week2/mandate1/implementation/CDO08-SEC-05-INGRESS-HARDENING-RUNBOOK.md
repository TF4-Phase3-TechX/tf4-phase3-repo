# CDO08-SEC-05 — Private operational portals

> **Đọc nhanh:** Storefront `/` phải tiếp tục public và trả `200 OK`. Grafana,
> Jaeger và Load Generator hiện đang truy cập được thật từ Internet nên phải được
> đưa về private. Các route `/feature`, `/flagservice/` và `/otlp-http/` cũng phải
> bị chặn trên public proxy dù hiện tại backend chỉ trả `503/404`. Phương án đề
> xuất là thêm explicit deny cho các route vận hành trên Envoy public và dùng
> **AWS SSO cá nhân → SSM Session Manager → Bastion private → `kubectl
> port-forward` trên Bastion → portal**. Phương án không cần SSH key, public IP,
> inbound port 22 hoặc internal ALB. CloudTrail ghi nhận phiên SSM; Kubernetes
> audit (nếu bật) ghi nhận API port-forward, nhưng không ghi nội dung HTTP/hành
> động trong portal. **Tài liệu này chưa phải phê
> duyệt triển khai; không được thay đổi runtime trước khi hoàn tất Approval gate.**

## 1. Trạng thái và quyết định cần đưa ra

**Trạng thái hiện tại: `RESEARCH COMPLETE — WAITING FOR APPROVAL`.**

- Đã xác nhận storefront public hoạt động bình thường.
- Đã xác nhận Grafana, Jaeger và Load Generator bị public exposure thật.
- Đã inventory các route operational/internal còn lại trong config và runtime.
- Chưa thay đổi ingress, frontend-proxy hoặc workload runtime.
- Quyết định cần approve: dùng **AWS SSO cá nhân → SSM → EC2 Bastion private →
  `kubectl port-forward` trên Bastion → portal**. Mỗi người dùng identity riêng;
  không dùng shared admin credential. Không cần SSH key, public IP, inbound port
  22 hoặc internal ALB. Chi phí chính là EC2 Bastion và logging/network liên quan,
  cần CDO04 xác nhận bằng AWS Pricing Calculator. Sau đó chặn tường minh sáu
  internal route trên public Envoy.

Luồng thực hiện để mọi bên cùng hiểu:

```text
Research/evidence (đã xong)
        ↓
Owner + Observability + Deploy Operator approve
        ↓
Kiểm tra private access cho Mentor/BTC
        ↓
Cắt internal routes khỏi public proxy
        ↓
Verify storefront + checkout + flagd + private access
        ↓
Attach evidence vào Jira và owner sign-off
```

## 2. Mục tiêu

- Owner: Nhân
- Pillar: Security
- Priority: P0 theo DIRECTIVE #1
- Storefront phải tiếp tục public.
- Mọi operational/internal portal phải private.
- Mentor/BTC và người có quyền phải có hướng dẫn truy cập private khi cần.
- Chỉ cắt public access sau khi phương án được owner và Deploy Operator approve.

## 3. Runtime evidence hiện tại

Thời điểm kiểm tra: `2026-07-13T09:33:09+07:00` (Asia/Bangkok).

Context:

```text
arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster
```

Public ALB:

```text
k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com
```

| Portal/route    | Backend runtime                       |                               Public result | Kết luận                                                          |
| --------------- | ------------------------------------- | ------------------------------------------: | ----------------------------------------------------------------- |
| Storefront `/`  | frontend                              |                                       `200` | Public đúng yêu cầu                                               |
| `/grafana/`     | Grafana đang chạy                     |                                       `200` | **Public exposure thật**                                          |
| `/jaeger/ui/`   | Jaeger đang chạy                      |                                       `200` | **Public exposure thật**                                          |
| `/loadgen/`     | Load Generator đang chạy              |                                       `200` | **Public exposure thật**                                          |
| `/feature`      | flagd-ui không có service/pod         |                                       `503` | Route public tồn tại, backend chưa chạy; chưa an toàn có chủ đích |
| `/flagservice/` | flagd đang chạy                       |                                       `404` | Route public tồn tại; backend trả 404, chưa phải access control   |
| `/otlp-http/`   | OTel Collector đang chạy              |                                       `404` | Route public tồn tại; backend trả 404, chưa phải access control   |
| Prometheus      | Service `ClusterIP:9090`              | Không có public route riêng trong inventory | Private ở lớp Service hiện tại                                    |
| OpenSearch      | Service `ClusterIP:9200/9300/9600`    | Không có public route riêng trong inventory | Private ở lớp Service hiện tại                                    |
| ArgoCD/CD UI    | Không có namespace/service/deploy/pod |                               Không tồn tại | Chưa deploy; phải private nếu xuất hiện sau này                   |

Nguồn cấu hình:

- `deploy/ingress.yaml`: ALB `internet-facing`, path `Prefix /` chuyển toàn bộ request vào `frontend-proxy:8080`.
- `techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml`: có route `/loadgen/`, `/jaeger/`, `/grafana/`, `/feature`, `/flagservice/`, `/otlp-http/`.

`503` hoặc `404` từ backend không chứng minh route private. Kết quả an toàn phải là route bị loại khỏi public proxy, bị policy chặn (`403`) hoặc bắt buộc auth (`401`).

## 4. Rủi ro

| Portal                | Rủi ro chính                                                                                       |
| --------------------- | -------------------------------------------------------------------------------------------------- |
| Grafana               | Lộ metrics/logs/dashboard và thông tin hạ tầng; có thể ảnh hưởng dashboard/alert tùy quyền runtime |
| Jaeger                | Lộ service topology, trace, lỗi và request attributes; có thể chứa dữ liệu nhạy cảm                |
| Load Generator        | Có thể bị dùng để tạo tải, làm tụt SLO và gián đoạn checkout                                       |
| flagd-ui/flagd        | Có thể tác động feature/fault flags; không được đụng hoặc vô hiệu hóa OpenFeature hooks            |
| OTLP                  | Có thể nhận telemetry giả/rác, gây tải và làm nhiễu evidence                                       |
| Prometheus/OpenSearch | Lộ metrics/logs nếu bị tạo public route trong tương lai                                            |
| ArgoCD/CD UI          | Nếu xuất hiện và public, có thể lộ hoặc thay đổi deployment/control plane                          |

## 5. So sánh private-access

| Phương án                   | Chi phí/tuần | Audit trail               | Quản lý quyền                                            | Rủi ro storefront | Rollback   |
| --------------------------- | ------------ | ------------------------- | -------------------------------------------------------- | ----------------- | ---------- |
| Laptop chạy `kubectl port-forward` trực tiếp | $0 | API/session-level nếu EKS audit bật; không có application-level audit | Phải cấp kubeconfig/RBAC trực tiếp cho từng người | Rất thấp | Dễ |
| SSH Bastion (port 22)       | ~$3–5        | ✅ sshd log               | ❌ Phải quản lý SSH key + whitelist IP thay đổi liên tục | Thấp              | Dễ         |
| **SSM Bastion + `kubectl port-forward`** | **EC2 + log/network** | **CloudTrail + SSM shell log + EKS API audit; không có application-level audit** | **AWS SSO cá nhân + SSM IAM + Bastion EKS RBAC** | Thấp | Dễ |
| VPN                         | ~$0–20       | 🔶 Tuỳ server             | Phức tạp                                                 | Thấp              | Trung bình |

### Lý do chọn SSM thay vì SSH Bastion

- **SSH Bastion:** IP người dùng thay đổi liên tục → phải sửa Security Group tay. Cấp key mới cho từng người → phải generate + gửi key an toàn. Mentor mới → lại làm lại từ đầu.
- **SSM:** Quyền = IAM role/policy. Thêm người mới → attach policy 1 lệnh. IP không quan trọng vì kết nối qua HTTPS. Không mở port 22.
- **Mentor/BTC dùng AWS SSO identity cá nhân** → CloudTrail truy vết được người mở phiên; không dùng shared admin credential.

### Vì sao không cho Mentor/BTC port-forward trực tiếp từ laptop?

- Phải cấp kubeconfig và Kubernetes RBAC trực tiếp cho từng người.
- Khó tạo một access path thống nhất khi môi trường máy và network khác nhau.
- SSM Bastion tạo điểm vào private tập trung và CloudTrail ghi danh tính mở phiên.
- `kubectl port-forward` vẫn được dùng, nhưng chạy trên Bastion bằng EKS role giới hạn.
- Đóng session/process thì private access mất; đây là hành vi fail-closed mong muốn.

## 6. Phương án đề xuất cho TF4

**Phương án chọn: AWS SSO cá nhân → SSM Session Manager → EC2 Bastion private → `kubectl port-forward` trên Bastion → portal.**

### 6.1 Tại sao chọn SSM?

**Chi phí (cho CDO04 duyệt):**

| Item | Chi phí ước tính |
|---|---|
| EC2 Bastion `t3.nano` | `$0.0052/giờ`; baseline 8 giờ/tuần = `$0.0416/tuần` |
| EBS gp3 mã hóa 8 GiB | Khoảng `$0.148/tuần`; EBS vẫn phát sinh phí khi EC2 dừng |
| SSM Session Manager | Không có phí riêng cho tính năng Session Manager |
| CloudWatch/S3 session log | Theo dung lượng và retention |
| NAT Gateway hiện có | Không tính thêm fixed hourly cost cho SEC-05; cộng khoảng `$0.045/GB` data processing, chưa gồm data transfer/cross-AZ nếu có |
| SSM VPC endpoints mới | **Không tạo**; 3 endpoint × 1 AZ × 168 giờ × `$0.01` ≈ `$5.04/tuần`, chưa gồm data |
| Internal ALB | **Không sử dụng trong phương án này** |
| **Fixed cost phương án chọn** | **Khoảng `$0.19/tuần` ở baseline 8 giờ; `$0.36/tuần` nếu chạy 40 giờ; tối đa khoảng `$1.02/tuần` nếu chạy 24x7. Chưa gồm NAT data, logging, data transfer và thuế.** |

**Kết luận cost:** chọn `t3.nano` scheduled/on-demand + EBS gp3 8 GiB + NAT hiện có. Đây là phương án rẻ nhất phù hợp thiết kế SSM; không tạo Internal ALB hoặc SSM VPC Endpoint mới. Vì `t3.nano` chỉ có 0.5 GiB RAM, Infra phải pilot SSM Agent + AWS CLI + `kubectl`; nếu cần tăng instance size thì phải gửi CDO04 review lại.

**Audit trail (cho CDO07 duyệt):**

CloudTrail ghi API mở/kết thúc session SSM:

```
EventName:    StartSession
UserIdentity: arn:aws:iam::511825856493:user/nhan
EventTime:    2026-07-14T10:30:00Z
SourceIPAddress: 1.2.3.4
RequestParameters:
  target: i-0abc123def456
  target: i-0abc123def456
```

CloudTrail cho biết **ai mở phiên, lúc nào, từ IP nào và vào Bastion nào**. SSM
shell logging (nếu bật) có thể ghi lệnh `kubectl port-forward`; EKS audit logging
(nếu bật) có thể ghi API port-forward do Bastion role gọi. Các lớp này **không ghi
nội dung HTTP hoặc hành động bên trong portal**. Đây là residual risk cần owner và
Tech Lead chấp nhận vì Acceptance Criteria hiện không yêu cầu application-level audit.

### 6.2 Kiến trúc

```
Internet
  │
  │  ❌ /grafana/, /jaeger/, /loadgen/ → 404 (Envoy block)
  │  ✅ /  → storefront (giữ nguyên)
  ▼
Public ALB → Envoy proxy


Mentor/BTC (AWS SSO identity cá nhân)
  │
  │  HTTPS — không cần port 22, không cần whitelist IP
  ▼
AWS SSM Endpoint
  │
  │  SSM Agent (chạy trong EC2 Bastion, private subnet)
  ▼
EC2 Bastion
  │  kubeconfig + EKS access entry/RBAC giới hạn
  │  kubectl port-forward bind 127.0.0.1
  ▼
Grafana / Jaeger / Loadgen (Kubernetes Service)


Team nội bộ (AWS SSO identity cá nhân)
  → Tương tự, chỉ có quyền mở session vào đúng Bastion
```

### 6.3 Các bước thực hiện

**Bước 1 — Envoy block public routes:**

```yaml
# envoy.tmpl.yaml — đặt trước catch-all /
- match: { path: "/grafana" }
  direct_response: { status: 404 }
- match: { prefix: "/grafana/" }
  direct_response: { status: 404 }
# tương tự: /jaeger/, /loadgen/, /feature, /flagservice/, /otlp-http/
```

**Bước 2 — Launch EC2 Bastion (private subnet, SSM role):**

- Quản lý bằng Terraform sau Infra review; không chạy trực tiếp lệnh `run-instances` mẫu.
- Private subnet, không public IP, Security Group không có inbound, không mở port 22.
- Bắt buộc IMDSv2, encrypted EBS, SSM Agent, patch baseline và instance profile tối thiểu.
- Bastion cần AWS CLI, `kubectl` và network đến EKS API; phương án chọn dùng **single NAT Gateway hiện có**, không tạo SSM VPC Endpoint mới.
- Tạo EKS Access Entry cho **Bastion instance role**, không dùng admin credential.
- Kubernetes RBAC chỉ cho `get/list` Service/Pod cần thiết và `create` trên `pods/portforward` trong `techx-tf4`, `techx-observability`.

**Bước 3 — Cấp quyền cho Mentor/BTC và team:**

- Mỗi người dùng AWS IAM Identity Center/SSO identity cá nhân; không dùng shared admin credential hoặc long-lived access key.
- Permission Set chỉ cho phép mở SSM session đến đúng Bastion và dùng đúng session documents.
- Người dùng không cần kubeconfig/EKS RBAC trên laptop; chỉ Bastion instance role có Kubernetes permission tối thiểu.
- IAM/SSO được quản lý bằng Terraform hoặc quy trình IAM được approve; không dùng `put-user-policy` thủ công.

**Bước 4 — Hướng dẫn truy cập hai lớp:**

Baseline port mapping phục vụ đối soát CDO07:

| Bastion loopback port | Kubernetes target | Source/runtime mapping |
|---:|---|---|
| `13000` | `techx-observability/svc/grafana:80` | `kubectl ... svc/grafana 13000:80` |
| `16686` | `techx-observability/svc/jaeger:16686` | `kubectl ... svc/jaeger 16686:16686` |
| `18089` | `techx-tf4/svc/load-generator:8089` | `kubectl ... svc/load-generator 18089:8089` |

Mapping này là audit baseline trong source control. Không đổi/reuse port cho service
khác nếu chưa cập nhật PR, runbook và CDO07 mapping evidence. Thiết kế hiện hỗ trợ
một active port-forward trên mỗi portal; nhu cầu concurrent session phải được
review và cấp port range cố định riêng.

Ví dụ Grafana:

```bash
# Laptop — login bằng SSO identity cá nhân.
aws sso login --profile <mentor-btc-profile>

# Terminal A — mở SSM shell vào Bastion.
aws ssm start-session \
  --profile <mentor-btc-profile> \
  --target <BASTION_INSTANCE_ID>

# Chạy bên trong Bastion và giữ process mở.
kubectl -n techx-observability port-forward \
  --address 127.0.0.1 svc/grafana 13000:80

# Terminal B trên laptop — chuyển localhost đến port vừa mở trên Bastion.
aws ssm start-session \
  --profile <mentor-btc-profile> \
  --target <BASTION_INSTANCE_ID> \
  --document-name AWS-StartPortForwardingSession \
  --parameters 'portNumber=["13000"],localPortNumber=["3000"]'

# Mở http://127.0.0.1:3000/grafana/
```

Thay lệnh Terminal A cho portal khác:

```bash
# Jaeger; Terminal B forward Bastion port 16686 về local 16686.
kubectl -n techx-observability port-forward \
  --address 127.0.0.1 svc/jaeger 16686:16686
aws ssm start-session \
  --profile <mentor-btc-profile> --target <BASTION_INSTANCE_ID> \
  --document-name AWS-StartPortForwardingSession \
  --parameters 'portNumber=["16686"],localPortNumber=["16686"]'
# Mở http://127.0.0.1:16686/jaeger/ui/

# Loadgen; Terminal B forward Bastion port 18089 về local 8089.
kubectl -n techx-tf4 port-forward \
  --address 127.0.0.1 svc/load-generator 18089:8089
aws ssm start-session \
  --profile <mentor-btc-profile> --target <BASTION_INSTANCE_ID> \
  --document-name AWS-StartPortForwardingSession \
  --parameters 'portNumber=["18089"],localPortNumber=["8089"]'
# Mở http://127.0.0.1:8089/
```

Khi đóng Terminal A hoặc B, private access dừng. Không chạy port-forward bằng
`0.0.0.0`, `nohup` hoặc service persistent nếu chưa có review riêng.

**Bước 5 — Verify audit trail (CDO07):**

```bash
# Query CloudTrail — xem ai đã start session
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --start-time 2026-07-14T00:00:00Z
```

`/otlp-http/` có thể được frontend browser dùng để gửi telemetry. Trước khi chặn,
Observability owner phải xác nhận endpoint thay thế hoặc xác nhận browser telemetry
này không bắt buộc. Sau thay đổi phải kiểm tra telemetry server-side và checkout
SLO vẫn bình thường. Backend hiện trả `404` không đủ để kết luận route không được dùng.

OpenSearch và flagd không nên hướng dẫn truy cập trực tiếp cho người không có nhiệm vụ quản trị tương ứng.

## 7. Approval gate

Trước khi sửa/deploy, phải có:

**Technical sign-off:**

- [ ] Nhân approve danh sách 6 route cần cắt (`/grafana`, `/jaeger`, `/loadgen`, `/feature`, `/flagservice`, `/otlp-http`).
- [ ] Quyết (Observability owner) xác nhận Grafana/Jaeger dùng được qua SSM tunnel và xác nhận cách xử lý `/otlp-http` không làm mất telemetry bắt buộc.
- [ ] flagd/OpenFeature owner xác nhận chỉ bỏ public route, không thay hook/service/config.
- [ ] Deploy Operator ghi release hiện tại, image tag, deploy window và rollback revision.

**Phương án private access:**

- [ ] Mentor/BTC xác nhận AWS SSO identity cá nhân đã được cấp quyền vào đúng Bastion và test tunnel hai lớp thành công.
- [ ] Bastion instance role có EKS Access Entry/RBAC tối thiểu và không có `cluster-admin`.
- [ ] Team nội bộ xác nhận Permission Set giới hạn đã được cấp và test thành công.

**CDO04 — `APPROVED WITH CONDITIONS`:**

- [x] CDO04 đồng ý phương án SSM Bastion về mặt budget.
- [x] Dùng single NAT Gateway hiện có; không tạo SSM VPC Endpoint mới.
- [x] Chọn `t3.nano`, EBS gp3 mã hóa 8 GiB và scheduled/on-demand với baseline 8 giờ/tuần; 24x7 chỉ là kịch bản chi phí cao nhất.
- [ ] Chốt CloudWatch/S3 session logging và retention trước deploy.
- [ ] Projected total weekly TF cost vẫn `<= $300` trước deploy.
- [ ] Không tăng instance size ngoài proposal nếu chưa được CDO04 review lại.
- [ ] Sau deploy attach Cost Explorer actual cost và giải thích variance so với estimate.

Projected fixed incremental cost của phương án chọn là khoảng `$0.19/tuần` ở baseline 8 giờ, hoặc `$1.02/tuần` nếu chạy 24x7. Mức `$3.7–$3.9/tuần` trong comment CDO04 được giữ làm **budget ceiling**, không dùng làm projected cost; các số trên chưa gồm NAT data, logging, data transfer và thuế.

**CDO07 — Audit review:**
- [ ] CDO07 xác nhận CloudTrail đang bật và ghi được `StartSession` event với đủ: user ARN, timestamp, source IP.
- [ ] CDO07 chấp nhận fixed Bastion port baseline: `13000=Grafana`, `16686=Jaeger`, `18089=Loadgen`.
- [ ] CDO07 xác nhận SSM shell logging và EKS audit logging có/không được bật.
- [ ] CDO07 xác minh CloudTrail S3 bucket thực tế, retention/delete control và mức immutability; S3 Versioning một mình không được gọi là WORM.
- [ ] Owner/Tech Lead chấp nhận residual risk: audit được identity/session/API port-forward nhưng không audit đầy đủ hành động HTTP trong portal.

## 8. Thực hiện sau approval

File dự kiến thay đổi:

```text
techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml
```

Thay các route proxy nội bộ đã approve bằng explicit deny và giữ catch-all storefront `/` ở cuối. Cluster Envoy không còn được route tới có thể để lại trong thay đổi đầu tiên nhằm giảm blast radius; dọn cluster là bước riêng sau khi verify. Build image tag bất biến, chạy Envoy config validation, deploy canary nếu có và theo dõi rollout. Không thay `deploy/ingress.yaml` nếu storefront vẫn dùng cùng public ALB.

Ví dụ nguyên tắc cấu hình (cần validate bằng đúng Envoy version của image):

```yaml
# Đặt trước route prefix "/" của storefront.
- match: { path: "/grafana" }
  direct_response: { status: 404 }
- match: { prefix: "/grafana/" }
  direct_response: { status: 404 }
```

Áp dụng tương tự cho path trần và subpath của Jaeger, Loadgen, Feature,
Flagservice và OTLP HTTP. Không redirect path trần sang portal nữa.

## 9. Verification bắt buộc

```bash
export ALB="http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"
date -Iseconds
kubectl -n techx-tf4 get ingress,svc,pod -o wide
kubectl -n techx-observability get svc,pod -o wide

curl -I "$ALB/"
curl -I "$ALB/grafana/"
curl -I "$ALB/jaeger/ui/"
curl -I "$ALB/loadgen/"
curl -I "$ALB/feature"
curl -I "$ALB/flagservice/"
curl -I "$ALB/otlp-http/"

# GET check tránh phụ thuộc việc backend có hỗ trợ HEAD hay không.
for path in grafana/ jaeger/ui/ loadgen/ feature flagservice/ otlp-http/; do
  curl -sS -o /dev/null -w "$path -> %{http_code} %{redirect_url}\n" "$ALB/$path"
done
```

Pass khi:

- [ ] Storefront `/` trả `200 OK`.
- [ ] Checkout smoke test pass và không làm tụt checkout SLO.
- [ ] Cả path trần và subpath của sáu internal routes không trả portal, không bị catch-all trả storefront SPA, không redirect vào portal và không WebSocket upgrade; mong đợi explicit public `404` hoặc policy `401/403`.
- [ ] Grafana/Jaeger/Loadgen truy cập được bằng AWS SSO → SSM → Bastion → `kubectl port-forward` khi Mentor/BTC cần.
- [ ] CloudTrail evidence xác nhận identity và thời gian mở/kết thúc SSM session; không tuyên bố đây là application-level audit.
- [ ] flagd pod vẫn Ready; ứng dụng vẫn dùng OpenFeature hooks bình thường.
- [ ] Có command output và screenshot trước/sau kèm timestamp; không chứa token/cookie/PII.

Checkout smoke test phải dùng quy trình hiện có của team. Không tạo giao dịch thật nếu test environment không có cơ chế cleanup/idempotency được approve.

## 10. Rollback

Rollback khi storefront không trả 200, checkout smoke test fail, SLO giảm, Envoy lỗi hoặc flagd/OpenFeature bị ảnh hưởng:

```bash
kubectl -n techx-tf4 rollout undo deployment/frontend-proxy
kubectl -n techx-tf4 rollout status deployment/frontend-proxy --timeout=5m
```

Nếu release do Helm quản lý, dùng `helm rollback <release> <previous-revision> --wait`. Sau rollback phải test lại storefront và checkout. Không expose lại operational portals public mặc định; nếu image cũ làm route public trở lại, áp dụng mitigation đã approve hoặc sửa forward thay vì chấp nhận exposure.

## 11. Definition of Done

- [ ] Runtime inventory và pre/post curl có timestamp được attach Jira.
- [ ] Storefront public `/` vẫn `200`; checkout smoke test pass, SLO không giảm.
- [ ] Grafana, Jaeger, Loadgen, feature, flagservice và OTLP không truy cập được từ public Internet.
- [ ] Mentor/BTC có hướng dẫn private access đã được kiểm chứng.
- [ ] flagd/OpenFeature hooks không bị thay đổi hoặc vô hiệu hóa.
- [ ] Rollback revision/image và kết quả rollback test được ghi lại.
- [ ] Nhân xác nhận Acceptance Criteria; PM cập nhật backlog.

## 12. Evidence cần attach vào Jira

Để reviewer không phải suy luận từ nhiều nguồn, gói evidence cuối cùng nên có:

1. **Before:** timestamp, public ALB, `kubectl get ingress,svc,pod` và kết quả
   `curl` cho storefront cùng sáu internal paths.
2. **Approval:** comment hoặc link xác nhận của Nhân, Quyết, flagd/OpenFeature
   owner, Mentor/BTC, Deploy Operator, CDO04 (Cost) và CDO07 (Audit).
3. **Change:** commit, image tag/release revision và danh sách chính xác các route
   đã bỏ; không đưa token, cookie hoặc credential vào evidence.
4. **After:** timestamp, cùng bộ lệnh `curl`, storefront `200`, checkout smoke
   test pass, flagd Ready và OpenFeature hooks hoạt động.
5. **Private access:** screenshot hoặc command output chứng minh người có quyền
   truy cập được Grafana/Jaeger/Loadgen qua runbook private.
6. **Rollback:** previous revision/image, lệnh rollback và điều kiện kích hoạt.

### Kết luận ngắn để cập nhật Jira

> Runtime evidence xác nhận Grafana, Jaeger và Load Generator đang public qua
> internet-facing ALB. Các route feature, flagservice và OTLP cũng tồn tại trên
> public proxy dù backend hiện trả lỗi. Đề xuất chặn tường minh toàn bộ
> operational/internal route trên public Envoy, giữ nguyên storefront, và cấp
> private access cho Mentor/BTC theo luồng: AWS SSO identity cá nhân → SSM Session
> Manager → EC2 Bastion private không mở SSH/public IP → `kubectl port-forward`
> chạy trên Bastion → operational portal. CloudTrail dùng để truy vết người mở
> phiên SSM; SSM shell/EKS audit (nếu bật) ghi nhận lệnh/API port-forward nhưng
> không ghi đầy đủ hành động HTTP trong portal. Hạn chế này được ghi nhận là
> residual risk cần owner/Tech Lead approve. Phương án không tạo internal ALB.
> Chưa triển khai cho đến khi phương án, chi phí, IAM/RBAC, network và rollback
> được các owner liên quan approve. Sau thay đổi phải chứng minh storefront vẫn
> trả `200`, checkout smoke test pass và SLO không giảm, flagd/OpenFeature không
> bị thay đổi hoặc vô hiệu hóa, các internal path không còn public, đồng thời
> Mentor/BTC truy cập private thành công bằng danh tính cá nhân.
