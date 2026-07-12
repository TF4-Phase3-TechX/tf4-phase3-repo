# COST-06: Cost Quick Wins — Báo cáo Đánh giá & Kế hoạch Tối ưu Chi phí Hạ tầng

---

## Tóm tắt điều hành (Executive Summary)

Quá trình rà soát hiện tại chỉ có thể khẳng định được một số điều từ cấu hình code thực tế trong repo, chứ chưa thể kết luận rằng các service observability có thể giảm limit ngay. Trong repo hiện có hai nguồn cấu hình riêng biệt: Docker Compose và Helm chart. Với Helm chart, `load-generator` hiện được cấu hình với `LOCUST_AUTOSTART=true` và limit memory `1500Mi` trong `techx-corp-chart/values.yaml`; **Jaeger có limit `600Mi`**; `prometheus` có limit `400Mi`; `grafana` có limit `300Mi`; `opensearch` có limit `1100Mi`. Ngoài ra, dữ liệu vận hành thực tế vẫn ghi nhận Jaeger từng bị `OOMKilled`, nên báo cáo này **không đề xuất giảm limit** cho Jaeger.

Do đó, báo cáo này **không đề xuất giảm limit** cho Jaeger/Prometheus/OpenSearch/Grafana. Với riêng Jaeger, dữ liệu hiện có (OOMKilled) là lý do để **loại hẳn khỏi danh sách ứng viên giảm limit** và chuyển sang diện cần điều tra/tăng. Nếu runtime cho thấy `OOMKilled`, restart liên tục, hoặc mức sử dụng gần sát giới hạn trong thời gian dài ở các service khác, hành động phù hợp cũng là giám sát, kiểm tra log và điều tra nguyên nhân trước khi thay đổi cấu hình.

**Tóm lại, hướng tiếp cận theo nguyên tắc evidence-first:**

1. Tắt autostart của `load-generator` — đây là thay đổi có thể thực hiện ngay dựa trên cấu hình code và không phụ thuộc vào số liệu runtime.
2. Điều tra nguyên nhân Jaeger bị `OOMKilled` ở mức 600 MiB hiện tại — ưu tiên trước khi xem xét bất kỳ thay đổi limit nào khác cho service này.
3. Thu thập dữ liệu vận hành thực tế trong 48–72 giờ (memory usage, restart count, `OOMKilled`, traffic thực tế) trước khi đề xuất bất kỳ thay đổi limit nào cho Prometheus/OpenSearch/Grafana.
4. Chỉ sau khi có đủ bằng chứng — kèm trích dẫn chính xác file và dòng cấu hình — mới đề xuất thay đổi limit, đi cùng kế hoạch rollback.

---

## 1. COST-06.1 — Rà soát Load Generator (Locust)

### 1.1 Hiện trạng cấu hình

| Thuộc tính | Giá trị | Nguồn (File:Dòng) |
| :--- | :--- | :--- |
| Enabled | `True` | `techx-corp-chart/values.yaml` — `load-generator.enabled: true` (*498*); `techx-corp-platform/docker-compose.yml` — service `load-generator` tồn tại (*410*) |
| Autostart | `True` | `techx-corp-chart/values.yaml` — `LOCUST_AUTOSTART` (*519*); `techx-corp-platform/.env` — biến `LOCUST_AUTOSTART=true` (*104*) |
| RAM Limit | 1500 MiB | `techx-corp-chart/values.yaml` — `resources.limits.memory: 1500Mi` (*535*); `techx-corp-platform/docker-compose.yml` — `memory: 1500M` (*421*) |
| Trạng thái vận hành | Chạy nền liên tục (24/7) | — |

#### Evidence:

![Kiểm tra Load Generator](./runtime/screenshots/Kiểm%20tra%20load-generator%20autostart.png)


### 1.2 Đánh giá rủi ro

**a) Rủi ro về chi phí:**

- Service chiếm dụng mức Limit RAM rất cao (1500 MiB) nhưng chỉ thực sự cần thiết khi có nhu cầu test tải chủ động.
- Chạy 24/7 gây lãng phí tài nguyên hạ tầng đám mây (compute reserved không sử dụng), ảnh hưởng trực tiếp đến chi phí instance/cluster theo mô hình tính phí theo tài nguyên cấp phát.

**b) Rủi ro về độ chính xác của chỉ số hệ thống:**

- Traffic giả lập được tạo tự động và liên tục làm tràn ngập hệ thống log/trace.
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

> ⚠️ **Giới hạn của bằng chứng đo lường:** Số liệu `docker stats` chỉ phản ánh **steady-state evidence** (trạng thái tải bình thường), **chưa** phản ánh hành vi bộ nhớ khi hệ thống chịu peak traffic hoặc load test thực tế — và quan trọng hơn, **không tự phát hiện được các sự kiện `OOMKilled` đã xảy ra trong quá khứ** như trường hợp Jaeger. Trước khi áp dụng bất kỳ mức limit mới nào, cần kiểm tra thêm:
>
> - `docker inspect <container> --format '{{.State.OOMKilled}}'` và lịch sử restart (`docker inspect <container> --format '{{.RestartCount}}'`)
> - `kubectl describe pod` và `kubectl logs --previous` để xem restart reason, event OOM và log trước khi container chết
> - Dashboard Grafana theo dõi memory theo thời gian thực trong lúc chạy load test có kiểm soát
> - Prometheus (`container_memory_usage_bytes`, `container_oom_events_total` hoặc metric tương đương) để quan sát xu hướng và đỉnh (peak) sử dụng bộ nhớ theo thời gian

### 2.2 Bằng chứng hiện có từ cấu hình code và vận hành thực tế

Bản báo cáo này không có đầy đủ số liệu runtime về memory usage dưới tải cho Prometheus/OpenSearch/Grafana. Riêng Jaeger đã có bằng chứng vận hành thực tế (OOMKilled). Các giá trị dưới đây phải được xem là điểm bắt đầu cho giám sát, kèm trích dẫn vị trí trong code — chưa phải căn cứ để cắt giảm.

| Dịch vụ | Limit hiện tại | Nguồn (File:Dòng) | Bằng chứng vận hành | Ý nghĩa |
| :--- | ---: | :--- | :--- | :--- |
| **Jaeger** | **600Mi** | `techx-corp-chart/values.yaml` — `resources.limits.memory: 600Mi` (*1058*) | ⚠️ **Đã từng bị `OOMKilled`** | **Không giảm.** Cần điều tra nguyên nhân OOM; cân nhắc tăng limit thay vì giảm |
| **Prometheus** | 400Mi | `techx-corp-chart/values.yaml` — `resources.limits.memory: 400Mi` (*1180*) | Chưa có dữ liệu OOM/restart | Cần đo peak memory dưới tải trước khi đề xuất thay đổi |
| **OpenSearch** | 1100Mi | `techx-corp-chart/values.yaml` — `resources.limits.memory: 1100Mi` (*1233*) | Chưa có dữ liệu OOM/restart | Không nên giảm ngay khi chưa có dữ liệu runtime và cảnh báo OOM |
| **Grafana** | 300Mi | `techx-corp-chart/values.yaml` — `resources.limits.memory: 300Mi` (*1213*) | Chưa có dữ liệu OOM/restart | Cần giám sát sát trước khi điều chỉnh |

#### Evidence:

![Kiểm tra Observability Stack](./runtime/screenshots/kiem%20tra%20resource%20cua%20observability%20stack.png)

> ⚠️ Các ô "*(điền số dòng)*" cần được xác minh trực tiếp trong `techx-corp-chart/values.yaml` và `techx-corp-platform/docker-compose.yml` trước khi trình reviewer. Không nêu số dòng khi chưa mở file kiểm tra thực tế.

### 2.3 Nguyên tắc quyết định theo hướng evidence-first

- Không giảm limit cho bất kỳ service observability nào chỉ vì một snapshot hoặc một lần đo nhẹ ở trạng thái không tải. Mọi thay đổi cần dựa trên dữ liệu theo thời gian, dưới tải và có kiểm soát.
- **Nếu runtime cho thấy `OOMKilled` hoặc restart liên tục (như trường hợp Jaeger), đây là tín hiệu để điều tra và cân nhắc TĂNG limit, không phải giảm** — kể cả khi số liệu snapshot steady-state cho thấy usage thấp.
- Khi đề xuất thay đổi, phải ghi rõ: số liệu thu thập được từ đâu, thời gian đo, điều kiện tải, trích dẫn file:dòng trong code, và cách rollback.

---

## 3. COST-06.3 — Cost Impact & Kế hoạch giảm thiểu (Mitigation Plan)

### 3.1 Tuần 1 — Hành động có căn cứ và không tự ý cắt giảm

> Báo cáo này không đề xuất giảm limit cho Jaeger/Prometheus/OpenSearch/Grafana trong Tuần 1. Riêng Jaeger, dữ liệu OOMKilled là bằng chứng ngược lại — cần điều tra/tăng chứ không giảm. Mọi thay đổi khác ở nhóm observability đều cần đợi dữ liệu vận hành thực tế và kiểm tra lại dưới tải.

#### Pha 1 — Làm ngay (đã có căn cứ)

| # | Hành động | Thay đổi cấu hình | Mục tiêu | Rủi ro | Trạng thái |
| :-: | :--- | :--- | :--- | :--- | :-- |
| 1 | Tắt autostart cho `load-generator` | `LOCUST_AUTOSTART=true` → `false` trong `techx-corp-platform/.env` | Ngăn service chạy nền không cần thiết | Thấp | ☐ |
| 2 | Ghi nhận cấu hình hiện tại trong code, kèm file:dòng chính xác | `techx-corp-platform/docker-compose.yml` | Làm baseline cho các quyết định tới, đảm bảo mọi số liệu đều truy xuất được | Thấp | ☐ |
| 3 | Mở điều tra riêng cho sự cố Jaeger `OOMKilled` | Xem log container, thời điểm xảy ra, tương quan với traffic | Xác định nguyên nhân trước khi đổi limit | Trung bình — cần ưu tiên xử lý | ☐ |

#### Pha 2 — Thu thập bằng chứng trước khi đổi limit

| Bước | Việc cần làm | Công cụ | Thời gian |
| :-- | :--- | :--- | :-- |
| 1 | Thu thập `docker stats` và Prometheus/Grafana metrics liên tục trong 48-72 giờ cho tất cả service observability | `docker stats`, Grafana/Prometheus | 48-72 giờ |
| 2 | Ghi nhận `OOMKilled`, restart count và thời điểm spike memory — đặc biệt đối chiếu lại lịch sử OOM của Jaeger để xác định pattern (thời điểm nào, tương quan traffic nào) | Docker logs, container events, `docker inspect` | Trong toàn bộ cửa sổ đo |
| 3 | Chạy một lần load test có kiểm soát và quan sát memory peak của Jaeger/Prometheus | `load-generator` (chỉ khi cần, bật thủ công), Grafana/Prometheus | 1 lần trong cửa sổ đo |
| 4 | Với Jaeger: đánh giá xem 600 MiB có đủ cho traffic thực tế sau khi tắt `load-generator` hay không — có thể OOM đến từ chính traffic giả lập, không phải traffic thật | So sánh OOM timestamp với lịch sử bật/tắt load-generator | Sau Bước 1 của Pha 1 |
| 5 | Chỉ khi có đủ dữ liệu mới đề xuất thay đổi limit (tăng hoặc giảm) và kèm theo kế hoạch rollback, trích dẫn file:dòng cấu hình liên quan | Báo cáo cập nhật | Sau khi có đủ evidence |

> 💡 **Lưu ý liên hệ giữa Pha 1 và Pha 2:** Có khả năng Jaeger bị OOMKilled một phần do khối lượng trace phát sinh từ chính `load-generator` chạy nền 24/7. Sau khi tắt autostart ở Pha 1, cần theo dõi xem tần suất OOM của Jaeger có giảm không — đây là dữ liệu quan trọng để phân biệt "OOM do traffic giả lập" và "OOM do limit thực sự quá thấp".

#### Kế hoạch xác minh sau triển khai (Verification checklist)

- [ ] Chạy `docker stats --no-stream` sau 24h và 72h, xác nhận `load-generator` không tự khởi động lại ngoài ý muốn.
- [ ] Thu thập log/container events để kiểm tra xem Jaeger có tiếp tục bị `OOMKilled` sau khi tắt `load-generator` không.
- [ ] Xác nhận vị trí file:dòng cho toàn bộ số liệu cấu hình nêu trong báo cáo (mục 1.1 và 2.2) trước khi trình reviewer.
- [ ] Chỉ khi có đủ dữ liệu runtime mới trình bày đề xuất thay đổi limit cho Jaeger/Prometheus/OpenSearch/Grafana.
- [ ] Nếu không có bằng chứng đủ mạnh, giữ nguyên limit hiện tại và ghi rõ lý do trong báo cáo.

#### Kế hoạch rollback

Nếu cần khôi phục `load-generator` về trạng thái autostart, rollback bằng cách đặt lại `LOCUST_AUTOSTART=true` trong `.env` và chạy lại:

```bash
docker compose up -d --force-recreate load-generator
```

---

### 3.2 Tuần 2 — Giám sát và chốt đề xuất nếu có bằng chứng

| # | Hành động | Mục tiêu | Owner | Trạng thái |
| :-: | :--- | :--- | :--- | :-- |
| 1 | Hoàn tất điều tra nguyên nhân OOM của Jaeger | Xác định có nên tăng limit hay cấu hình lại (vd. sampling rate, batch size) | | ☐ |
| 2 | Hoàn tất thu thập dữ liệu cho Prometheus | Xác định peak usage, restart count và `OOMKilled` dưới tải | | ☐ |
| 3 | Giám sát OpenSearch & Grafana | Theo dõi biểu đồ RAM hàng ngày, giữ nguyên limit hiện tại cho đến khi có bằng chứng rõ ràng | | ☐ |
| 4 | Đánh giá Prometheus retention | Xem xét `retention.time=7d` chỉ sau khi có dữ liệu lưu trữ và mức sử dụng thực tế | | ☐ |

**Ghi chú (quan trọng):** OpenSearch và Grafana không được giảm limit trong bản này. Jaeger **không được giảm** và cần ưu tiên điều tra/tăng. Mọi đề xuất điều chỉnh cần đi kèm dữ liệu giám sát dài hạn, bằng chứng vận hành thực tế (không chỉ snapshot), và trích dẫn file:dòng cấu hình. Nếu runtime cho thấy `OOMKilled` hoặc mức sử dụng gần giới hạn ở bất kỳ service nào, cần tăng/điều tra thay vì giảm.

Gợi ý mở rộng cho Tuần 2 (nếu team có nhu cầu):

- Thiết lập alert Grafana khi RAM sử dụng của bất kỳ service nào (kể cả Jaeger) vượt 85% limit, và alert riêng cho sự kiện OOMKilled.
- Đánh giá index lifecycle management (ILM) của OpenSearch để tự động xóa/nén index cũ, giảm áp lực bộ nhớ mà không cần tăng limit.
- Với Jaeger: xem xét điều chỉnh sampling rate hoặc batch size thay vì chỉ tăng memory limit, nếu nguyên nhân OOM đến từ khối lượng trace quá lớn.

---

## 4. Tổng hợp tác động (Impact Summary)

| Chỉ số | Trước | Sau (dự kiến, Tuần 1) | Chênh lệch |
| :--- | ---: | ---: | ---: |
| Load-generator chạy nền | Có (24/7) | Không (chỉ khi cần) | Loại bỏ nhiễu log/trace |
| Độ tin cậy dữ liệu SLO/SLI | Bị nhiễu bởi traffic giả lập | Phản ánh đúng người dùng thật hơn | Cải thiện |
| Jaeger memory limit | 600M, đã từng OOMKilled | **Không giảm — ưu tiên điều tra nguyên nhân OOM, cân nhắc tăng** | Đảo ngược hướng xử lý so với đề xuất ban đầu |
| Prometheus / OpenSearch / Grafana limit | Theo cấu hình hiện tại trong code | **Không thay đổi trong bản này** — chờ dữ liệu runtime và kiểm tra dưới tải | Không có thay đổi limit nào được đề xuất |
| Chi phí AWS thực tế (billing) | — | — | **Chưa thể khẳng định giảm ngay** — chỉ có thể xác nhận khi có thay đổi hạ tầng thực tế ở cấp node/instance hoặc bin-packing |

---


## Phụ lục A — Danh sách kiểm tra trước khi triển khai (Pre-deployment Checklist)

- [ ] Backup file `docker-compose.yml` và `.env` hiện tại
- [ ] Xác minh và điền đầy đủ vị trí file:dòng cho mọi số liệu cấu hình trong báo cáo (mục 1.1, 2.2)
- [ ] Thông báo team về thời gian bảo trì/restart service (nếu áp dụng ngoài giờ thấp điểm)
- [ ] Chuẩn bị sẵn giá trị rollback cho `load-generator`
- [ ] Xác nhận không có job/test nào đang phụ thuộc vào `load-generator` chạy nền tại thời điểm tắt autostart
- [ ] Mở điều tra riêng (ticket/issue) cho sự cố Jaeger `OOMKilled`, không gộp chung với hạng mục cost optimization
