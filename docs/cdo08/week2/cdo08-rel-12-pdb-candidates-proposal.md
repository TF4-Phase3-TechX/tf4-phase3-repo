# Đề xuất PodDisruptionBudget cho critical services

| Thông tin     | Giá trị                                                             |
| ------------- | ------------------------------------------------------------------- |
| Backlog ID    | `CDO08-REL-12`                                                      |
| Owner         | Hoàng Nam                                                           |
| Pillar        | Reliability                                                         |
| Priority      | P2                                                                  |
| Loại tài liệu | Technical review proposal                                           |
| Review gate   | Nguyên review technical risk trước khi tạo PDB trong Helm           |
| Phạm vi       | CDO08 Week 2 - PDB candidates sau readiness và replica availability |

## 1. Mục tiêu

Tài liệu này đề xuất danh sách PodDisruptionBudget (PDB) candidates cho các service critical trên customer/checkout path. Mục tiêu là chuẩn bị bước bảo vệ voluntary disruption như node drain, maintenance hoặc eviction có kiểm soát, nhưng không tạo PDB khi workload chưa đủ điều kiện.

Phạm vi giữ nguyên theo backlog đã được duyệt:

- `frontend-proxy`
- `frontend`
- `checkout`
- `cart`
- `payment`
- `shipping`
- `product-catalog`

PDB không thay thế readiness/liveness probe và không thay thế replica baseline. PDB chỉ nên được tạo sau khi:

- `CDO08-REL-02` readiness/liveness probe đã rollout ổn định.
- `CDO08-REL-01` replica baseline quay lại `2/2 Ready` cho các service trong scope.
- Không có pod stuck, restart bất thường hoặc readiness false negative trong runtime evidence gần nhất.

## 2. Hiện trạng và evidence

### 2.1. PDB baseline

| Evidence                         | Kết luận                                           |
| -------------------------------- | -------------------------------------------------- |
| `kubectl -n techx-tf4 get pdb`   | `No resources found in techx-tf4 namespace.`       |
| Backlog item `CDO08-REL-12`      | Revenue path chưa có PodDisruptionBudget           |
| Week 1 finding `NAM-RUNTIME-007` | Thiếu PDB được ghi nhận là runtime reliability gap |

Runtime evidence hiện tại:

```bash
$ kubectl -n techx-tf4 get pdb
No resources found in techx-tf4 namespace.
```

Kết luận: namespace app hiện chưa có PDB nào bảo vệ các workload trong scope.

### 2.2. Replica baseline tại thời điểm viết proposal

Runtime evidence hiện tại cho bảy critical services:

```bash
$ kubectl -n techx-tf4 get deploy frontend-proxy frontend checkout cart payment shipping product-catalog
NAME              READY   UP-TO-DATE   AVAILABLE   AGE
frontend-proxy    1/1     1            1           6d10h
frontend          1/1     1            1           6d10h
checkout          1/1     1            1           6d10h
cart              1/1     1            1           6d10h
payment           1/1     1            1           6d10h
shipping          1/1     1            1           6d10h
product-catalog   1/1     1            1           6d10h
```

Kết luận: tại thời điểm viết proposal, bảy service critical đang là `1/1`. Do đó chưa đủ điều kiện để apply PDB an toàn.

Ghi chú: trước đó `REL-01` đã từng rollout các service này lên `2/2`, nhưng một deploy phục vụ task khác đã đưa runtime về `1/1`. Vì vậy PDB phải phụ thuộc vào trạng thái runtime cuối cùng, không chỉ phụ thuộc vào thiết kế ban đầu của `REL-01`.

### 2.3. Readiness baseline

`REL-02` đã thêm readiness/liveness probe cho bảy service critical. Đây là điều kiện cần trước PDB vì Kubernetes dùng trạng thái pod healthy/ready để quyết định disruption có được phép tiếp tục hay không.

Nếu readiness sai hoặc quá nhạy, PDB có thể tính số pod available thấp hơn thực tế, từ đó block drain hoặc rollout. Vì vậy PDB chỉ nên được triển khai sau khi probe baseline đã ổn định trên runtime.

## 3. PDB dùng để giải quyết vấn đề gì

PDB bảo vệ service khỏi **voluntary disruption**. Đây là các gián đoạn có kiểm soát, ví dụ:

- `kubectl drain` node.
- Node maintenance chủ động.
- Cluster autoscaler scale down node.
- Eviction có kiểm soát bởi Kubernetes.

PDB không bảo vệ được **involuntary disruption**, ví dụ:

- Node chết đột ngột.
- Kernel panic.
- AZ/network outage.
- Pod bị OOMKilled.
- Container crash do bug ứng dụng.

Vì vậy PDB không làm service tự có HA. Nó chỉ là guardrail để Kubernetes không chủ động evict quá nhiều pod healthy cùng lúc.

## 4. Điều kiện tiên quyết trước khi tạo PDB

Không tạo PDB cho workload `replicas: 1`.

Lý do:

- Với một pod duy nhất, PDB `minAvailable: 1` sẽ block voluntary disruption hoàn toàn.
- Nếu node cần drain thật, drain có thể kẹt vì Kubernetes không được phép evict pod đó.
- Nếu chọn `maxUnavailable: 1`, PDB gần như không bảo vệ availability cho single-replica workload.
- PDB không tạo thêm pod thay thế; nó chỉ giới hạn eviction.

Điều kiện apply tối thiểu:

| Điều kiện  | Trạng thái yêu cầu trước khi tạo PDB                               |
| ---------- | ------------------------------------------------------------------ |
| Replica    | Service có `replicas >= 2` và runtime `READY 2/2`                  |
| Readiness  | Readiness probe đã hoạt động ổn định                               |
| Rollout    | `kubectl rollout status deploy/<service>` thành công               |
| Events     | Không có `FailedScheduling`, `BackOff`, `CrashLoopBackOff` mới     |
| Scheduling | Pod được phân tán hợp lý trên node nếu mandate drain node cần demo |
| Review     | Nguyên approve technical risk trước implementation                 |

## 5. PDB candidate matrix

| Service           | Runtime hiện tại | Readiness baseline | PDB candidate | Đề xuất khi đủ điều kiện                   | Lý do                                                                            |
| ----------------- | ---------------- | ------------------ | ------------- | ------------------------------------------ | -------------------------------------------------------------------------------- |
| `frontend-proxy`  | `1/1`            | Đã có readiness    | Có, sau `2/2` | `minAvailable: 1` hoặc `maxUnavailable: 1` | Entry point public cho storefront; cần giữ ít nhất một pod khi drain/maintenance |
| `frontend`        | `1/1`            | Đã có readiness    | Có, sau `2/2` | `minAvailable: 1` hoặc `maxUnavailable: 1` | Service trực tiếp phục vụ browse/cart UI path                                    |
| `checkout`        | `1/1`            | Đã có readiness    | Có, sau `2/2` | `minAvailable: 1` hoặc `maxUnavailable: 1` | Revenue path quan trọng nhất; không nên bị evict hết trong maintenance           |
| `cart`            | `1/1`            | Đã có readiness    | Có, sau `2/2` | `minAvailable: 1` hoặc `maxUnavailable: 1` | Cart ảnh hưởng trực tiếp browse-to-checkout conversion                           |
| `payment`         | `1/1`            | Đã có readiness    | Có, sau `2/2` | `minAvailable: 1` hoặc `maxUnavailable: 1` | Payment nằm trong checkout path; cần giảm voluntary disruption                   |
| `shipping`        | `1/1`            | Đã có readiness    | Có, sau `2/2` | `minAvailable: 1` hoặc `maxUnavailable: 1` | Checkout phụ thuộc shipping quote/order step                                     |
| `product-catalog` | `1/1`            | Đã có readiness    | Có, sau `2/2` | `minAvailable: 1` hoặc `maxUnavailable: 1` | Browse/product details phụ thuộc service này                                     |

Kết luận của matrix: tất cả bảy service đều là PDB candidates, nhưng **chưa được apply ở runtime hiện tại** vì đang `1/1`.

## 6. Đề xuất `minAvailable` / `maxUnavailable`

Với baseline `2 replicas`, hai cấu hình tương đương về mặt mục tiêu là:

```yaml
minAvailable: 1
```

hoặc:

```yaml
maxUnavailable: 1
```

Đề xuất dùng `minAvailable: 1` cho readability vì nó diễn đạt trực tiếp mục tiêu: luôn giữ tối thiểu một pod available trong voluntary disruption.

Không dùng:

```yaml
minAvailable: 2
```

với `replicas: 2`.

Lý do:

- `minAvailable: 2` yêu cầu cả hai pod luôn available.
- Khi drain một node chứa một replica, Kubernetes không thể evict pod đó vì sẽ làm available giảm từ 2 xuống 1.
- Kết quả là node drain hoặc maintenance có thể bị block.
- Cấu hình này chỉ phù hợp khi replica count lớn hơn và reviewer chấp thuận trade-off rõ ràng.

Đề xuất baseline PDB khi đủ điều kiện:

| Replica count | PDB đề xuất                                | Ý nghĩa                                                    |
| ------------- | ------------------------------------------ | ---------------------------------------------------------- |
| `1`           | Không tạo PDB                              | Tránh block drain hoặc tạo policy không có ý nghĩa         |
| `2`           | `minAvailable: 1`                          | Cho phép evict một pod nhưng giữ ít nhất một pod available |
| `3`           | `minAvailable: 2` hoặc `maxUnavailable: 1` | Chỉ áp dụng nếu service được approve tăng lên 3 replicas   |

## 7. Rủi ro nếu cấu hình PDB sai

### 7.1. Block node drain

Nếu PDB yêu cầu quá nhiều pod available so với replica count, node drain có thể bị kẹt. Đây là rủi ro chính trong mandate maintenance-no-downtime, vì nhóm cần tự thực hiện drain hoặc rolling-restart trước mentor.

Ví dụ rủi ro:

```text
replicas = 2
minAvailable = 2
node drain cần evict 1 pod
available sẽ còn 1
PDB không cho evict
node drain bị block
```

### 7.2. PDB không bảo vệ khi readiness sai

PDB dựa trên pod health/availability. Nếu readiness probe false negative, Kubernetes có thể nghĩ service không đủ pod available và block disruption.

Vì vậy PDB phụ thuộc trực tiếp vào `REL-02`.

### 7.3. PDB không thay thế capacity

Khi một pod bị evict, pod còn lại phải đủ capacity giữ SLO. PDB chỉ giữ số pod tối thiểu, không đảm bảo pod còn lại chịu được traffic.

Vì vậy PDB phụ thuộc trực tiếp vào `REL-01`, capacity review và SLO evidence.

### 7.4. PDB không xử lý node chết đột ngột

Nếu node bị mất đột ngột, đó là involuntary disruption. PDB không ngăn được sự kiện này. Để chịu được node chết đột ngột cần replica, spread, readiness đúng và capacity đủ.

## 8. Kế hoạch rollout

Không tạo PDB cho toàn bộ service trong một thay đổi thiếu kiểm soát nếu runtime chưa quay lại `2/2`.

Thứ tự đề xuất:

1. Khôi phục và xác nhận `REL-01`: bảy critical services đạt `2/2 Ready`.
2. Xác nhận `REL-02`: readiness/liveness vẫn render đúng và không gây restart bất thường.
3. Render Helm với PDB templates hoặc manifests candidate.
4. Apply PDB theo batch nhỏ, ưu tiên service entry/revenue path:
    - Batch 1: `frontend-proxy`, `frontend`.
    - Batch 2: `checkout`, `cart`.
    - Batch 3: `payment`, `shipping`, `product-catalog`.
5. Sau mỗi batch, chạy verification.
6. Chỉ sau khi PDB ổn định mới dùng cho mandate demo node drain hoặc rolling-restart.

Không test drain production-style nếu chưa có dashboard SLO và rollback owner trong khung giờ thống nhất với mentor/team.

## 9. Verification và rollback

### 9.1. Verification trước implementation

```bash
kubectl -n techx-tf4 get pdb
kubectl -n techx-tf4 get deploy frontend-proxy frontend checkout cart payment shipping product-catalog
kubectl -n techx-tf4 get pods -o wide
```

Điều kiện để tiếp tục implementation:

- `get pdb` chưa có conflict với PDB cũ.
- Các service candidate đã `2/2`.
- Pod phân tán hợp lý và không có pod `Pending`/`CrashLoopBackOff`.

### 9.2. Verification sau implementation

```bash
kubectl -n techx-tf4 get pdb
kubectl -n techx-tf4 describe pdb <pdb-name>
kubectl -n techx-tf4 rollout status deploy/<service>
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 get events --sort-by=.lastTimestamp
```

Kỳ vọng:

- PDB xuất hiện cho từng candidate đã apply.
- `Allowed disruptions` hợp lý, không âm hoặc bằng 0 ngoài dự kiến.
- Service vẫn `Ready` và rollout không kẹt.
- Không có event `Cannot evict pod` hoặc rollout stuck sau khi apply.

### 9.3. Verification cho mandate drain/maintenance

Khi đã có approval và khung giờ demo:

1. Chụp baseline SLO dashboard trước test.
2. Thực hiện drain node hoặc rolling-restart theo kịch bản được approve.
3. Theo dõi:
    - checkout success rate.
    - browse/cart success rate.
    - storefront p95 latency.
    - pod availability và PDB `Allowed disruptions`.
4. Chụp dashboard trong và sau test.
5. Ghi lại Helm revision, kubectl commands và events.

### 9.4. Rollback

Nếu PDB làm kẹt rollout/drain:

1. Dừng drain hoặc rollout đang thực hiện nếu còn an toàn.
2. Xóa PDB của service bị ảnh hưởng hoặc rollback Helm revision gần nhất.
3. Xác nhận deployment quay lại `Ready`.
4. Kiểm tra events không còn eviction/drain block.
5. Ghi lại nguyên nhân và điều chỉnh `minAvailable`/batch trước lần thử tiếp theo.

Không tăng node group hoặc nới scheduling constraint trong lúc sự cố nếu chưa có CDO04/Tech Lead approval.

## 10. Các quyết định cần technical review

Nguyên cần xác nhận trước implementation:

- Danh sách bảy PDB candidates có đúng với customer/checkout path không.
- Baseline `minAvailable: 1` cho service có `replicas: 2` có phù hợp để bắt đầu không.
- Có service nào cần defer PDB vì readiness, rollout hoặc runtime behavior chưa đủ ổn định không.
- Thứ tự rollout theo batch có hợp lý không.
- Verification sau khi apply PDB đã đủ để chứng minh không làm kẹt rollout/drain chưa.
- Rollback bằng xóa PDB hoặc Helm rollback có đủ an toàn nếu drain/rollout bị block không.

## 11. Quan hệ với Mandate 3

Mandate 3 yêu cầu nhóm tự hẹn mentor và demo drain node hoặc rolling-restart mà customer flow không rớt SLO. PDB là một phần của guardrail cho kịch bản này, nhưng không phải điều kiện duy nhất.

Thứ tự đúng cho Mandate 3:

1. Readiness/liveness đúng để pod chưa sẵn sàng không nhận traffic.
2. Critical services có ít nhất hai replicas để không còn single-pod SPOF.
3. Pod được phân tán hợp lý để mất một node vẫn còn capacity.
4. PDB bảo vệ voluntary disruption để drain không evict quá nhiều pod cùng lúc.
5. SLO dashboard chứng minh browse/cart/checkout không rớt trong lúc demo.

Vì vậy `CDO08-REL-12` nên được xem là bước sau của `REL-01` và `REL-02`, không phải thay thế hai backlog đó.

## 12. Kết luận

Tất cả bảy critical services đều là PDB candidates vì nằm trên customer/checkout path và cần được bảo vệ khỏi voluntary disruption trong maintenance window. Tuy nhiên runtime hiện tại đang `1/1`, nên chưa được tạo PDB ngay.

Đề xuất baseline sau khi `REL-01` quay lại `2/2` và `REL-02` ổn định:

- Tạo PDB cho từng service critical.
- Dùng `minAvailable: 1` cho service có `replicas: 2`.
- Không tạo PDB cho workload single-replica.
- Rollout theo batch nhỏ và verify không block rollout/drain.

Cách tiếp cận này giữ đúng tinh thần production: không thêm policy chỉ để có YAML, mà chỉ bật PDB khi nó thật sự cải thiện maintenance safety và không làm kẹt vận hành.
