# MANDATE-02 — Chuẩn bị Flash Sale 200 users: tuning, evidence và cost estimate

**Trạng thái:** chuẩn bị đã triển khai/render; **chưa chạy EKS flash-sale**.  
**Mục tiêu mandate:** 200 concurrent users, giữ 15 phút; checkout ≥99%, browse/cart ≥99.5%, storefront p95 <1s; co về mức thường sau peak; chi phí trên successful unit không phình. Nguồn: [`MANDATE-02`](../../requirements/mandates/MANDATE-02-scale-under-budget.md).

> Phân loại bằng chứng trong tài liệu:
> - **Implemented/rendered:** cấu hình đang có trong repository, chưa phải số liệu runtime EKS.
> - **Local runtime:** CSV Minikube API-only, hữu ích để chọn canary nhưng **không chứng minh EKS/AWS cost**.
> - **Pre-live estimate:** mô hình giá AWS cho kế hoạch test, không phải hóa đơn.
> - **Pending EKS verification:** điều kiện bắt buộc trước khi đóng mandate.

## 1. Traceability và verdict hiện tại

| Yêu cầu | Evidence hiện có | Verdict hiện tại |
|---|---|---|
| 200 users / 15 phút, giữ SLO | Local `lean-v2` final run có 200 users, 15 phút; raw CSV được copy tại `artifacts/` | **Local pass; EKS pending** |
| Browse/cart ≥99.5%, checkout ≥99%, storefront p95 <1s | Xem §2; flow SLO của local CSV đều đạt | **Local pass; EKS pending** |
| Tự tìm/bịt bottleneck, không phá kiến trúc | Direct requests/limits, HPA CPU cho critical stateless path, Metrics Server và guardrail; không đổi flagd hay stateful autoscaling | **Implemented/rendered** |
| Scale lên rồi xuống | Local frontend từng có tín hiệu HPA `1→2→3→1`; EKS canary đặt `frontend`/`checkout` HPA 1–3 replica. EKS chưa có HPA timeline | **Local signal; EKS pending** |
| ~$300/tuần và cost/successful unit không phình | Giá AWS Price List và allocation model tại §5; Cost Explorer/CUR chưa đối chiếu | **Pre-live partial estimate only** |

Ràng buộc mandate vẫn giữ nguyên: storefront public, cổng vận hành private, và không vô hiệu hóa/động vào cơ chế incident `flagd`.

## 2. Local evidence được archive — không phải EKS result

### 2.1 Nguồn và integrity

Nguồn immutable ban đầu:
`C:/Users/thanh/Desktop/workspace/FINAL-PHASE/docs/artifacts/minikube-resource-tuning/20260713T163957Z/lean-v2/flash-sale/`

Bốn CSV được copy nguyên byte vào [`artifacts/lean-v2-20260713T163957Z/`](./artifacts/lean-v2-20260713T163957Z/) để mentor có thể kiểm tra lại. Run ID là `20260713T163957Z`; đây là Minikube `techx-perf`, API-only, loại trừ `chaos`.

| File | SHA-256 |
|---|---|
| `flash-sale_stats.csv` | `7a014161c8865bfce11ede363d125268e47fd3baff2fa3821c1aab4db38b91fd` |
| `flash-sale_stats_history.csv` | `aa12ec1505e9c35d3cce65becd9d6ccfe273b532c296671eb6b98807f7201ba6` |
| `flash-sale_failures.csv` | `03158b9dc3505155eb03d9d204e6c7c557874200fab791d621c98f6659617919` |
| `flash-sale_exceptions.csv` | `3e73e8f665731ee4e45a6a91202a31b06999f2c53240f14aee2532e0e0b42b09` |

### 2.2 Kết quả đã tính từ `flash-sale_stats.csv`

| Flow / phép đo | Requests | Failures | Success | p95 | Threshold | Local verdict |
|---|---:|---:|---:|---:|---:|---|
| All requests | 47,080 | 3 | 99.994% | 28 ms | thông tin tổng | pass |
| Storefront `GET /` | 200 | 0 | 100% | 130 ms | <1,000 ms | pass |
| Cart `GET /api/cart` | 4,239 | 3 (`503`) | 99.929% | 8 ms | ≥99.5%, <1,000 ms | pass |
| Cart `POST /api/cart` | 8,630 | 0 | 100% | 10 ms | ≥99.5%, <1,000 ms | pass |
| Checkout `POST /api/checkout` | 2,868 | 0 | 100% | 89 ms | ≥99% | pass |

Tổng successful requests là **47,077**. `flash-sale_failures.csv` ghi đúng ba `503` ở `GET /api/cart`; `flash-sale_exceptions.csv` chỉ có header, không có exception. History CSV là bằng chứng ramp/steady/ramp-down của cùng run, không thay thế snapshot HPA/EKS.

Các số trên phù hợp với báo cáo local nguồn [`MINIKUBE-LOCAL-TUNING-REPORT.md`](C:/Users/thanh/Desktop/workspace/FINAL-PHASE/docs/MINIKUBE-LOCAL-TUNING-REPORT.md), nhưng không được dùng để tuyên bố AWS đã pass. Docker/Minikube không mô phỏng scheduler EKS, node allocatable thực, T3 Unlimited CPU credits/surplus charges, Cost Explorer/CUR hay cost/order.

## 3. Lý do chọn tuning hiện tại

### 3.1 Nguyên tắc chọn candidate

Local lab dùng ladder `lean → balanced → headroom`: bắt đầu mức reservation thấp nhất, chỉ tăng khi SLO hoặc reliability gate fail. `lean-v2` là candidate local sau khi giảm những service stateless low-risk; local run cuối giữ client SLO và không có Jaeger restart/OOM mới sau khi dùng **local-only** `MEMORY_MAX_TRACES=5000`.

Điều đó chỉ là lý do để bắt đầu EKS canary với requests/limits rõ ràng, **không** phải lý do để giảm tiếp hay copy Jaeger cap sang EKS. Các reliability gate vẫn quan trọng hơn client SLO: một run `lean-v2` trước đó đã bị loại dù Locust pass vì Jaeger `OOMKilled`.

### 3.2 Thay đổi chuẩn bị đã làm trong repository

| Hạng mục | Thay đổi | Lý do / giới hạn |
|---|---|---|
| Resource contract | 12 service trong scope flash-sale có direct CPU/memory requests và limits tại [`values.yaml`](../../../techx-corp-chart/values.yaml): `frontend-proxy`, `frontend`, `cart`, `product-catalog`, `recommendation`, `product-reviews`, `llm`, `checkout`, `currency`, `payment`, `shipping`, `load-generator` | Scheduler có reservation rõ ràng; CPU HPA có baseline. Không tune node size/count. |
| Replica baseline | `cart`, `frontend-proxy`, `payment`, `product-catalog`, `shipping` dùng 1 replica; `frontend` và `checkout` dùng HPA floor 1 tại [`values.yaml`](../../../techx-corp-chart/values.yaml) | Giải phóng capacity/cost trước Flash Sale. Không scale stateful, flagd hoặc observability. |
| Autoscaling | Chỉ `frontend` và `checkout` dùng `autoscaling/v2`, min 1 / max 3, target CPU 70%, scale up tối đa +1 pod/60s, scale-down stabilization 300s tại [`values.yaml`](../../../techx-corp-chart/values.yaml) và [`hpa.yaml`](../../../techx-corp-chart/templates/hpa.yaml) | Deployment bỏ `spec.replicas` khi HPA enabled; `minReplicas: 1` là effective baseline. |
| Kubernetes resource metrics | Metrics Server là dependency của release observability, không phải workflow riêng; request `50m/100Mi`, limit `100m/200Mi` tại [`values-observability.yaml`](../../../deploy/values-observability.yaml) | Cấp `metrics.k8s.io` cho HPA CPU và `kubectl top`; Prometheus vẫn phụ trách dashboard/SLO, không thay thế Metrics API. |
| Load control | [`values-load-test-task4.yaml`](../../../deploy/values-load-test-task4.yaml) cấu hình API-only, 200 users, spawn 5/s, total 16m20s, browser traffic disabled và `LOCUST_AUTOSTART=false`; `load-generator` có 1 replica | Pod chỉ phát traffic khi operator bắt đầu phiên được duyệt. Runbook giải thích 1m ramp-up + 15m steady + 20s ramp-down. |
| Evidence gate | [`RUNBOOK.md`](./RUNBOOK.md) yêu cầu UI-first evidence từ Grafana, Jaeger, OpenSearch, Alertmanager và Locust; chỉ Locust CSV/HTML là raw load-generator output | Không dùng `monitor-load-test.sh`, CLI dump hay raw Prometheus/Alertmanager JSON làm evidence MANDATE-02. |
| Delivery checks | [CI](../../../.github/workflows/ci.yaml) render/lint chart, assert 12 deployments có CPU/memory requests/limits và chỉ có HPA `frontend`,`checkout`; [deploy](../../../.github/workflows/deploy.yaml) deploy observability trước, verify Metrics API rồi mới deploy app và chụp HPA/pod/node evidence | Giảm lỗi render/order trước canary; không phải runtime test evidence. |

### 3.3 Capacity boundaries và open risk

- EKS Managed Node Group là `t3.large` On-Demand, **min 2 / desired 2 / max 4**; EBS root là 20-GiB gp3/node: [`infra/terraform/eks.tf`](../../../infra/terraform/eks.tf).
- Repository không có Karpenter, Cluster Autoscaler hay node autoscaler. Vì vậy `max_size=4` là giới hạn cấu hình, **không có nghĩa HPA sẽ tự tạo node**. HPA max 3 là ceiling pod-side của `frontend`/`checkout`.
- Namespace quota là requests `4 CPU`/`8Gi`, limits `8 CPU`/`12Gi`, tối đa 40 pods: [`deploy/quota.yaml`](../../../deploy/quota.yaml). Cần kiểm tra scheduling thật trước full run.
- Local history ghi product-catalog có bootstrap restarts cũ và checkout chưa scale; cả hai cần baseline EKS, không được che giấu bằng tăng resource hàng loạt.
- Không có live deployment/load test EKS nào được thực hiện bởi thay đổi này.

## 4. Kịch bản EKS được phép chạy

Dùng lại [Task-4 runbook](../../epic-03-performance-efficiency/runtime/RUNBOOK.md) và harness hiện có, không tạo workflow/harness mới:

1. Deploy observability; verify `deployment/metrics-server`, `apiservice/v1beta1.metrics.k8s.io`, raw `/apis/metrics.k8s.io/v1beta1`, `kubectl top nodes`.
2. Deploy app với `values-app-stamp.yaml`; xác nhận 5 Deployment static có 1 available replica, `frontend`/`checkout` HPA min/current là 1, HPA target/CPU metrics, requests/limits và quota headroom.
3. Chụp pre-test baseline đang có tại [`TASK-5-Pre-Load-Test-Baseline.md`](./TASK-5-Pre-Load-Test-Baseline.md), rồi chạy API-only 200-user shape. Bài test không tự chạy do `LOCUST_AUTOSTART=false`.
4. Giám sát SLO, restart/OOM, per-pod limit utilization, node utilization, HPA desired/current replicas, events và node count. Dừng theo safety stop trong [`RUNBOOK.md`](./RUNBOOK.md) nếu checkout error hoặc resource gate vượt ngưỡng.
5. Sau ramp-down, chờ HPA scale-down window (300s) và xác nhận `frontend`/`checkout` quay về 1 replica; thu evidence UI cho HPA, events, pods và node metrics. Không pass scale-down nếu replica/usage không quay lại baseline này.
6. Chụp Locust CSV/HTML và UI evidence cùng test window từ Grafana, Jaeger, OpenSearch và Alertmanager; sau đó so Cost Explorer/CUR và T3 credit/surplus-credit data cho đúng UTC window.

## 5. AWS Price List cost estimate (pre-live)

### 5.1 Đơn giá và phạm vi

Giá được truy vấn từ AWS Price List API ngày **2026-07-14** cho `us-east-1`, On-Demand:

| Line item | Unit price | AWS Price List provenance |
|---|---:|---|
| EC2 Linux shared `t3.large` | `$0.0832/hour` | SKU `HBVJM3Q9S8K6MNPJ`, rate `HBVJM3Q9S8K6MNPJ.JRTCKXETXF.6YS6EN2CT7`; publication `2026-07-13T18:17:17Z`; effective `2026-07-01` |
| EKS cluster control plane | `$0.1000/hour` | SKU `ZYWMR684YSMFHWEU`, rate `ZYWMR684YSMFHWEU.JRTCKXETXF.6YS6EN2CT7`; publication `2026-07-07T15:23:51Z`; effective `2026-07-01` |
| EBS gp3 provisioned storage | `$0.0800/GB-month` | SKU `JG3KUJMBRGHV3N8G`, rate `JG3KUJMBRGHV3N8G.JRTCKXETXF.6YS6EN2CT7`; publication `2026-07-13T18:17:17Z`; effective `2026-07-01` |

Pricing model: 2 already-running `t3.large`, one EKS control plane, and two known 20-GiB gp3 root volumes (40 GiB). `t3.large` has baseline CPU credits; any T3 Unlimited surplus-credit charges are explicitly **not** priced in this model.

### 5.2 Allocation cho một test window

Test configuration là 16m20s tổng (`0.272222h`) để bao gồm 1m ramp-up + 15m steady + 20s ramp-down. Lấy local final run làm workload denominator: 47,077 successful requests và 2,868 successful **checkout requests**.

```text
window_cost = 2 × $0.0832 × 0.272222h
            + 1 × $0.1000 × 0.272222h
            + 40 GiB × $0.0800/GB-month × (0.272222h / 720h)
            = $0.073730
```

| Chỉ số allocation | Công thức | Estimate |
|---|---|---:|
| EC2 nodes trong window | `2 × 0.0832 × 0.272222h` | `$0.045298` |
| EKS control plane trong window | `0.10 × 0.272222h` | `$0.027222` |
| 40 GiB gp3 trong window | `3.20 × 0.272222/720` | `$0.001210` |
| **Allocated infrastructure/window** | Tổng ba line trên | **`$0.073730`** |
| Allocation / successful request | `$0.073730 / 47,077` | **`$0.000001566`** (~`$0.001566` / 1,000 requests) |
| Allocation / successful checkout request proxy | `$0.073730 / 2,868` | **`$0.000025708`** |

`checkout request proxy` **không phải** cost/order: repository chưa reconcile đơn thành công, duplicate order hay cleanup. Post-run chỉ được ghi cost/order khi lấy được số successful orders đúng cùng window.

Marginal bill của một lần test trên baseline đã chạy là gần **$0** cho compute/control-plane/storage đã luôn bật; `$0.073730` là allocation để so efficiency, không phải hóa đơn tăng thêm. Nếu operator **chủ động** tăng thêm hai nodes trong 15 phút thì EC2 sensitivity là `2 × $0.0832 × 0.25h = $0.041600`, chưa tính root EBS, traffic hoặc T3 credits. Đây không phải outcome tự động vì không có node autoscaler.

### 5.3 Weekly sanity check và budget ambiguity

```text
2 × $0.0832 × 168h + $0.10 × 168h + 40 GiB × $0.08 × 7/30
= $45.501867/week
```

Đây là **partial allocated baseline** (EC2 + EKS + known root gp3) và bằng ~15.2% target `$300/week` của mandate. Nó **không** chứng minh budget compliance vì chưa gồm NAT/data processing, ALB/LCU, data transfer, CloudWatch, ECR, application/observability storage, workload EBS ngoài root volumes, tax hoặc T3 surplus credits. Baseline cost report cũ có inventory các cost driver đó: [`COST-01`](../../epic-04-cost-optimization/01-baseline-cost-estimate.md).

Có một policy inconsistency cần xử lý rõ ràng: mandate/onboarding nói `~$300/week`, còn Terraform budget hiện được đặt nominal `$300/month`. Không được xem hai ngưỡng này là cùng một budget. Trước sale, owner tài chính phải xác nhận threshold dùng để đánh giá; sau sale, Cost Explorer/CUR theo UTC window là nguồn final.

## 6. Điều kiện đóng MANDATE-02

- [ ] EKS metrics API/HPA metrics hoạt động và deploy evidence được lưu.
- [ ] 200-user/15-minute EKS run có raw Locust CSV/HTML/log và thực tế đạt từng SLO.
- [ ] Không có restart/OOM/Pending mới; CPU/memory/node headroom và quota được kiểm chứng.
- [ ] HPA/evidence chứng minh scale-down sau peak, hoặc nêu rõ service không scale vì CPU không đủ target.
- [ ] Cost Explorer/CUR, ALB/NAT/data transfer và T3 credit/surplus-charge được đối chiếu cùng UTC window.
- [ ] Tính lại cost/successful request và cost/successful order từ live denominators; so với baseline trước test, không chỉ so total bill.

**Kết luận:** Tuning và guardrail đã chuẩn bị một canary bảo thủ, có request/limit contract và evidence path. Local flash-sale cho thấy candidate đáng thử; nó không thay thế EKS load test hay AWS billing verification.
