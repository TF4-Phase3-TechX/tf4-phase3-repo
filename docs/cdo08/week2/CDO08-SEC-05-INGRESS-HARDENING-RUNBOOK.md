# CDO08-SEC-05 — Private operational portals

> **Đọc nhanh:** Storefront `/` phải tiếp tục public và trả `200 OK`. Grafana,
> Jaeger và Load Generator hiện đang truy cập được thật từ Internet nên phải được
> đưa về private. Các route `/feature`, `/flagservice/` và `/otlp-http/` cũng phải
> bị chặn trên public proxy dù hiện tại backend chỉ trả `503/404`. Phương án đề
> xuất là thêm explicit deny cho các route vận hành trên Envoy public và dùng
> **AWS SSM Session Manager** làm tunnel private access — không cần SSH key, không
> cần whitelist IP, audit trail tự động qua CloudTrail. BTC dùng admin credential
> có sẵn; team nội bộ dùng IAM read-only role. **Tài liệu này chưa phải phê
> duyệt triển khai; không được thay đổi runtime trước khi hoàn tất Approval gate.**

## 1. Trạng thái và quyết định cần đưa ra

**Trạng thái hiện tại: `RESEARCH COMPLETE — WAITING FOR APPROVAL`.**

- Đã xác nhận storefront public hoạt động bình thường.
- Đã xác nhận Grafana, Jaeger và Load Generator bị public exposure thật.
- Đã inventory các route operational/internal còn lại trong config và runtime.
- Chưa thay đổi ingress, frontend-proxy hoặc workload runtime.
- Quyết định cần approve: dùng **AWS SSM Session Manager qua EC2 Bastion** làm private access
  — BTC dùng admin credential có sẵn, team nội bộ dùng IAM read-only role.
  Không cần SSH key, không cần whitelist IP, audit trail tự động qua CloudTrail.
  Chi phí ~$3.5/tuần (EC2 t3.nano). Sau đó chặn tường minh sáu internal route trên public Envoy.

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
| `kubectl port-forward`      | $0           | ❌ Không có               | Cần kubeconfig + đúng role                               | Rất thấp          | Dễ         |
| SSH Bastion (port 22)       | ~$3–5        | ✅ sshd log               | ❌ Phải quản lý SSH key + whitelist IP thay đổi liên tục | Thấp              | Dễ         |
| **AWS SSM Session Manager** | **~$3–5**    | **✅ CloudTrail tự động** | **✅ IAM role — không cần key, không cần whitelist IP**  | Thấp              | Dễ         |
| VPN                         | ~$0–20       | 🔶 Tuỳ server             | Phức tạp                                                 | Thấp              | Trung bình |
| Internal ALB                | +$20         | 🔶 ALB log                | Cần thêm đường vào VPC                                   | Thấp              | Trung bình |

### Lý do chọn SSM thay vì SSH Bastion

- **SSH Bastion:** IP người dùng thay đổi liên tục → phải sửa Security Group tay. Cấp key mới cho từng người → phải generate + gửi key an toàn. Mentor mới → lại làm lại từ đầu.
- **SSM:** Quyền = IAM role/policy. Thêm người mới → attach policy 1 lệnh. IP không quan trọng vì kết nối qua HTTPS. Không mở port 22.
- **BTC đã có admin credential** → họ dùng SSM ngay, không cần setup gì thêm.

### Lý do loại `kubectl port-forward`

- **Không audit được:** Không có log nào ghi lại ai đã vào Grafana/Jaeger lúc nào.
- **Không dùng chung:** Port bind vào local machine — nhiều người không thể vào cùng lúc.
- **Không persistent:** Đóng terminal là mất access.

## 6. Phương án đề xuất cho TF4

**Phương án chọn: AWS SSM Session Manager qua EC2 Bastion** — không cần SSH key, không cần whitelist IP.

### 6.1 Tại sao chọn SSM?

**Chi phí (cho CDO04 duyệt):**

| Item                                                | Chi phí ước tính                               |
| --------------------------------------------------- | ---------------------------------------------- |
| EC2 `t3.nano` chạy bastion                          | ~$3.5/tuần                                     |
| SSM Session Manager                                 | $0 (built-in AWS)                              |
| Không cần VPN gateway, ALB thêm, hay manage SSH key | $0                                             |
| **Tổng thêm**                                       | **~$3.5/tuần** — nằm trong ngân sách $300/tuần |

So sánh: VPN ~$20/tuần, Internal ALB ~$20/tuần, SSH Bastion tương đương nhưng tốn công quản lý key + SG.

**Audit trail (cho CDO07 duyệt):**

Mọi session SSM đều được ghi tự động vào **AWS CloudTrail**:

```
EventName:    StartSession
UserIdentity: arn:aws:iam::511825856493:user/nhan
EventTime:    2026-07-14T10:30:00Z
SourceIPAddress: 1.2.3.4
RequestParameters:
  target: i-0abc123def456
  portNumber: 80   ← Grafana
```

CDO07 query CloudTrail → biết ngay **ai vào, lúc nào, từ IP nào, vào service nào**.

### 6.2 Kiến trúc

```
Internet
  │
  │  ❌ /grafana/, /jaeger/, /loadgen/ → 404 (Envoy block)
  │  ✅ /  → storefront (giữ nguyên)
  ▼
Public ALB → Envoy proxy


BTC (admin credential có sẵn)
  │
  │  HTTPS — không cần port 22, không cần whitelist IP
  ▼
AWS SSM Endpoint
  │
  │  SSM Agent (chạy trong EC2 Bastion, private subnet)
  ▼
EC2 Bastion → tunnel → Grafana / Jaeger / Loadgen (ClusterIP, chỉ trong VPC)


Team nội bộ (IAM read-only role)
  → Tương tự, nhưng chỉ có quyền StartSession vào bastion instance này
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

```bash
# IAM role cho EC2: AmazonSSMManagedInstanceCore
# Không cần mở port 22, không cần public IP cho bastion
aws ec2 run-instances \
  --image-id ami-0c02fb55956c7d316 \
  --instance-type t3.nano \
  --iam-instance-profile Name=SSMInstanceProfile \
  --subnet-id subnet-private-xxxx \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=techx-tf4-bastion}]'

# Security Group bastion: KHÔNG cần mở port nào từ internet
# Security Group Grafana/Jaeger/Loadgen: inbound chỉ từ bastion SG
```

**Bước 3 — Cấp quyền cho team nội bộ (không phải BTC):**

```bash
# BTC đã có admin → không cần làm gì thêm

# Team nội bộ: tạo IAM policy chỉ cho phép StartSession vào đúng bastion
aws iam put-user-policy \
  --user-name nhan \
  --policy-name SSMBastionReadOnly \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["ssm:StartSession", "ssm:TerminateSession"],
      "Resource": "arn:aws:ec2:*:*:instance/<bastion-instance-id>"
    }]
  }'
```

**Bước 4 — Hướng dẫn truy cập (BTC và team nội bộ dùng chung cách này):**

```bash
# Cài Session Manager plugin (1 lần)
brew install --cask session-manager-plugin   # macOS
# hoặc: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html

# Login (BTC dùng admin profile, team dùng profile của mình)
aws sso login --profile tf4-readonly

# Tunnel vào Grafana
aws ssm start-session \
  --target i-<bastion-instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<grafana-clusterip>"],"portNumber":["80"],"localPortNumber":["3000"]}'
# → Mở http://localhost:3000

# Tunnel vào Jaeger
aws ssm start-session \
  --target i-<bastion-instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<jaeger-clusterip>"],"portNumber":["16686"],"localPortNumber":["16686"]}'
# → Mở http://localhost:16686

# Tunnel vào Loadgen
aws ssm start-session \
  --target i-<bastion-instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<loadgen-clusterip>"],"portNumber":["8089"],"localPortNumber":["8089"]}'
# → Mở http://localhost:8089
```

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

- [ ] BTC xác nhận đã test SSM tunnel thành công với admin credential (instance-id đã được cung cấp).
- [ ] Team nội bộ xác nhận IAM read-only role đã được cấp và test tunnel thành công.

**CDO04 — Cost review:**

- [ ] CDO04 xác nhận EC2 `t3.nano` (~$3.5/tuần) nằm trong ngân sách $300/tuần.
- [ ] CDO04 xác nhận SSM rẻ hơn SSH Bastion (tương đương cost EC2 nhưng không tốn công vận hành key/SG), VPN ~$20/tuần, Internal ALB ~$20/tuần.

**CDO07 — Audit review:**
- [ ] CDO07 xác nhận CloudTrail đang bật và ghi được `StartSession` event với đủ: user ARN, timestamp, source IP.
- [ ] CDO07 xác nhận audit trail đáp ứng trụ Auditability: ai vào, lúc nào, từ đâu.

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
- [ ] Grafana/Jaeger/Loadgen truy cập được theo private runbook khi Mentor/BTC cần.
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
> public proxy dù backend hiện trả lỗi. Đề xuất chặn tường minh toàn bộ operational/internal
> route trên public Envoy, giữ nguyên storefront, và dùng AWS SSO + kubectl
> port-forward làm đường truy cập private tạm thời cho Mentor/BTC. Chưa triển khai
> cho đến khi đủ approval. Sau thay đổi phải chứng minh storefront 200, checkout
> pass, flagd/OpenFeature không bị ảnh hưởng và các internal path không còn public.
