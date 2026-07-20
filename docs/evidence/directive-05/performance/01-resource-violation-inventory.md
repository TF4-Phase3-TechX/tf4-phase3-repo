# Bảng kê phân tích cấu hình tài nguyên (Resource Violation Inventory)

* **Trạng thái:** Hoàn thành khảo sát thực tế (Đã verify bằng live `kubectl top pod --containers` và Pod specs từ EKS).
* **Người thực hiện:** An (CDO-04) & Ninh (CDO-04).
* **Ngày tổng hợp:** 16/07/2026.
* **Mục tiêu:** Quét toàn bộ Deployment, StatefulSet, DaemonSet, Job, CronJob (bao gồm container chính, initContainers và sidecars) trong cả 2 namespace `techx-tf4` và `techx-observability`.

---

## I. TỔNG HỢP TRẠNG THÁI (SUMMARY VERDICT)

| Mức độ Severity | Số lượng | Mô tả hành động cần thiết |
| :--- | :---: | :--- |
| **`Blocker`** | 0 | Không có lỗi logic (như Request > Limit) hoặc HPA thiếu CPU request. |
| **`High risk`** | 1 | CPU/Memory cấu hình không cân xứng nghiêm trọng với tải thực tế của `opensearch-0` (RAM thực tế gấp ~8.8 lần request). |
| **`Needs tuning`** | 3 | Workload vượt quá request cơ bản (`payment` pods) hoặc có sự khác biệt giữa baseline và peak load (`kafka` chạm limit khi tải cao nhưng thấp khi chạy thường). |
| **`Compliant`** | 26 | Cấu hình hợp lý và đầy đủ requests/limits. |

---

## II. BẢNG KÊ KHAI WORKLOAD INVENTORY (ALL WORKLOADS)

Bảng dưới đây thống kê toàn bộ các container và cấu hình tài nguyên đối chiếu với observed usage thực tế:

| Workload / Pod | Container | Type | CPU Req / Limit | Memory Req / Limit | Observed Usage (CPU/Memory) | Severity | Rationale (Lý giải) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`opensearch`** | `opensearch` | App | `1000m` / `1000m` | `100Mi` / `1100Mi` | `130m` / `882Mi` | **High Risk** | Xác nhận nguy cơ cao. RAM thực tế (`882Mi`) chiếm ~80% limit và gấp **~8.8 lần** request. Scheduler chỉ dự phòng `100Mi` gây rủi ro lập lịch sai trên Node. Cần nâng RAM request lên ít nhất `768Mi`. |
| **`kafka`** | `kafka` | App | `100m` / `500m` | `700Mi` / `700Mi` | `21m` / `501Mi` | **Needs tuning** | Ở chế độ thường (baseline), CPU chạy thấp (`21m`) và RAM dùng ~72% limit (`501Mi`). Tuy nhiên lúc test tải cao, CPU đã có lịch sử chạm đỉnh limit `500m` gây nghẽn. Cần tăng CPU request/limit lên `300m`/`800m`. |
| **`payment pod 1`** | `payment` | App | `50m` / `200m` | `64Mi` / `128Mi` | `11m` / `86Mi` | **Needs tuning** | RAM thực tế (`86Mi`) vượt quá request `64Mi` (vượt 22Mi). Cần nâng RAM request lên `96Mi`. |
| **`payment pod 2`** | `payment` | App | `50m` / `200m` | `64Mi` / `128Mi` | `14m` / `93Mi` | **Needs tuning** | RAM thực tế (`93Mi`) vượt quá request `64Mi` (vượt 29Mi). Cần nâng RAM request lên `96Mi`. |
| **`accounting`** | `accounting` | App | `50m` / `200m` | `256Mi` / `256Mi` | `8m` / `111Mi` | **Compliant** | Hoạt động bình thường. |
| **`accounting`** | `wait-for-kafka` | Init | `5m` / `25m` | `8Mi` / `32Mi` | < 1m / ~1Mi | **Compliant** | Init container siêu nhẹ (Exception). |
| **`ad`** | `ad` | App | `50m` / `200m` | `150Mi` / `300Mi` | `2m` / `215Mi` | **Compliant** | Hoạt động bình thường. |
| **`cart`** | `cart` | App | `75m` / `300m` | `96Mi` / `192Mi` | `66m` / `40Mi` | **Compliant** | Hoạt động bình thường. |
| **`cart`** | `wait-for-valkey` | Init | `5m` / `25m` | `8Mi` / `32Mi` | < 1m / ~1Mi | **Compliant** | Exception. |
| **`checkout`** | `checkout` | App | `75m` / `300m` | `48Mi` / `96Mi` | `3m` / `12Mi` | **Compliant** | HPA dùng CPU mapping thành công với CPU request `75m`. |
| **`checkout`** | `wait-for-kafka` | Init | `5m` / `25m` | `8Mi` / `32Mi` | < 1m / ~1Mi | **Compliant** | Exception. |
| **`currency`** | `currency` | App | `75m` / `300m` | `96Mi` / `192Mi` | `2m` / `16Mi` | **Compliant** | HPA dùng CPU mapping thành công với CPU request `75m`. |
| **`email`** | `email` | App | `20m` / `100m` | `50Mi` / `100Mi` | `2m` / `51Mi` | **Compliant** | Usage sát request nhưng chưa vượt limit. |
| **`flagd`** | `flagd` | App | `20m` / `100m` | `40Mi` / `75Mi` | `2m` / `23Mi` | **Compliant** | Hoạt động bình thường. |
| **`flagd`** | `wait-for-kafka` | Init | `5m` / `25m` | `8Mi` / `32Mi` | < 1m / ~1Mi | **Compliant** | Exception. |
| **`fraud-detection`** | `fraud-detection` | App | `50m` / `200m` | `150Mi` / `300Mi` | `2m` / `150Mi` | **Compliant** | Hoạt động bình thường. |
| **`fraud-detection`** | `wait-for-kafka` | Init | `5m` / `25m` | `8Mi` / `32Mi` | < 1m / ~1Mi | **Compliant** | Exception. |
| **`frontend`** | `frontend` | App | `100m` / `400m` | `192Mi` / `320Mi` | `19m` / `74Mi` | **Compliant** | HPA dùng CPU mapping thành công với CPU request `100m`. |
| **`frontend-proxy`** | `frontend-proxy` | App | `50m` / `200m` | `64Mi` / `128Mi` | `6m` / `17Mi` | **Compliant** | Hoạt động bình thường. |
| **`image-provider`** | `image-provider` | App | `10m` / `50m` | `25Mi` / `50Mi` | `1m` / `4Mi` | **Compliant** | Hoạt động bình thường. |
| **`llm`** | `llm` | App | `75m` / `250m` | `96Mi` / `192Mi` | `14m` / `68Mi` | **Compliant** | Hoạt động bình thường. |
| **`load-generator`** | `load-generator` | App | `300m` / `600m` | `256Mi` / `512Mi` | `15m` / `108Mi` | **Compliant** | Hoạt động bình thường. |
| **`postgresql`** | `postgresql` | App | `50m` / `500m` | `256Mi` / `512Mi` | `6m` / `44Mi` | **Compliant** | Cần theo dõi thêm do postgres từng bị OOM sau bài test tải. |
| **`product-catalog`** | `product-catalog` | App | `50m` / `200m` | `32Mi` / `64Mi` | `3m` / `12Mi` | **Compliant** | Hoạt động bình thường. |
| **`product-reviews`** | `product-reviews` | App | `75m` / `300m` | `96Mi` / `192Mi` | `12m` / `66Mi` | **Compliant** | Hoạt động bình thường. |
| **`quote`** | `quote` | App | `10m` / `50m` | `20Mi` / `40Mi` | `1m` / `15Mi` | **Compliant** | Hoạt động bình thường. |
| **`recommendation`** | `recommendation` | App | `75m` / `300m` | `128Mi` / `256Mi` | `11m` / `40Mi` | **Compliant** | Hoạt động bình thường. |
| **`shipping`** | `shipping` | App | `20m` / `75m` | `16Mi` / `32Mi` | `1m` / `2Mi` | **Compliant** | Hoạt động bình thường. |
| **`valkey-cart`** | `valkey-cart` | App | `20m` / `100m` | `32Mi` / `64Mi` | `3m` / `4Mi` | **Compliant** | Hoạt động bình thường. |
| **`otel-collector`** | `opentelemetry-collector` | App | `50m` / `200m` | `100Mi` / `200Mi` | `69m` / `145Mi` | **Compliant** | Workload chạy DaemonSet. |
| **`grafana`** | `grafana` | App | `100m` / `500m` | `512Mi` / `768Mi` | `10m` / `431Mi` | **Compliant** | Hoạt động bình thường. |
| **`grafana`** | `grafana-sc-alerts` | Sidecar | `20m` / `150m` | `64Mi` / `256Mi` | < 1m / ~5Mi | **Compliant** | Hoạt động bình thường. |
| **`jaeger`** | `jaeger` | App | `100m` / `500m` | `768Mi` / `768Mi` | `23m` / `22Mi` | **Compliant** | Cần theo dõi thêm do jaeger từng bị OOM sau bài test tải. |
| **`metrics-server`** | `metrics-server` | App | `50m` / `100m` | `100Mi` / `200Mi` | `4m` / `24Mi` | **Compliant** | Hoạt động bình thường. |
| **`prometheus`** | `prometheus-server` | App | `100m` / `500m` | `1Gi` / `1Gi` | `52m` / `516Mi` | **Compliant** | Hoạt động bình thường. |
| **`alertmanager`** | `alertmanager` | App | `10m` / `100m` | `50Mi` / `100Mi` | `6m` / `17Mi` | **Compliant** | Hoạt động bình thường. |

---

## III. DANH SÁCH NGOẠI LỆ ĐÃ ĐƯỢC DUYỆT (EXCEPTIONS)

Một số container chạy tác vụ nền, phụ trợ siêu nhẹ hoặc chạy tức thời được miễn trừ khỏi yêu cầu tối ưu hóa CPU/RAM (được giữ baseline thấp):

1.  **Các Init Containers chờ dịch vụ (`wait-for-kafka`, `wait-for-valkey`)**:
    *   *Mô tả*: Chỉ chạy trong 2-3 giây đầu để kiểm tra cổng kết nối (netcat).
    *   *Cấu hình ngoại lệ*: Cấp CPU request `5m` / limit `25m`, RAM `8Mi` / limit `32Mi` (Đạt an toàn tối thiểu).
2.  **StatefulSet Init Containers (`fsgroup-volume`, `configfile` của opensearch)**:
    *   *Cấu hình ngoại lệ*: CPU request `10m` / limit `50m`, RAM `32Mi` / limit `64Mi`.

---

## IV. BẰNG CHỨNG TỪ RENDERED MANIFEST (EVIDENCE LINKS)

Để đối chiếu chi tiết cấu hình tài nguyên khai báo, vui lòng tham khảo các tệp tin kết xuất trực tiếp trong IDE:
*   Cấu hình ứng dụng chi tiết: [rendered-app.yaml](../../../../note/mandate/rendered-app.yaml)
*   Cấu hình giám sát chi tiết: [rendered-observability.yaml](../../../../note/mandate/rendered-observability.yaml)

---

## V. MINH CHỨNG HÌNH ẢNH THỰC TẾ (VISUAL EVIDENCE)

Dưới đây là các hình ảnh ghi lại kết quả rà soát thực tế trên cụm EKS:

### 1. Minh chứng sử dụng tài nguyên thực tế (`kubectl top`)
![Ảnh 1: Kết quả chạy lệnh kubectl top pods](file:///d:/Phase3_Xbrain/tf4-phase3-repo/docs/evidence/directive-05/performance/image/image.png)

### 2. Biểu đồ Resource Saturation trên Grafana
![Ảnh 2: Biểu đồ CPU & Memory Usage thực tế so với đường Limits](file:///d:/Phase3_Xbrain/tf4-phase3-repo/docs/evidence/directive-05/performance/image/image1.png)

### 3. Trạng thái hoạt động của HPA
![Ảnh 3: Trạng thái get HPA hiển thị đầy đủ phần trăm CPU Target](file:///d:/Phase3_Xbrain/tf4-phase3-repo/docs/evidence/directive-05/performance/image/image2.png)

### 4. Cấu hình tài nguyên trong Rendered Manifest (IDE)
![Ảnh 4: Khai báo CPU/Memory của container chính và init container trong rendered-app.yaml](file:///d:/Phase3_Xbrain/tf4-phase3-repo/docs/evidence/directive-05/performance/image/image3.png)

