# CDO08-REL-29 AZ Failure Gap Register

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-29
**Ngày ghi nhận:** 2026-07-28
**Scope tham chiếu:** `docs/cdo08/week3/mandate21/adr/CDO08-REL-28-revenue-path-scope.md`

Tài liệu này phân loại các gap quan sát được từ runtime baseline trước khi quyết định scale/topology/PDB cho Mandate 21. Đây là gap register audit/decision input, không phải implementation plan.

Baseline nguồn:

```text
docs/cdo08/week3/mandate21/scan/CDO08-REL-29-multi-az-runtime-baseline.md
```

---

## 1. Severity Model

| Severity | Ý nghĩa                                                                                                                 |
| -------- | ----------------------------------------------------------------------------------------------------------------------- |
| Critical | Mất 1 AZ có khả năng làm đứt trực tiếp revenue path hoặc mất dữ liệu/khả năng ghi dữ liệu cần RPO 0                     |
| High     | Mất 1 AZ có khả năng degrade đáng kể hoặc làm mất thành phần dữ liệu/async quan trọng; cần owner quyết định trước drill |
| Medium   | Không trực tiếp làm sập browse/cart/checkout nhưng ảnh hưởng readiness, drill driver, observability hoặc archive RPO    |
| Low      | Drift/health note cần theo dõi, chưa đủ evidence gây failure                                                            |

Scope note:

- REL-29 chỉ ghi baseline/gap, không scale hoặc sửa topology ngay.
- Single replica không tự động đồng nghĩa phải scale; mỗi gap cần phân loại impact trước.

---

## 2. Gap Register

| ID           | Gap                                                                                     | Evidence runtime                                                                                                                                                      | Impact khi mất AZ                                                                                                                                             | Severity     | Recommended next action                                                                                                                              |
| ------------ | --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| REL29-GAP-01 | `cart` có 2 replicas nhưng cả 2 pods đang nằm ở `us-east-1a`                            | `cart-55b7847dbb-4z57w` và `cart-55b7847dbb-hts4x` đều chạy trên node `ip-10-0-10-182`, AZ `us-east-1a`                                                               | Nếu mất `us-east-1a`, toàn bộ pod `cart` hiện tại mất cùng lúc; browse/cart/checkout path có thể fail cho cart operations dù deployment desired replicas là 2 | **Critical** | REL32/implementation task cần điều chỉnh topology/placement cho `cart` trước drill; không chỉ tăng replica nếu scheduler vẫn có thể dồn cùng AZ      |
| REL29-GAP-02 | `accounting` chỉ 1 replica, ở `us-east-1b`, strategy `Recreate`                         | `accounting-6f4f696586-84hf9`, AZ `us-east-1b`; deployment `replicas=1`, strategy `Recreate`; no HPA/PDB observed                                                     | Nếu mất `us-east-1b`, accounting consumer/service mất cho tới khi reschedule; ảnh hưởng post-checkout data path/RPO accounting tùy cách app ghi nhận order    | **High**     | Phân loại accounting có nằm trong RPO 0 order-data path của Mandate 21 hay không; nếu có, cần HA/topology/PDB riêng                                  |
| REL29-GAP-03 | `fraud-detection` chỉ 1 replica, ở `us-east-1b`, strategy `Recreate`                    | `fraud-detection-d99b9b5d5-z8xxk`, AZ `us-east-1b`; deployment `replicas=1`, strategy `Recreate`; no HPA/PDB observed                                                 | Nếu mất `us-east-1b`, fraud async consumer/service mất cho tới khi reschedule; có thể tạo lag hoặc mất khả năng xử lý event nếu state/offset không an toàn    | **High**     | Phân loại fraud-detection là async non-blocking hay required order-data path; nếu required, cần HA/topology riêng                                    |
| REL29-GAP-04 | `kafka-connect-orders-archive` chỉ 1 replica, ở `us-east-1b`                            | `kafka-connect-orders-archive-7d948c46f7-75zj9`, AZ `us-east-1b`; deployment `replicas=1`; no HPA/PDB observed                                                        | Nếu mất `us-east-1b`, MSK archive tạm dừng tới khi reschedule; request path không đứt nhưng archive RPO có thể vượt mục tiêu nếu recovery chậm                | **Medium**   | Ghi nhận là backup/archive path; cần quyết định RPO archive trong AZ-loss drill và khả năng tự reschedule trong RTO                                  |
| REL29-GAP-05 | `load-generator` chỉ 1 replica, ở `us-east-1b`                                          | `load-generator-589b5df7f7-sm4rd`, AZ `us-east-1b`; deployment `replicas=1`; no HPA/PDB observed                                                                      | Nếu mentor làm mất `us-east-1b`, drill traffic source có thể mất, khiến phép đo SLO/RTO bị gián đoạn dù customer path có thể vẫn ổn                           | **Medium**   | Trước drill cần quyết định load-generator có cần HA/placement sang AZ khác hay dùng external driver; đây là test-driver risk                         |
| REL29-GAP-06 | `product-reviews` desired 2 nhưng chỉ 1 pod Ready; pod ở `us-east-1b` not Ready/BackOff | `product-reviews` deployment `1/2`; pod `product-reviews-745fc8cf6b-r8fhn` Running `Ready=False`; events có readiness timeout và BackOff; PDB allowed disruptions `0` | Không trực tiếp core checkout path, nhưng làm `techx-corp` Progressing và làm baseline trước drill không clean                                                | **Medium**   | Owner service cần fix readiness/runtime hoặc xác nhận product-reviews out-of-scope cho revenue-path AZ drill                                         |
| REL29-GAP-07 | `techx-corp` Argo health `Progressing` trước drill                                      | Argo output: `techx-corp sync=Synced health=Progressing op=Succeeded`                                                                                                 | Drill baseline không hoàn toàn healthy; nếu SLO dip xảy ra, khó tách AZ failure với workload đang progressing                                                 | **Medium**   | Cần đưa `techx-corp` về Healthy hoặc ghi waiver rõ nếu component progressing ngoài revenue path                                                      |
| REL29-GAP-08 | `techx-raw` Argo `OutOfSync`                                                            | Argo output: `techx-raw sync=OutOfSync health=Healthy`                                                                                                                | Raw infra/policy drift có thể gây nhiễu audit readiness; trước đó từng thấy drift NetworkPolicy ngoài scope                                                   | **Low**      | Ghi nhận drift và xác nhận resource out-of-scope trước drill; không block nếu drift không ảnh hưởng revenue path                                     |
| REL29-GAP-09 | Chỉ observed 2 AZ trong cluster snapshot                                                | Nodes chỉ ở `us-east-1a` và `us-east-1b`; không thấy node `us-east-1c`                                                                                                | Mất 1 AZ vẫn có thể chịu được nếu workload trải đều 2 AZ; nhưng không có margin AZ thứ ba, và các dồn placement như `cart` trở nên nguy hiểm hơn              | **Medium**   | REL32 cần quyết định 2-AZ posture có đủ theo budget/RTO không, hoặc có cần third-AZ node capacity tối thiểu                                          |
| REL29-GAP-10 | Một số service dùng zone topology `ScheduleAnyway`, không hard block dồn AZ             | Deployment topology scan cho nhiều services có `topology.kubernetes.io/zone`, `maxSkew=1`, `whenUnsatisfiable=ScheduleAnyway`; `cart` đang dồn 2 pods vào `1a`        | Scheduler có thể vẫn tạo placement không chống AZ-loss trong điều kiện constraint/resource cụ thể                                                             | **High**     | Không kết luận chỉ cần "đã có topology spread"; cần kiểm tra service-by-service và cân nhắc `DoNotSchedule` hoặc hard anti-affinity cho revenue path |

---

## 3. Revenue Path Risk View

| Layer                         | Current state                                                         | AZ-loss concern                              | Gap IDs                    |
| ----------------------------- | --------------------------------------------------------------------- | -------------------------------------------- | -------------------------- |
| Entry                         | `frontend-proxy` 2 replicas across `1a/1b`, PDB allowed `1`           | Baseline tốt                                 | None observed              |
| Frontend                      | `frontend` 2 replicas across `1a/1b`, HPA 2/6, PDB allowed `1`        | Baseline tốt                                 | None observed              |
| Cart                          | `cart` 2 replicas, HPA 2/4, PDB allowed `1`, but both pods in `1a`    | Losing `1a` can remove all cart pods         | REL29-GAP-01               |
| Checkout                      | `checkout` 2 replicas across `1a/1b`, HPA 2/3, PDB allowed `1`        | Baseline tốt                                 | None observed              |
| Product catalog               | `product-catalog` 2 replicas across `1a/1b`, HPA 2/4, PDB allowed `1` | Baseline tốt                                 | None observed              |
| Payment                       | `payment` 2 replicas across `1a/1b`, PDB allowed `1`                  | No HPA observed, but placement baseline tốt  | None observed              |
| Shipping/Quote/Currency/Email | 2 replicas across `1a/1b`                                             | Baseline tốt                                 | None observed              |
| Async order data              | `accounting`, `fraud-detection` single replica in `1b`                | Losing `1b` interrupts async data processing | REL29-GAP-02, REL29-GAP-03 |
| Archive/backup                | `kafka-connect-orders-archive` single replica in `1b`                 | Losing `1b` pauses archive until reschedule  | REL29-GAP-04               |
| Drill driver                  | `load-generator` single replica in `1b`                               | Losing `1b` can stop live load source        | REL29-GAP-05               |

---

## 4. Capacity / Quota Impact Notes

Current quota headroom:

| Resource        |     Headroom |
| --------------- | -----------: |
| pods            |           14 |
| requests.cpu    |        1710m |
| requests.memory | khoảng 4.9Gi |
| limits.cpu      |        4600m |
| limits.memory   | khoảng 4.3Gi |

Implication:

- Có headroom để xử lý một số gap có chọn lọc.
- Không nên scale toàn bộ service bừa bãi; CPU request headroom còn khoảng 1.71 core.
- REL32 nên ưu tiên gap theo risk: `cart` placement trước, sau đó single-replica data/archive/drill-driver theo impact.

---

## 5. Non-Gap / Positive Baseline

Các thành phần sau đã có baseline tốt trong snapshot này:

| Service           | Evidence                                        |
| ----------------- | ----------------------------------------------- |
| `frontend-proxy`  | 2 pods across `1a/1b`, PDB allowed `1`, HPA 2/4 |
| `frontend`        | 2 pods across `1a/1b`, PDB allowed `1`, HPA 2/6 |
| `checkout`        | 2 pods across `1a/1b`, PDB allowed `1`, HPA 2/3 |
| `currency`        | 2 pods across `1a/1b`, PDB allowed `1`, HPA 2/3 |
| `payment`         | 2 pods across `1a/1b`, PDB allowed `1`          |
| `product-catalog` | 2 pods across `1a/1b`, PDB allowed `1`, HPA 2/4 |
| `quote`           | 2 pods across `1a/1b`, PDB allowed `1`          |
| `shipping`        | 2 pods across `1a/1b`, PDB allowed `1`          |
| `email`           | 2 pods across `1a/1b`, PDB allowed `1`          |

---

## 6. Recommended Review Order

1. Confirm `cart` is Critical for REL32 because current placement is not AZ-tolerant.
2. Decide whether `accounting` and `fraud-detection` are in-scope for RPO 0 order-data path under Mandate 21.
3. Decide whether `kafka-connect-orders-archive` must stay continuously available during AZ loss, or whether short reschedule lag is acceptable.
4. Decide how live load will be generated if `load-generator` AZ is lost.
5. Clean or explicitly waive `product-reviews` and Argo health drift before mentor drill.
6. Only after the above, implement targeted scale/topology/PDB changes in separate task/PR.

---

## 7. Out Of Scope For REL-29

REL-29 không thực hiện các thay đổi sau:

- Không scale deployment.
- Không thay đổi HPA.
- Không thay đổi PDB.
- Không thay đổi topology spread hoặc anti-affinity.
- Không restart workload.
- Không chạy AZ failure drill.

Các thay đổi implement sẽ đi vào task sau, dựa trên baseline/gap register này.
