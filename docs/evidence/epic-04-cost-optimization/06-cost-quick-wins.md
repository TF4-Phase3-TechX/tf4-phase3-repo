# COST-06: Cost Quick Wins — Báo cáo Đánh giá & Kế hoạch Tối ưu Chi phí Hạ tầng

---

## Tóm tắt điều hành (Executive Summary)

Quá trình rà soát cấu hình `docker-compose.yml` và số liệu `docker stats` runtime cho thấy hạ tầng hiện đang **cấp phát dư thừa (over-provisioned)** ở nhiều service, đồng thời tồn tại một tiến trình sinh traffic giả lập (`load-generator`) chạy nền liên tục dù không phục vụ mục đích production.

**Tổng RAM limit có thể thu hồi ngay trong Tuần 1:** ước tính **~2.5 GB**, bao gồm:

| Hạng mục | RAM Limit thu hồi |
| :--- | ---: |
| Tắt autostart `load-generator` | ~1500 MiB |
| Hạ limit Jaeger (1.172 GiB → 300 MiB) | ~900 MiB |
| Hạ limit Prometheus (200 MiB → 100 MiB) | ~100 MiB |
| **Tổng cộng** | **~2500 MiB (≈ 2.5 GiB)** |

Đây là các thay đổi **rủi ro thấp, tác động cao (low-risk, high-impact)**, không yêu cầu thay đổi kiến trúc, có thể triển khai và rollback trong vài phút.

---

## 1. COST-06.1 — Rà soát Load Generator (Locust)

### 1.1 Hiện trạng cấu hình

| Thuộc tính | Giá trị | Nguồn |
| :--- | :--- | :--- |
| Enabled | `True` | Service `load-generator` khai báo trực tiếp trong `techx-corp-platform/docker-compose.yml` |
| Autostart | `True` | Biến `LOCUST_AUTOSTART=true` trong file `techx-corp-platform/.env` |
| RAM Limit | 1500 MiB | `techx-corp-platform/docker-compose.yml` → `deploy.resources.limits.memory` |
| Trạng thái vận hành | Chạy nền liên tục (24/7) | — |

#### Evidence: 
![Kiểm tra Load Generator](./runtime/screenshots/Kiểm%20tra%20load-generator%20autostart.png)


### 1.2 Đánh giá rủi ro

**a) Rủi ro về chi phí:**
- Service chiếm dụng mức Limit RAM rất cao (1500 MiB) nhưng chỉ thực sự cần thiết khi có nhu cầu test tải chủ động.
- Chạy 24/7 gây lãng phí tài nguyên hạ tầng đám mây (compute reserved không sử dụng), ảnh hưởng trực tiếp đến chi phí instance/cluster theo mô hình tính phí theo tài nguyên cấp phát.

**b) Rủi ro về độ chính xác của chỉ số hệ thống:**
- Traffic giả lập được tạo tự động và liên tục làm **tràn ngập hệ thống log/trace**.
- Gây nhiễu dữ liệu, làm sai lệch các biểu đồ đo lường SLO/SLI của người dùng thật trên Grafana → ảnh hưởng đến độ tin cậy của báo cáo giám sát và khả năng phát hiện anomaly thực tế.

### 1.3 Mức độ ưu tiên
🔴 **Cao** — Ảnh hưởng đồng thời cả chi phí lẫn độ tin cậy dữ liệu giám sát.

---

## 2. COST-06.2 — Đánh giá tài nguyên Observability Stack

### 2.1 Phương pháp đo lường
Số liệu thu thập bằng lệnh:
```bash
docker stats --no-stream
```
Đo lường tại thời điểm hệ thống vận hành ở trạng thái tải bình thường (steady-state), không trong lúc chạy load test.

> ⚠️ **Giới hạn của bằng chứng đo lường:** Số liệu `docker stats` ở trên chỉ phản ánh **steady-state evidence** (trạng thái tải bình thường), **chưa** phản ánh hành vi bộ nhớ khi hệ thống chịu peak traffic hoặc load test thực tế. Trước khi áp dụng chính thức các mức limit mới (đặc biệt với Jaeger), cần **validate lại dưới điều kiện tải** bằng một hoặc nhiều công cụ sau:
> - `kubectl top pod` / `kubectl top node` (nếu hạ tầng chạy trên Kubernetes)
> - Dashboard Grafana theo dõi memory theo thời gian thực trong lúc chạy load test có kiểm soát
> - Prometheus (`container_memory_usage_bytes` hoặc metric tương đương) để quan sát xu hướng và đỉnh (peak) sử dụng bộ nhớ theo thời gian, không chỉ một điểm dữ liệu tức thời.

### 2.2 Bảng số liệu Runtime thực tế

| Dịch vụ | RAM Tiêu thụ thực tế | RAM Limit hiện tại | % Sử dụng | Trạng thái đánh giá |
| :--- | ---: | ---: | ---: | :--- |
| **Jaeger** | 21.18 MiB | 1.172 GiB (~1200 MiB) | ~1.76% | 🔴 Over-provisioning nghiêm trọng |
| **OpenSearch** | 796.9 MiB | 1 GiB (1024 MiB) | ~77.82% | 🟡 Mức sử dụng cao, cần theo dõi |
| **Prometheus** | 38.57 MiB | 200 MiB | ~19.28% | 🟢 Thấp, an toàn — có thể tối ưu nhẹ |
| **Grafana** | 136.7 MiB | 175 MiB | ~78.13% | 🟡 Sát giới hạn, cần theo dõi |'

# Evidence: 
![Kiểm tra Observability Stack](./runtime/screenshots/kiem%20tra%20resource%20cua%20observability%20stack.png)

### 2.3 Phân tích chi tiết

**Jaeger — Over-provisioning nghiêm trọng nhất:**
Tỷ lệ sử dụng thực tế chỉ ~1.76% so với limit cấp phát. Đây là điểm lãng phí lớn nhất trong toàn bộ stack. Nguyên nhân khả dĩ: cấu hình limit được thiết lập theo giá trị mặc định/khuyến nghị chung mà chưa điều chỉnh theo khối lượng trace thực tế của hệ thống (đặc biệt sau khi tắt `load-generator`, lượng trace sẽ còn giảm thêm).

**OpenSearch & Grafana — Cần thận trọng:**
Cả hai đang ở ngưỡng 78-80% RAM limit. Đây **không phải** là ứng viên để cắt giảm ngay; ngược lại cần giám sát chặt để tránh nguy cơ OOM (Out of Memory) khi có peak traffic hoặc khi dữ liệu tăng trưởng theo thời gian.

**Prometheus — Dư địa tối ưu nhẹ:**
Sử dụng thực tế ~19% limit. Có thể giảm limit vừa phải (200 → 100 MiB) nhưng cần đối chiếu thêm với cấu hình `retention.time` vì retention dài sẽ làm tăng dung lượng dữ liệu on-disk/in-memory theo thời gian.

---

## 3. COST-06.3 — Cost Impact & Kế hoạch giảm thiểu (Mitigation Plan)

### 3.1 Tuần 1 — Quick Wins (Rủi ro thấp, triển khai ngay)

| # | Hành động | Thay đổi cấu hình | RAM thu hồi | Rủi ro | Owner | Trạng thái |
| :-: | :--- | :--- | ---: | :--- | :--- | :-- |
| 1 | Tắt autostart Load Generator | `LOCUST_AUTOSTART=true` → `false`; chuyển service sang khởi chạy thủ công (profile `manual` / `docker compose --profile load-test up`) | ~1500 MiB | Thấp | | ☐ |
| 2 | Hạ memory limit Jaeger | `1.172 GiB` → `250–300 MiB` | ~900 MiB | Thấp | | ☐ |
| 3 | Hạ memory limit Prometheus | `200 MiB` → `100 MiB` | ~100 MiB | Thấp | | ☐ |

**Memory headroom tiềm năng sau Bước 1 + Load Generator + Prometheus: ~2260 MiB**
**Memory headroom tiềm năng tối đa (nếu triển khai cả Bước 2 sau khi validate): ~2472 MiB**
 
> Không có hạng mục nào trong Tuần 1 tác động đến OpenSearch hoặc Grafana — hai service này bị loại khỏi phạm vi giảm limit của Tuần 1 (xem mục 3.2 và ghi chú tại 2.3).

#### Chi tiết triển khai kỹ thuật

**(1) Load Generator — chuyển sang manual trigger**

Trong `.env`:
```diff
- LOCUST_AUTOSTART=true
+ LOCUST_AUTOSTART=false
```

Khuyến nghị bổ sung `profiles` trong `techx-corp-platform/docker-compose.yml` để service không khởi động cùng `docker compose up` mặc định:
```yaml
services:
  load-generator:
    profiles: ["load-test"]
    deploy:
      resources:
        limits:
          memory: 1500M
```
Khi cần chạy load test chủ động:
```bash
docker compose --profile load-test up -d load-generator
```

**(2) Jaeger — hạ memory limit theo từng bước an toàn (staged rollout)**
 
Mặc dù mức sử dụng thực tế đo được chỉ ~21.18 MiB, việc hạ limit thẳng từ 1.2 GiB xuống 300 MiB trong một lần là **rủi ro không cần thiết** vì số liệu hiện có mới chỉ là steady-state evidence (xem mục 2.1). Khuyến nghị chia làm 2 bước:
 
**Bước 1 — Hạ về mức trung gian an toàn:**
```diff
services:
  jaeger:
    deploy:
      resources:
        limits:
-         memory: 1200M
+         memory: 512M
```
Sau khi áp dụng Bước 1, theo dõi tối thiểu **3-5 ngày** (bao gồm ít nhất một lần chạy load test có kiểm soát nếu có thể) các chỉ số:
- Container có bị `OOMKilled` / restart bất thường không
- Trace ingestion có bị drop/mất dữ liệu không (so sánh số lượng trace trước/sau)
- Xu hướng memory theo `kubectl top` / Grafana / Prometheus có ổn định dưới 512 MiB không
**Bước 2 — Chỉ thực hiện sau khi Bước 1 đã ổn định:**
```diff
services:
  jaeger:
    deploy:
      resources:
        limits:
-         memory: 512M
+         memory: 300M
```
> Bước 2 **không** thực hiện đồng thời với Bước 1. Đây là bước cân nhắc thêm, phụ thuộc vào kết quả giám sát thực tế sau Bước 1, không nằm trong cam kết "chắc chắn triển khai" của Tuần 1.

**(3) Prometheus — hạ memory limit**
```diff
services:
  prometheus:
    deploy:
      resources:
        limits:
-         memory: 200M
+         memory: 100M
```

#### Kế hoạch xác minh sau triển khai (Verification checklist)
- [ ] Chạy `docker stats --no-stream` sau 24h và 72h để xác nhận RAM tiêu thụ thực tế vẫn nằm trong limit mới, không có container bị `OOMKilled`.
- [ ] Kiểm tra `docker inspect <container> | grep OOMKilled` để đảm bảo không có sự cố memory.
- [ ] **Validate dưới tải** bằng `kubectl top` (nếu K8s), Grafana, hoặc Prometheus — không chỉ dựa vào `docker stats` steady-state — trước khi coi Bước 1 của Jaeger là "ổn định".
- [ ] Sau Bước 1 Jaeger (512 MiB), theo dõi tối thiểu 3-5 ngày trace ingestion không bị drop trước khi cân nhắc Bước 2 (300 MiB).
- [ ] Xác nhận dashboard Grafana không còn traffic giả lập từ load-generator (kiểm tra qua trace nguồn gốc request trong Jaeger).
- [ ] Đối chiếu với đội hạ tầng/billing: memory headroom thu được có được chuyển hóa thành thay đổi node count/instance type hay không — nếu không, ghi rõ trong báo cáo là "chưa có tiết kiệm chi phí trực tiếp trong kỳ billing hiện tại".

#### Kế hoạch rollback
Nếu phát sinh sự cố (OOM, mất trace/metric), rollback bằng cách khôi phục giá trị limit cũ trong `docker-compose.yml`/`.env` và chạy lại:
```bash
docker compose up -d --force-recreate jaeger prometheus
```

---

### 3.2 Tuần 2 — Giám sát & Đánh giá sâu hơn

| # | Hành động | Mục tiêu | Owner | Trạng thái |
| :-: | :--- | :--- | :--- | :-- |
| 1 | Giám sát OpenSearch & Grafana | Theo dõi biểu đồ RAM hàng ngày, giữ nguyên limit hiện tại (1 GiB / 175 MiB) để tránh OOM khi peak traffic | | ☐ |
| 2 | Tối ưu retention Prometheus | Đánh giá lại `retention.time=7d`; xem xét giảm nếu team không cần truy vết metric quá cũ, giúp giảm chi phí lưu trữ | | ☐ |

**Ghi chú :** OpenSearch và Grafana **không được giảm limit trong Tuần 1**, và cũng không nằm trong nhóm Quick Win. Lý do: mức sử dụng thực tế đo được đang tiệm cận ngưỡng cao (~78% limit hiện tại) — giảm limit ở giai đoạn này có rủi ro OOM đáng kể, đặc biệt khi có peak traffic hoặc dữ liệu tăng trưởng theo thời gian. Mọi điều chỉnh giảm limit ở hai service này (nếu có, trong tương lai) cần đi kèm dữ liệu giám sát dài hạn (>1-2 tuần) và chỉ nên xem xét khi mức sử dụng ổn định rõ ràng dưới ngưỡng an toàn (khuyến nghị <60-65%).
 
Gợi ý mở rộng cho Tuần 2 (nếu team có nhu cầu):
- Thiết lập alert Grafana khi RAM sử dụng của OpenSearch/Grafana vượt 85% limit.
- Đánh giá index lifecycle management (ILM) của OpenSearch để tự động xóa/nén index cũ, giảm áp lực bộ nhớ mà không cần tăng limit.
---

## 4. Tổng hợp tác động (Impact Summary)
 
| Chỉ số | Trước | Sau (dự kiến, Tuần 1 — Bước 1 Jaeger) | Chênh lệch |
| :--- | ---: | ---: | ---: |
| Tổng memory limit cấp phát (4 service liên quan) | ~3072 MiB | ~812 MiB | **-2260 MiB headroom tiềm năng (-74%)** |
| Load-generator chạy nền | Có (24/7) | Không (chỉ khi cần) | Loại bỏ nhiễu log/trace |
| Độ tin cậy dữ liệu SLO/SLI | Bị nhiễu bởi traffic giả lập | Phản ánh đúng người dùng thật | Cải thiện |
| Chi phí AWS thực tế (billing) | — | — | **Chưa thay đổi ngay** — chỉ là headroom ở cấp container; cần hành động ở cấp hạ tầng (giảm node, resize instance, bin-packing) để hiện thực hóa tiết kiệm chi phí |

---

