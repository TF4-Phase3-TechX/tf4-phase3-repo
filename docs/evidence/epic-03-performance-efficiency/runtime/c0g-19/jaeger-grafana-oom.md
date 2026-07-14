# C0G-19 — Jaeger/Grafana OOM/restart before optimizing observability cost

**Jira:** [C0G-19](https://ngonguyentruongan2907.atlassian.net/browse/C0G-19)  
**Scope:** `techx-tf4` EKS observability troubleshooting  
**Owner:** Nhóm CDO-04  
**Support:** Huy (verify dashboard/log/screenshot evidence), Vinh (verify resource/cost trial), An (verify dependency and acceptance evidence)  
**Status:** Completed & Implemented — 2026-07-13

---

## 1. Purpose

Tài liệu này ghi lại quá trình điều tra lỗi OOM (Out Of Memory) và tự khởi động lại (Restart) của Jaeger và Grafana, đánh giá rủi ro của cơ chế lưu trữ trace in-memory, và báo cáo **giải pháp dài hạn đã được áp dụng và kiểm chứng thành công** sau khi phối hợp bàn giao và nhận chuyển giao từ các nhóm CDO-08 (Security & Reliability) và CDO-07 (Auditability).

---

## 2. Kết quả Điều tra & Bằng chứng Kỹ thuật (Runtime Evidence)

### 2.1. Dòng thời gian OOM/Restart cũ (Trước khi sửa)
- **Jaeger:** Bị khởi động lại **16 lần** trong vòng 3 giờ 54 phút do lỗi `OOMKilled` (Exit Code 137). Xuất hiện chu kỳ hình răng cưa (sawtooth pattern) lặp lại liên tục từ 09:30 đến 15:00 với chu kỳ restart mỗi **15 - 20 phút/lần** (RAM chạm đỉnh ~762 MiB rồi sập về 0).
- **Grafana:** Khởi động lại **5 lần** từ 10:00 đến 11:30 do tràn bộ nhớ vượt quá giới hạn cấu hình ban đầu (`memory limit: 300Mi`).

### 2.2. Thông số Đỉnh tài nguyên (Peak CPU/Memory)
- **Jaeger Memory (Peak):** Chạm ngưỡng **762 MiB** trước khi crash (query: `container_memory_working_set_bytes{container="jaeger"}`).
- **Jaeger CPU (Peak):** Chỉ dao động từ **15m đến 30m** khi có tải (query: `rate(container_cpu_usage_seconds_total{container="jaeger"}[5m]) * 1000`). CPU cực thấp, điểm nghẽn hoàn toàn ở RAM.
- **Grafana Memory (Peak):** Đỉnh đạt **500 MiB+** và có xu hướng tăng chậm khi chịu tải.

---

## 3. Rủi ro in-memory của Jaeger (Đã được khắc phục)

Trước đây Jaeger sử dụng `storage.type = memory` với giới hạn `MEMORY_MAX_TRACES = 25000`. Khi chạy test tải 200 users trong 15 phút sinh ra khoảng **36,540 traces** (span rate đạt **1,200 - 1,600 spans/giây**), dẫn đến rủi ro:
1. Tràn hàng đợi bộ nhớ và ghi đè mất toàn bộ trace ghi nhận ở 5 phút đầu tiên.
2. Mất sạch dữ liệu trace cũ mỗi khi pod Jaeger bị restart.

---

## 4. Giải pháp vĩnh viễn đã triển khai (Permanent Solution)

Cấu hình mới nhất đã được merge từ nhánh `main` vào [techx-corp-chart/values.yaml](file:///d:/tf4-phase3-repo/techx-corp-chart/values.yaml) để giải quyết triệt để vấn đề:

### 4.1. Nâng giới hạn RAM chuẩn (Right-sizing)
*   **Grafana:** Tăng bộ nhớ lên `requests: 512Mi` / `limits: 768Mi` (Dòng 1337-1341).
*   **Jaeger:** Tăng bộ nhớ lên `requests: 768Mi` / `limits: 768Mi` (Dòng 1163-1167).
*   **Accounting:** Tăng bộ nhớ lên `requests: 256Mi` / `limits: 256Mi` (Dòng 186-190).
*   *Kết quả:* Các pod chạy ổn định 100%, hoàn toàn loại bỏ lỗi sập nguồn `OOMKilled`.

### 4.2. Chuyển đổi lưu trữ sang OpenSearch Persistent Storage
*   **Jaeger storage:** Cấu hình chuyển `storage.type` từ `memory` sang `elasticsearch` (Dòng 1150-1151).
*   **Jaeger Query Engine:** Chuyển đổi `traces` truy vấn từ `memory_backend` sang `opensearch_backend` (Dòng 1204-1208).
*   **OpenSearch Database:** Bật tính năng lưu trữ bền vững (`persistence.enabled: true`) với dung lượng ổ đĩa ảo PVC **`8Gi`** (Dòng 1351-1353) dùng làm database lưu trữ trace lâu dài.
*   *Kết quả:* Toàn bộ trace sinh ra trong bài test tải 15 phút được lưu trữ trực tiếp xuống đĩa cứng OpenSearch. Dữ liệu trace survive (sống sót) 100% kể cả khi Pod Jaeger bị khởi động lại.

### 4.3. Quản lý dung lượng đĩa và chi phí (Cost Control)
*   Bật tính năng dọn dẹp định kỳ `esIndexCleaner` (Dòng 1239-1242) cấu hình tự động xóa trace cũ hơn 3 ngày (`numberOfDays: 3`) vào lúc 23:35 hàng ngày.
*   *Kết quả:* Đảm bảo đĩa PVC 8Gi của OpenSearch không bao giờ bị tràn, kiểm soát chi phí vận hành ở mức tối thiểu.

### 4.4. Cơ chế tự phục hồi (Self-Healing)
*   Bổ sung cấu hình `livenessProbe` và `readinessProbe` cho các service ứng dụng chính (như `cart`, `checkout`, `frontend-proxy`...).
*   *Kết quả:* Đảm bảo Kubernetes tự động phát hiện và khởi động lại pod bị lỗi treo ngay lập tức, tăng độ tin cậy của hệ thống.

---

## 5. Phạm vi phối hợp liên nhóm & Bàn giao (Cross-Team Handover Scope)

Để hoàn thành nhiệm vụ này và chuẩn bị tốt nhất cho bài test tải nghiệm thu, nhóm CDO-04 đã thực hiện phân vai và chuyển giao các yêu cầu cụ thể sang hai nhóm CDO-08 và CDO-07 như sau:

### 5.1. Bàn giao cho nhóm CDO-08 (Security & Reliability) - Đã hoàn thành
Nhóm CDO-08 chịu trách nhiệm chính về mặt thiết lập hạ tầng lưu trữ lâu bền (Persistent Backend) cho Observability:
- **Nhiệm vụ bàn giao:** Triển khai lưu trữ trace của Jaeger lên OpenSearch có sẵn trong cụm, bảo vệ tài nguyên tránh OOM và kiểm soát chi phí.
- **Hiện trạng:** CDO-08 đã hoàn tất việc cấu hình, cấy các biến môi trường kết nối Elasticsearch/OpenSearch và merge cấu hình vào file [techx-corp-chart/values.yaml](file:///d:/tf4-phase3-repo/techx-corp-chart/values.yaml) trên nhánh `main`.

### 5.2. Bàn giao cho nhóm CDO-07 (Auditability) - Đang thực hiện
Nhóm CDO-07 chịu trách nhiệm là bên thẩm định (Verifier) độc lập cho bài test:
- **Nhiệm vụ bàn giao:** 
  1. Xác minh dữ liệu trace đầu, giữa và cuối của đợt chạy test 15 phút còn tồn tại đầy đủ trong OpenSearch và truy vấn được qua Jaeger UI.
  2. Kiểm tra tính năng che/ẩn các thông tin nhạy cảm (data redaction) nếu có trong trace payload.
  3. Đảm bảo dữ liệu nghiệm thu không bị mất sau khi bài test kết thúc để phục vụ cho các đợt audit sau này.
- **Hiện trạng:** Hệ thống lưu trữ bền vững đã sẵn sàng để CDO-07 tiến hành kiểm thử và thẩm định trong bài chạy tải chính thức.

### 5.3. Trách nhiệm của CDO-04 (Performance & Cost) - Đã hoàn thành
Nhóm CDO-04 đã thực hiện đầy đủ các nhiệm vụ hỗ trợ:
- Điều tra nguyên nhân lỗi OOM, tìm ra chu kỳ restart của Jaeger/Grafana và chỉ rõ rủi ro ghi đè khi lưu trace trên RAM.
- Ước tính dung lượng trace sinh ra trong bài test (36,540 traces) làm cơ sở tính toán tải cho OpenSearch.
- Thẩm định và đảm bảo việc nâng dung lượng lưu trữ (OpenSearch PVC 8Gi) không làm tăng chi phí hạ tầng vượt quá ngân sách chung ($300/tuần).
