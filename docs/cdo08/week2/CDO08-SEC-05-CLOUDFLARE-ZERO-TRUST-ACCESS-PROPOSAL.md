# CDO08-SEC-05 - Proposal thay SSM-only access bằng Cloudflare Zero Trust

## 1. Bối cảnh

Mandate 01 yêu cầu storefront vẫn public, nhưng các cổng vận hành như Grafana, Jaeger, Load Generator, dashboard/log/metric/trace UI và mọi control-plane nội bộ phải private. Hiện CDO08 đã xử lý phần public exposure bằng cách chặn các route vận hành trên public `frontend-proxy`, đồng thời dùng AWS SSO -> SSM Session Manager -> Bastion -> port-forward làm đường truy cập riêng tư tạm thời.

Phương án SSM đạt yêu cầu bảo mật tối thiểu vì không expose portal ra public internet và có AWS identity/audit trail. Tuy nhiên về vận hành nó còn nặng: mentor/team phải có AWS account, cài Session Manager plugin, chạy lệnh SSM port-forward theo port, session hết thì phải chạy lại. Mentor đã góp ý cần đưa vào backlog một phương án dễ vận hành hơn, ví dụ OpenVPN, Tailscale, NetBird hoặc Cloudflare Zero Trust.

Lưu ý tên gọi: phương án được đề xuất ở đây là **Cloudflare Zero Trust + Cloudflare Tunnel + Access**, không phải AWS CloudFront. CloudFront là CDN/public edge, muốn bảo vệ portal nội bộ sẽ phải tự ghép thêm Cognito/Lambda@Edge/WAF/origin protection và vẫn không tự nhiên giải quyết bài toán private operational access như Cloudflare Tunnel.

## 2. Mục tiêu bổ sung cho SEC-05

Thay SSM-only access bằng một đường truy cập vận hành dễ dùng hơn:

- Mentor/team vào được Grafana, Jaeger, Load Generator bằng domain dễ nhớ.
- Không cần mở lại `/grafana`, `/jaeger`, `/loadgen` trên public ALB storefront.
- Không cần SSH key, không cần whitelist IP cá nhân, không cần cấp kubeconfig cho mentor.
- Có lớp authentication/authorization trước portal.
- Có audit log ở lớp access.
- Giữ SSM Bastion làm break-glass/fallback trong thời gian chuyển đổi.

## 3. Các phương án đã research

### 3.1 Giữ nguyên SSM Session Manager

SSM hiện đã hoạt động và phù hợp làm giải pháp khẩn cấp. Ưu điểm là dùng AWS IAM/SSO cá nhân, không cần mở inbound port, có CloudTrail cho `StartSession`, chi phí thấp nếu Bastion chạy theo lịch.

Điểm yếu là trải nghiệm vận hành kém. Người dùng phải có AWS account/profile, cài plugin, nhớ instance ID, chạy lệnh port-forward, giữ terminal mở và dùng `localhost`. Với mentor hoặc team khác chỉ cần xem dashboard, flow này quá nhiều bước.

Kết luận: giữ làm fallback, không nên là primary access path.

### 3.2 OpenVPN

OpenVPN là phương án VPN truyền thống, dễ hiểu với mô hình private network. Người dùng cài client, connect VPN rồi truy cập private endpoint.

Tradeoff:

- Cần vận hành VPN server hoặc dùng CloudConnexa.
- Phải quản lý user, profile, network route, DNS, revoke access.
- Cần thêm hạ tầng/networking và runbook vận hành.
- Phù hợp nếu cả TF cần private network rộng, nhưng hơi nặng nếu mục tiêu ngắn hạn chỉ là web portal như Grafana/Jaeger.

Kết luận: không chọn làm phương án đầu tiên cho TF4 vì setup/ops overhead lớn hơn nhu cầu hiện tại.

### 3.3 Tailscale

Tailscale có Kubernetes Operator và tailnet identity-based access. Theo tài liệu Tailscale, Kubernetes Operator có thể expose workloads trong cluster vào tailnet, hỗ trợ private Kubernetes API access, ingress/egress và audit/session recording tùy cấu hình.

Tradeoff:

- Rất tốt nếu team chấp nhận cài Tailscale client và dùng tailnet lâu dài.
- Phù hợp với private network/dev access, không expose public.
- Nhưng mentor/team ngoài phải join tailnet hoặc được mời vào tailnet.
- Domain access có thể làm được, nhưng người dùng vẫn cần client/tailnet membership.

Kết luận: tốt cho platform dài hạn, nhưng chưa tối ưu nếu yêu cầu của mentor là vào bằng domain/browser càng ít bước càng tốt.

### 3.4 NetBird

NetBird cũng là mesh VPN/Zero Trust network, có IdP, policy, route và remote network access. Theo tài liệu onboarding của NetBird, có thể tạo peer/routing peer để truy cập private network/resource.

Tradeoff:

- Tương tự Tailscale, phù hợp nếu muốn private network cho nhiều loại tài nguyên.
- Người dùng thường cần client hoặc enrollment vào network.
- Cần thêm thiết kế route/policy và vận hành peer/gateway.
- Ít trực tiếp hơn Cloudflare Access cho bài toán web portal theo domain.

Kết luận: là lựa chọn thay thế tốt nếu TF muốn mesh VPN, nhưng không phải option nhanh nhất cho web-only operational portals.

### 3.5 AWS CloudFront

CloudFront là CDN/public edge của AWS. Có thể dùng CloudFront trước portal, ghép thêm Cognito/Lambda@Edge hoặc signed URL/cookie để thêm authentication.

Tradeoff:

- Endpoint vẫn là public internet endpoint.
- Phải tự thiết kế authentication, authorization, header validation, origin protection.
- Nếu origin là internal service trong EKS, cần thêm ALB/NLB hoặc route public/private phức tạp.
- Không giải quyết tự nhiên yêu cầu "mọi cổng vận hành phải riêng tư" nếu chỉ đặt CloudFront trước portal.

Kết luận: không chọn. CloudFront phù hợp phân phối public content/API hơn là private operational portal access.

### 3.6 Cloudflare Zero Trust + Cloudflare Tunnel + Access

Cloudflare Tunnel cho phép `cloudflared` chạy trong hạ tầng và tạo kết nối outbound-only tới Cloudflare, không cần public routable IP cho origin. Cloudflare Access có thể đặt lớp authentication/authorization trước self-hosted application, policy mặc định deny nếu user không match Allow policy.

Tradeoff:

- Cần domain trên Cloudflare hoặc partial CNAME setup.
- Cần quản lý Cloudflare account, Access policy và tunnel token/credential.
- Đây là SaaS bên thứ ba, cần cân nhắc ownership và account admin.
- Cần deploy `cloudflared` trong cluster hoặc trên Bastion/private subnet.

Ưu điểm:

- Mentor vào bằng domain như `grafana.<domain>`, `jaeger.<domain>`, `loadgen.<domain>`.
- Không cần AWS account cho người chỉ xem portal.
- Không cần port-forward thủ công.
- Không cần mở public ALB cho portal nội bộ.
- Cloudflare Access cung cấp auth, policy, session duration và access logs.
- Tunnel là outbound-only, origin service không cần public IP.
- Dễ mở rộng thêm portal mới bằng hostname/path và Access app/policy.

Kết luận: **chọn Cloudflare Zero Trust + Tunnel + Access làm primary access path mới**. SSM giữ làm fallback/break-glass.

## 4. Quyết định

Chọn phương án:

```text
Mentor/team browser
  -> https://grafana.<domain>
  -> Cloudflare Access login/policy
  -> Cloudflare Tunnel
  -> cloudflared connector trong EKS hoặc Bastion private subnet
  -> Kubernetes Service nội bộ: grafana / jaeger / loadgen
```

Storefront vẫn đi qua public ALB hiện tại:

```text
Internet
  -> public ALB
  -> frontend-proxy
  -> storefront
```

Các route vận hành trên public ALB vẫn bị chặn:

```text
/grafana   -> 404
/jaeger    -> 404
/loadgen   -> 404
/feature   -> 404
/flagservice -> 404
/otlp-http -> 404 hoặc method blocked
```

## 5. Scope implement đề xuất

Proposal này không rollback phần SEC-05 đã làm. SEC-05 vẫn giữ nguyên mục tiêu: public ALB chỉ phục vụ storefront và chặn operational routes.

Phần bổ sung này chỉ thêm đường private access mới để thay thế trải nghiệm SSM thủ công.

### 5.1 Portal cần publish qua Cloudflare Access

Ưu tiên:

1. Grafana: `grafana.<domain>`
2. Jaeger: `jaeger.<domain>`
3. Load Generator: `loadgen.<domain>`

Không publish:

- `flagd` hoặc `flagservice` control path nếu không có nhu cầu mentor truy cập.
- OTLP endpoint.
- OpenSearch API.
- Kubernetes API.
- ArgoCD/CD UI nếu hệ thống hiện chưa deploy. Nếu sau này có ArgoCD/CD UI thì phải thêm vào cùng mô hình private access, không đi public ALB.

### 5.2 Cách deploy `cloudflared`

Khuyến nghị deploy `cloudflared` trong Kubernetes namespace riêng, ví dụ `cloudflare-access` hoặc `techx-observability`, bằng Helm hoặc manifest GitOps.

Các yêu cầu:

- Dùng Cloudflare Tunnel token/credential trong Kubernetes Secret.
- Chạy ít nhất 2 replica nếu muốn HA cho access path.
- Không cần Service type `LoadBalancer`.
- Không cần public ingress.
- Egress outbound HTTPS tới Cloudflare phải được phép.
- Resource request/limit nhỏ nhưng phải có để không ảnh hưởng workload chính.

Ví dụ luồng nội bộ:

```text
cloudflared deployment
  -> grafana.techx-observability.svc.cluster.local:80
  -> jaeger.techx-observability.svc.cluster.local:16686
  -> load-generator.techx-tf4.svc.cluster.local:8089
```

Tên service/port cần verify lại bằng runtime trước khi implement.

## 6. Các bước implement đề xuất

### Bước 1 - Chuẩn bị Cloudflare account/domain

- Xác nhận domain hoặc subdomain TF4 sẽ dùng.
- Nếu full DNS setup: quản lý DNS trực tiếp trong Cloudflare.
- Nếu partial setup: tạo CNAME ở DNS provider hiện tại trỏ về Cloudflare hostname theo hướng dẫn Cloudflare.
- Tạo Zero Trust organization.
- Kết nối IdP nếu có, hoặc dùng One-time PIN/email allowlist cho giai đoạn đầu.

### Bước 2 - Tạo Access policy

Tạo policy tối thiểu:

- Allow mentor email/domain được duyệt.
- Allow team TF4 được duyệt.
- Deny default cho mọi người còn lại.
- Session duration ngắn, ví dụ 8-12 giờ cho mentor review.
- Bật MFA nếu IdP hỗ trợ.

Policy nên tách theo app:

- `TF4 Grafana Access`
- `TF4 Jaeger Access`
- `TF4 Loadgen Access`

Nếu cần đơn giản hóa, có thể dùng một reusable policy `TF4 Operational Portal Reviewers`.

### Bước 3 - Tạo Cloudflare Tunnel

- Tạo named tunnel, ví dụ `tf4-operational-portals`.
- Lấy tunnel token/credential.
- Lưu token vào GitHub Actions Secret hoặc AWS Secrets Manager/Kubernetes Secret tùy CD workflow.
- Không commit token vào repo.

### Bước 4 - Deploy `cloudflared`

Tạo manifest/Helm values cho `cloudflared`:

- Deployment 2 replicas.
- Secret chứa tunnel token.
- Config route hostname tới internal service.
- Readiness/liveness probe nếu chart hỗ trợ.
- NetworkPolicy nếu cluster dùng policy.

Ví dụ routing logic:

```yaml
ingress:
  - hostname: grafana.<domain>
    service: http://grafana.techx-observability.svc.cluster.local:80
  - hostname: jaeger.<domain>
    service: http://jaeger.techx-observability.svc.cluster.local:16686
  - hostname: loadgen.<domain>
    service: http://load-generator.techx-tf4.svc.cluster.local:8089
  - service: http_status:404
```

Port/service thực tế phải lấy từ:

```bash
kubectl -n techx-observability get svc
kubectl -n techx-tf4 get svc
```

### Bước 5 - Verify public ALB vẫn chỉ phục vụ storefront

Kỳ vọng:

```bash
curl -I http://<PUBLIC_ALB>/
curl -I http://<PUBLIC_ALB>/grafana/
curl -I http://<PUBLIC_ALB>/jaeger/ui/
curl -I http://<PUBLIC_ALB>/loadgen/
```

Expected:

- `/` trả `200`.
- `/grafana`, `/jaeger`, `/loadgen` trả `404` hoặc bị block theo thiết kế.

### Bước 6 - Verify Cloudflare Access

Test 1: user không nằm trong policy.

- Mở `https://grafana.<domain>`.
- Expected: bị deny hoặc yêu cầu login nhưng không được cấp quyền.

Test 2: mentor/team nằm trong policy.

- Login qua Cloudflare Access.
- Expected: vào được Grafana/Jaeger/Loadgen.

Test 3: session hết hạn.

- Sau session duration, mở lại portal.
- Expected: phải re-authenticate.

Test 4: Access log.

- Chụp log Cloudflare Access cho ít nhất một lần allow và một lần deny.

### Bước 7 - Verify không ảnh hưởng SLO/storefront

Vì Cloudflare Tunnel chỉ phục vụ operational portal và không nằm trên customer checkout path, rủi ro ảnh hưởng storefront thấp. Vẫn cần smoke test:

```bash
curl -I http://<PUBLIC_ALB>/
kubectl -n techx-tf4 get deploy frontend-proxy frontend checkout cart payment shipping product-catalog
kubectl -n techx-tf4 get pods
```

Nếu có checkout smoke checklist, chạy lại sau deploy.

### Bước 8 - Update runbook

Update các docs hiện tại:

- `docs/cdo08/week2/output/MANDATE-01-VERIFICATION-GUIDE.md`
- `docs/cdo08/week2/output/MANDATE-01-CUTOVER-REPORT.md`
- `docs/cdo08/week2/CDO08-SEC-05-INGRESS-HARDENING-RUNBOOK.md`

Nội dung update:

- SSM chuyển thành fallback/break-glass.
- Primary access path là Cloudflare Access domain.
- Thêm hướng dẫn mentor: vào domain, login, không cần AWS account nếu chỉ review portal.
- Thêm cách CDO07 lấy Access logs.

## 7. Acceptance Criteria

- Public ALB storefront `/` vẫn truy cập được.
- Public ALB không truy cập được `/grafana`, `/jaeger`, `/loadgen`, `/feature`, `/flagservice`, `/otlp-http`.
- `https://grafana.<domain>` chỉ vào được sau Cloudflare Access authentication.
- User không nằm trong policy bị deny.
- Mentor/team được allow vào được Grafana/Jaeger/Loadgen bằng domain.
- Cloudflare Access log có bằng chứng allow/deny.
- `cloudflared` chạy ổn định trong cluster hoặc private subnet.
- SSM Bastion vẫn còn fallback trong giai đoạn chuyển đổi.
- Không commit tunnel token, app secret hoặc credential vào repo.

## 8. Rollback và safety

Rollback an toàn:

1. Disable Cloudflare Access app hoặc tunnel route.
2. Scale down `cloudflared` deployment nếu cần.
3. Giữ public ALB block routes vận hành, không rollback việc expose portal ra public.
4. Dùng lại SSM Bastion fallback nếu mentor/team cần truy cập gấp.

Không rollback bằng cách mở lại `/grafana`, `/jaeger`, `/loadgen` trên public `frontend-proxy`.

## 9. Evidence cần nộp

- Screenshot hoặc output Cloudflare Access app/policy.
- Screenshot/tunnel status showing `cloudflared` healthy.
- `kubectl get deploy,pods` cho `cloudflared`.
- `curl` public ALB chứng minh storefront `200` và portal route public bị chặn.
- Screenshot mentor/team login thành công vào Grafana/Jaeger/Loadgen qua domain.
- Screenshot/log deny với user không được phép.
- Cloudflare Access log/audit evidence.
- Smoke test storefront/checkout sau khi bật tunnel.

## 10. Tài liệu tham khảo

- Cloudflare Tunnel: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/
- Cloudflare Access self-hosted applications: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/
- Tailscale Kubernetes Operator: https://tailscale.com/docs/kubernetes-operator
- NetBird Getting Started: https://docs.netbird.io/get-started
- OpenVPN Access Server pricing: https://openvpn.net/access-server/pricing/
- AWS CloudFront Developer Guide: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/
