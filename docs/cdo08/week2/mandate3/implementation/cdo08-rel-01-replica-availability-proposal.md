# Đề xuất tăng replica và phân tán critical services

| Thông tin     | Giá trị                                                                            |
| ------------- | ---------------------------------------------------------------------------------- |
| Backlog ID    | `CDO08-REL-01`                                                                     |
| Owner         | Hoàng Nam                                                                          |
| Pillar        | Reliability                                                                        |
| Priority      | P0                                                                                 |
| Loại tài liệu | Technical and cost review proposal                                                 |
| Review gate   | Nguyên review technical risk và CDO04 review cost/capacity trước khi cập nhật Helm |
| Phạm vi       | CDO08 Week 2 - replica availability cho 7 critical app services                    |

## 1. Mục tiêu

Tài liệu này đề xuất phương án tăng availability cho bảy critical app services đang chạy single-replica. Mục tiêu là loại bỏ single point of failure ở customer/checkout path mà không tăng tài nguyên thiếu kiểm soát, làm pod `Pending` hoặc gây rủi ro rollout trên cluster hiện tại.

Phạm vi giữ nguyên theo backlog đã được duyệt:

- `frontend-proxy`
- `frontend`
- `checkout`
- `cart`
- `payment`
- `shipping`
- `product-catalog`

Task này chỉ thay đổi stateless application services. PostgreSQL, Valkey và Kafka cần thiết kế persistence/replication riêng, không tăng replica cơ học trong task này.

## 2. Hiện trạng và evidence

### 2.1. Replica baseline

| Evidence                                      | Kết luận                                                |
| --------------------------------------------- | ------------------------------------------------------- |
| `techx-corp-chart/values.yaml:27`             | `default.replicas: 1`                                   |
| `techx-corp-chart/templates/_objects.tpl:13`  | Component không override sẽ render theo default replica |
| `kubectl -n techx-tf4 get deploy`             | Runtime Week 1 xác nhận critical services đều `1/1`     |
| `docs/cdo08/week1/replica-coverage-matrix.md` | Static/runtime matrix và criticality đã được ghi nhận   |

### 2.2. Cluster baseline

| Hạng mục               | Hiện trạng                                                     | Ý nghĩa với task                                                               |
| ---------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Worker nodes           | 2 x `t3.large`                                                 | Hai node là failure domains tối thiểu để phân tán hai replicas                 |
| Availability Zones     | `us-east-1a`, `us-east-1b`                                     | Có basic multi-AZ compute placement                                            |
| Node group             | `min=2`, `desired=2`, `max=4`                                  | Tăng pod không tự động đồng nghĩa tăng node; cần xác nhận autoscaling/capacity |
| Workload density       | Khoảng 25 deployments và observability/data workloads          | Hai node đang chia sẻ nhiều workload; cần runtime headroom evidence            |
| Baseline cost estimate | Khoảng `$56.83-$58.18/tuần`, chưa gồm toàn bộ usage-based cost | Thấp hơn trần mandate nhưng phải xác nhận actual cost bằng Cost Explorer       |
| Scenario 4 nodes       | Khoảng `$84.79/tuần`, chưa gồm usage-based cost                | Chỉ là estimate; không dùng làm lý do scale node khi chưa có approval          |

Nguồn cluster/cost:

- `infra/terraform/eks.tf:35-40`
- `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md`
- `docs/evidence/epic-04-cost-optimization/05-right-sizing-cost-saving-recommendation.md`

## 3. Capacity impact sơ bộ

Việc tăng từ một lên hai replicas tạo thêm bảy pod. Dựa trên memory limit hiện có trong `values.yaml`, phần memory limit tăng thêm theo lý thuyết là:

| Service           | Memory limit/pod | Replica tăng thêm | Memory limit tăng thêm |
| ----------------- | ---------------: | ----------------: | ---------------------: |
| `frontend-proxy`  |            65 Mi |                 1 |                  65 Mi |
| `frontend`        |           250 Mi |                 1 |                 250 Mi |
| `checkout`        |            20 Mi |                 1 |                  20 Mi |
| `cart`            |           160 Mi |                 1 |                 160 Mi |
| `payment`         |           140 Mi |                 1 |                 140 Mi |
| `shipping`        |            20 Mi |                 1 |                  20 Mi |
| `product-catalog` |            20 Mi |                 1 |                  20 Mi |
| **Tổng**          |                  |         **7 pod** |             **675 Mi** |

Đây không phải mức sử dụng thực tế và cũng chưa phải scheduler reservation:

- Chart hiện chủ yếu khai báo memory limit, chưa có CPU/memory requests rõ cho các service trong scope.
- Scheduler có thể đánh giá capacity không chính xác nếu requests bằng 0 hoặc bị default bởi policy ngoài chart.
- Actual usage, node allocatable, system overhead và observability pressure cần được lấy từ Prometheus/Grafana hoặc runtime API trước khi approve.
- Cost impact được phân tích riêng ở mục `4.6`; không quy đổi trực tiếp memory limit của pod thành USD.

## 4. So sánh 2 replicas và 3 replicas

Quyết định replica count không nên dựa trên nguyên tắc "càng nhiều càng an toàn". Cần cân đồng thời availability, capacity còn lại khi có lỗi, scheduling, rollout và cost.

### 4.1. So sánh tổng quan

| Tiêu chí                          | 2 replicas/service                                              | 3 replicas/service                                                            |
| --------------------------------- | --------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Pod count của 7 service           | 14 pod, tăng 7 pod so với baseline                              | 21 pod, tăng 14 pod so với baseline                                           |
| Tổng memory limit lý thuyết       | 1,350 Mi                                                        | 2,025 Mi                                                                      |
| Memory limit tăng so với baseline | +675 Mi                                                         | +1,350 Mi                                                                     |
| Khi mất 1 pod                     | Còn 1 pod, khoảng 50% nominal capacity                          | Còn 2 pod, khoảng 67% nominal capacity                                        |
| Availability cơ bản               | Loại single-pod SPOF                                            | Có thêm safety margin khi một pod lỗi/rollout                                 |
| Rolling update                    | Ít pod hơn, nhưng một pod lỗi làm capacity giảm một nửa         | Giữ được hai pod khi một pod lỗi, rollout an toàn hơn nếu cluster đủ capacity |
| Phân bố trên 2 node               | Có thể đạt `1/1`                                                | Chỉ đạt `2/1`, không cân tuyệt đối                                            |
| Mất node                          | Nếu spread đúng, còn 1 pod                                      | Có thể còn 1 hoặc 2 pod tùy node bị mất                                       |
| Required anti-affinity hostname   | Khả thi cho desired replicas nhưng có thể chặn surge pod thứ ba | Không khả thi trên cluster chỉ có 2 node                                      |
| Node pressure                     | Thấp hơn                                                        | Cao hơn; dễ tác động observability và stateful workloads                      |
| Cost nếu vẫn dùng 2 node          | Không thêm fixed EC2/EBS cost nếu fit; dùng thêm headroom       | Không thêm fixed EC2/EBS cost nếu fit; node pressure cao hơn                  |
| Phù hợp                           | Minimum HA baseline                                             | Service cần thêm capacity/safety margin có evidence                           |

### 4.2. Lợi ích và đánh đổi của 2 replicas

**Lợi ích:**

- Là mức tối thiểu để loại single-replica SPOF.
- Với hai node hiện tại, có thể đặt một pod trên mỗi node.
- Tăng thêm khoảng 675 Mi memory limit cho toàn bộ scope, thấp hơn phương án ba replicas.
- Giữ nhiều node headroom hơn cho observability, data workloads và flash-sale traffic.
- Phù hợp làm fixed baseline trước khi có load evidence đầy đủ.

**Đánh đổi:**

- Khi một pod lỗi hoặc đang rollout, chỉ còn một pod phục vụ; nominal capacity giảm khoảng 50%.
- Không còn redundancy nếu pod còn lại tiếp tục lỗi.
- Một pod còn lại phải tự giữ SLO trong failure/maintenance window.
- Nếu một replica không chịu được tải 200 user, SLO vẫn có thể vỡ dù service không downtime hoàn toàn.

### 4.3. Lợi ích và đánh đổi của 3 replicas

**Lợi ích:**

- Khi mất một pod vẫn còn hai pod, giữ khoảng 67% nominal capacity.
- Có safety margin tốt hơn cho rollout, restart và transient failure.
- Phù hợp với service đã chứng minh một pod không đủ giữ SLO khi một replica bị loại khỏi traffic.
- Giảm rủi ro một lỗi tiếp theo làm service mất hoàn toàn sau khi pod đầu tiên đã hỏng.

**Đánh đổi:**

- Tăng 14 pod so với baseline hiện tại và thêm khoảng 1,350 Mi memory limit.
- Trên hai node chỉ có thể phân bố `2/1`; mất node chứa hai pod vẫn chỉ còn một pod phục vụ.
- Required pod anti-affinity theo hostname không thể schedule ba pod trên hai node.
- Tăng CPU/memory/telemetry pressure và xác suất phải scale node group.
- Nếu thêm node chỉ để giữ ba replicas, EC2 cost và chi phí phụ trợ tăng dù traffic thường có thể chưa cần.
- Nhân ba mọi service không chứng minh được cost/request hiệu quả theo Mandate 2.

### 4.4. Đề xuất replica count để review

Đề xuất ban đầu:

- Dùng **2 replicas** làm fixed availability baseline cho cả bảy service sau khi `REL-02` hoàn thành.
- Không dùng **3 replicas** đồng loạt.
- Chỉ nâng riêng service từ 2 lên 3 khi load test hoặc runtime evidence chứng minh một trong các điều kiện:
    - Một pod còn lại không giữ được SLO khi pod kia bị loại khỏi traffic.
    - CPU/memory/latency saturation xuất hiện ở mức tải mục tiêu.
    - Rollout/restart với hai replicas làm error rate hoặc p95 vượt ngưỡng.
    - Business impact của việc thiếu safety margin lớn hơn resource/cost tăng thêm.
- Sau peak, nếu sử dụng dynamic scaling thì tài nguyên phải co xuống; không giữ ba replicas thường trực chỉ để vượt bài test ngắn hạn khi không có evidence.

Đây là quyết định cần CDO04 xác nhận bằng node headroom, actual usage và cost/request. Tech Lead xác nhận mức availability còn lại khi một pod hoặc một node bị mất.

PDB không nằm trong phạm vi triển khai chính của proposal này, nhưng nên được đánh dấu là follow-up bắt buộc sau khi `REL-02` và `REL-01` ổn định. Khi critical services đã có `>=2 replicas`, readiness hoạt động đúng và pod được spread qua nhiều node, PDB mới có ý nghĩa để giảm rủi ro voluntary disruption như node `drain` hoặc maintenance.

Vì vậy, PDB chưa nên được xử lý trước replica/probe. Tuy nhiên, nếu mandate node `drain` hoặc rolling restart được kích hoạt trong Week 2, backlog PDB nên được nâng từ P2 lên P1 hoặc P0-dependent item: không làm trước `REL-02/REL-01`, nhưng phải làm ngay sau khi bảy critical services đạt `2/2 Ready` và rollout ổn định.

### 4.5. Nguồn ngân sách và điểm cần xác nhận

Nguồn chính thức hiện tại:

- `onboarding/BUDGET.md`: trần khoảng `$300/tuần/TF` cho toàn bộ AWS infrastructure.
- `mandates/MANDATE-02-scale-under-budget.md`: flash sale không được vượt trần hiện tại và cost/order hoặc cost/request không được phình khi tải tăng.

Hai file này thống nhất rằng `$300/tuần/TF` là **trần**, không chỉ là credit hỗ trợ.

### 4.6. Ước tính cost theo scenario 2/3 replicas

Kubernetes không tính phí theo pod hoặc replica. Chi phí compute chỉ tăng rõ khi replica mới không còn fit trên hai worker nodes và TF phải tăng node count.

Giả định dùng để tính:

| Hạng mục                       |                                Giá tham chiếu | Nguồn                                                                                                                                               |
| ------------------------------ | --------------------------------------------: | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| EC2 `t3.large` Linux On-Demand |                                 `$0.0835/giờ` | [AWS EC2 Unlimited Mode concepts](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-unlimited-mode-concepts.html) |
| EBS gp3                        |                              `$0.08/GB-tháng` | [AWS EBS pricing](https://aws.amazon.com/ebs/pricing/)                                                                                              |
| EKS standard support           |                           `$0.10/cluster-giờ` | [AWS EKS pricing](https://aws.amazon.com/eks/pricing/)                                                                                              |
| Cross-AZ data transfer         |            `$0.01/GB` theo mỗi hướng tính phí | [AWS EC2 On-Demand data transfer pricing](https://aws.amazon.com/ec2/pricing/on-demand/)                                                            |
| T3 Unlimited surplus CPU       | `$0.05/vCPU-giờ` nếu phát sinh surplus credit | [AWS EC2 Unlimited Mode concepts](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-unlimited-mode-concepts.html) |

Tài liệu estimate Week 1 của CDO04 dùng `$0.0832/giờ` cho `t3.large`, trong khi nguồn AWS tham chiếu tại thời điểm cập nhật proposal hiển thị `$0.0835/giờ`. Chênh lệch này nhỏ nhưng cho thấy estimate cần ghi kèm thời điểm; Cost Explorer vẫn là nguồn xác nhận actual spend, credit và discount của account TF.

Quy ước:

- Một tuần = `168 giờ`.
- Mỗi worker node có root volume gp3 `20 GiB` theo hạ tầng hiện tại.
- Chưa tính NAT processing, ALB LCU, CloudWatch, ECR, public IPv4, thuế và actual cross-AZ traffic.

Chi phí tăng thêm của một worker node:

```text
EC2:  $0.0835 x 168 giờ                         = $14.03/tuần
EBS:  20 GiB x $0.08 x 12 tháng / 52 tuần      =  $0.37/tuần
Tổng tối thiểu một node bổ sung                 = ~$14.40/tuần
```

Scenario cost cho riêng quyết định replica:

| Scenario                              | Node count | Chi phí tăng thêm so với 2 node hiện tại | Ý nghĩa                                                |
| ------------------------------------- | ---------: | ---------------------------------------: | ------------------------------------------------------ |
| 2 replicas cho 7 service và vẫn fit   |          2 |        **Không tăng fixed EC2/EBS cost** | Chỉ dùng thêm CPU/memory headroom hiện có              |
| 3 replicas cho 7 service và vẫn fit   |          2 |        **Không tăng fixed EC2/EBS cost** | Node pressure cao hơn đáng kể; vẫn có usage-based cost |
| Replica pressure buộc tăng lên 3 node |          3 |                         **~$14.40/tuần** | Thêm 1 x `t3.large` và 20 GiB gp3                      |
| Replica pressure buộc tăng lên 4 node |          4 |                         **~$28.80/tuần** | Thêm 2 x `t3.large` và 40 GiB gp3                      |

EKS control-plane charge không đổi khi tăng replica hoặc worker node vì vẫn là một cluster. Cross-AZ, telemetry, ALB/NAT và T3 CPU-credit cost có thể tăng theo traffic nhưng chưa thể tính thành con số cố định khi chưa có số GB, LCU, log volume và surplus vCPU-hours thực tế.

Ví dụ công thức bổ sung:

```text
Cross-AZ charge = số GB truyền liên AZ x $0.01/GB cho mỗi hướng tính phí
T3 surplus cost = surplus vCPU-hours x $0.05
```

Kết luận cost cho quyết định 2/3 replicas:

- Nếu replica mới vẫn fit trên hai worker nodes hiện tại, fixed infra cost tăng thêm gần như `$0` vì TF chưa phải trả thêm EC2/EBS cho node mới. Tuy nhiên đây không phải là cost tuyệt đối bằng `$0`, vì usage-based cost như telemetry, log/trace, network hoặc T3 surplus CPU vẫn có thể tăng theo tải.
- Đánh đổi chính giữa 2 và 3 replicas là node headroom: 3 replicas dùng nhiều CPU/memory hơn và có xác suất buộc scale node cao hơn.
- Nếu phải thêm một `t3.large` node, chi phí tối thiểu tăng khoảng `$14.40/tuần/node`, chưa gồm usage-based cost.
- CDO04 cần xác nhận trước khi approve: `2 replicas fit`, `3 replicas fit`, hay `3 replicas cần scale node`, dựa trên node utilization, actual usage, SLO/load evidence và Cost Explorer.

## 5. Readiness prerequisite

`CDO08-REL-02` nên được approve và triển khai trước `REL-01`:

- Replica chỉ giúp duy trì traffic khi Kubernetes phân biệt được pod nào đã sẵn sàng.
- Không có readiness, pod mới có thể nhận traffic quá sớm trong rollout.
- Liveness/readiness sai có thể làm nhiều replicas cùng `NotReady` hoặc restart, khiến việc tăng replica không đạt mục tiêu availability.

Nếu `REL-02` chưa hoàn tất, `REL-01` chỉ nên dừng ở design/cost review và không rollout production.

## 6. Phương án phân tán pod

### 6.1. Phương án A - Required pod anti-affinity theo hostname

Hai replicas của cùng service bắt buộc nằm trên hai node khác nhau.

**Ưu điểm:**

- Bảo đảm không có hai replicas cùng nằm trên một node.
- Mất một node vẫn còn một replica của từng service.

**Rủi ro trên cluster hai node:**

- Default RollingUpdate có thể tạo surge pod thứ ba.
- Required anti-affinity không cho pod thứ ba nằm cùng hai pod hiện hữu.
- Không có node thứ ba đủ điều kiện, surge pod có thể `Pending` và rollout bị kẹt.
- Nếu đặt `maxSurge: 0`, `maxUnavailable: 1`, rollout có thể tiếp tục nhưng tạm giảm xuống một replica, làm giảm capacity và safety margin.

Phương án này chỉ nên được chọn khi reviewer đồng thời chốt rollout strategy và capacity behavior.

### 6.2. Phương án B - Preferred pod anti-affinity

Scheduler ưu tiên tách replicas nhưng vẫn cho phép co-location khi thiếu capacity.

**Ưu điểm:** rollout ít bị kẹt và surge pod vẫn schedule được.

**Đánh đổi:** không bảo đảm tuyệt đối hai replicas nằm khác node; cần verify sau mỗi rollout và có thể phải reschedule thủ công.

### 6.3. Phương án C - Topology spread constraints (Recommended)

Đề xuất chính cho review:

```yaml
topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: kubernetes.io/hostname
      whenUnsatisfiable: DoNotSchedule
      labelSelector:
          matchLabels:
              app.kubernetes.io/name: <service>
```

**Ưu điểm:**

- Với hai replicas và hai node, scheduler phải phân tán theo hostname.
- `maxSkew: 1` vẫn cho phép surge pod thứ ba tạo phân bố `2/1`, tránh giới hạn tuyệt đối của required anti-affinity.
- Phù hợp hơn với rolling update trên cluster hai node.

**Điều kiện:**

- Cần bổ sung hỗ trợ `topologySpreadConstraints` vào Helm template/schema nếu chart chưa render field này.
- Label selector phải đúng với từng component.
- Phải render chart và chạy scheduling test trước production rollout.

### 6.4. Đề xuất lựa chọn

Ưu tiên **topology spread constraints với `maxSkew: 1`** cho bảy service. Nếu Tech Lead muốn giới hạn thay đổi template trong lần đầu, có thể dùng preferred anti-affinity làm baseline tạm thời nhưng phải ghi rõ không có hard guarantee.

Không áp required anti-affinity đồng loạt nếu chưa chứng minh rolling update không bị `Pending` trên cluster hai node.

## 7. HPA assessment

HPA chưa nên nằm trong lần triển khai baseline của task này:

- Backlog yêu cầu tối thiểu hai replicas để loại SPOF, còn HPA giải quyết dynamic load.
- Repo chưa có HPA template/manifest cho các service trong scope.
- CPU requests chưa được khai báo rõ; CPU-based HPA cần requests đáng tin cậy.
- Cần xác nhận metrics-server, min/max replicas, scale-up/down policy và load evidence.
- HPA có thể kích hoạt thêm pod/node và ảnh hưởng trực tiếp cost của Mandate 2.

HPA nên là follow-up sau probe, requests/limits baseline và load test. Trong task hiện tại chỉ ghi nhận HPA candidate, không triển khai khi chưa có review riêng.

## 8. Rollout proposal

### 8.1. Pre-deployment gates

- `REL-02` đã được approve và probe đã verify trên runtime.
- CDO04 xác nhận node CPU/memory headroom và actual cost.
- Nguyên approve topology spread/anti-affinity và rollout strategy.
- Helm render không lỗi; bảy deployments render `replicas: 2` và scheduling rule đúng label.
- Có Helm revision ổn định để rollback.

### 8.2. Triển khai từng service

Không tăng cả bảy service trong một rollout. Thứ tự đề xuất:

1. `frontend-proxy` - entrypoint stateless, kiểm tra distribution và routing.
2. `frontend` - storefront/API layer.
3. `product-catalog` - browse và checkout item lookup.
4. `shipping` - checkout dependency, footprint nhỏ.
5. `payment` - revenue-critical, cần smoke test kỹ.
6. `cart` - kiểm tra behavior với Valkey và readiness flag.
7. `checkout` - orchestration/revenue path, thực hiện sau khi dependency ổn.

Sau mỗi service:

- Theo dõi rollout status và pod events.
- Xác nhận `2/2` replicas `Ready`.
- Xác nhận hai pod phân tán đúng node.
- Chạy smoke test liên quan.
- Theo dõi error rate, p95 và restart.
- Dừng batch tiếp theo nếu pod `Pending`, `NotReady`, restart bất thường hoặc SLO/customer flow xấu đi.

## 9. Verification

### 9.1. Static/render verification

```bash
helm template techx-corp ./techx-corp-chart \
  -f deploy/values-observability.yaml \
  -f deploy/values-flagd-sync.yaml
```

Kiểm tra rendered Deployment có:

- `spec.replicas: 2` cho đúng bảy service.
- Topology spread/anti-affinity đúng label và topology key.
- Không thay đổi ngoài scope.

### 9.2. Runtime verification

```bash
kubectl -n techx-tf4 get deploy
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 rollout status deploy/<service>
kubectl -n techx-tf4 get events --sort-by=.lastTimestamp
```

Evidence phải có timestamp và chứng minh:

- Bảy deployments đạt `2/2 Ready`.
- Hai replicas của cùng service nằm trên node khác nhau.
- Không có `FailedScheduling`, `Insufficient memory/cpu`, `NotReady` hoặc restart bất thường.
- Browse, cart và checkout smoke test thành công.
- SLI/SLO không xấu đi sau rollout.

## 10. Rollback và safety

Rollback theo service, không rollback toàn bộ bảy service nếu chỉ một service gặp lỗi:

1. Dừng rollout batch tiếp theo.
2. Nếu lỗi do scheduling rule, revert rule của service bị ảnh hưởng.
3. Nếu lỗi do capacity/cost, rollback replica count service đó về `1`.
4. Nếu toàn release không ổn định, rollback về Helm revision ổn định gần nhất.
5. Xác nhận pod trở lại `Ready`, events ổn định và customer flow phục hồi.

Không tăng node group hoặc nới scheduling constraint trong lúc sự cố nếu chưa có CDO04/Tech Lead approval; hành động khẩn cấp phải được ghi evidence và lý do.

## 11. Cost/capacity review cho CDO04

CDO04 cần xác nhận các điểm sau trước implementation:

- Actual cost hiện tại từ Cost Explorer và headroom so với `$300/tuần/TF`.
- CPU/memory usage, peak usage và node allocatable của hai worker nodes.
- Hai node hiện tại có đủ headroom để thêm bảy pod replica mới mà không tạo CPU/memory pressure không.
- Nếu một node bị drain/restart, node còn lại có đủ capacity phục vụ tối thiểu một replica của mỗi critical service không.
- Node group có autoscaling thực sự hay chỉ đang cấu hình `max_size=4` trong Terraform.
- Nếu chọn 3 replicas hoặc xảy ra surge pod trong rollout, workload có buộc phải scale thêm node không.
- Usage-based cost dưới load test có tăng đáng kể không, gồm telemetry/log/trace, network/cross-AZ và T3 surplus CPU.

Chi tiết cost scenario nằm ở mục `4.6`. Phần CDO04 cần xác nhận ở đây là scenario thực tế: `2 replicas fit`, `3 replicas fit`, hay `3 replicas cần scale node`.

## 12. Các quyết định cần technical review

Nguyên và CDO04 xác nhận:

- Giữ nguyên danh sách bảy critical services.
- Chấp thuận 2 replicas làm baseline và tiêu chí nào cho phép một service tăng lên 3 replicas.
- `REL-02` là prerequisite trước production rollout.
- Chọn topology spread, preferred anti-affinity hay required anti-affinity.
- Chọn rollout strategy tương thích với cluster hai node.
- Node/cost headroom đủ cho bảy pod bổ sung.
- HPA được defer sang follow-up sau requests/metrics/load evidence.
- Xác nhận PDB có được nâng thành follow-up bắt buộc sau `REL-02/REL-01` không, đặc biệt nếu mandate node `drain` hoặc rolling restart được kích hoạt.
- Chấp thuận rollout từng service và rollback độc lập.

Sau khi cả technical risk và cost/capacity được approve mới cập nhật Helm chart và thu runtime evidence theo Jira task.

## 13. Kết luận

Đề xuất chính: tăng bảy critical services lên **2 replicas** để loại bỏ single-replica SPOF trên customer/checkout path. Việc rollout chỉ nên thực hiện sau khi đã có probe baseline, capacity/cost review và scheduling strategy được approve.

Với cluster hai node, **topology spread `maxSkew: 1`** là hướng phù hợp nhất để phân tán hai replicas mà vẫn cho phép rolling surge. Required anti-affinity có thể bảo đảm tách node chặt hơn, nhưng có rủi ro làm surge pod `Pending` và khóa rolling update.

Quyết định triển khai nên giữ ba nguyên tắc:

- Rollout từng service sau `REL-02`, đo SLO và capacity sau mỗi bước.
- Không tăng lên **3 replicas** đồng loạt; chỉ áp dụng cho service có load/SLO evidence cho thấy hai replicas chưa đủ.
- Chưa triển khai HPA trong baseline; chỉ xem xét sau khi có requests/limits, metrics và load-test evidence.

Cách tiếp cận này phù hợp tinh thần production và Mandate 2: tăng availability có kiểm soát, có cost review, không tăng tài nguyên chỉ để vượt bài test ngắn hạn.
---
## 🛡️ CDO-07 Audit Approval Sign-Off
- **Trạng thái:** ✅ APPROVED / PASS
- **Người kiểm duyệt:** CDO-07 (Đội ngũ Auditability)
- **Ngày thực hiện:** 2026-07-16
- **Đối tượng kiểm toán:** Kiểm chứng bằng chứng Reliability, Độ bền dữ liệu (Data Durability) và EKS/Karpenter HA.
- **Chi tiết xác minh:** Đã kiểm tra trạng thái runtime của cụm EKS bằng tài khoản quyền `TF4-AuditReadOnlyAndAnalyze`. Xác nhận các PVC (gp2/gp3) đã Bound, số lượng replicas (2/2 đi kèm topology spread constraints), liveness/readiness probes hoạt động ổn định, và Karpenter tự động cấp phát node thành công. Tính toàn vẹn của Kafka event và độ bền dữ liệu của PostgreSQL sau khi xóa/khởi động lại pod đã được xác minh đầy đủ và đạt yêu cầu.

