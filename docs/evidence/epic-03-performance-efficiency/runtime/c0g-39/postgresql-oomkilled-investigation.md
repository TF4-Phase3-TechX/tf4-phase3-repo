# C0G-39 — PostgreSQL OOMKilled: quan sát, đối chiếu, phát hiện, đề xuất

**Jira:** C0G-39
**Owner:** CDO-04 (Performance Efficiency + Cost Optimization)
**Liên quan:** C0G-18 (accounting OOM), C0G-19 (jaeger/grafana OOM)
**Status:** Đã chạy acceptance run (200 user / ramp-up 20 / 15 phút) — không tái hiện OOM. Đề xuất đang chờ áp dụng.

---

## 1. Quan sát được

```
postgresql-75fff48d97-6prp2   0/1   OOMKilled   0          4d2h
postgresql-75fff48d97-6prp2   1/1   Running     1 (2s ago) 4d2h
```

Pod `postgresql` chạy ổn định 4 ngày liền (restart = 0) rồi đột ngột OOMKilled 1 lần, tự phục hồi. Cấu hình hiện tại: `techx-corp-chart/values.yaml:903-905` — chỉ có `limits.memory: 100Mi`, không có `requests`, không có tham số Postgres tuỳ chỉnh (chạy mặc định gốc).

Vị trí node tại thời điểm OOM:
```
grafana      → ip-10-0-10-231
accounting   → ip-10-0-10-231
jaeger       → ip-10-0-11-40   (RESTARTS 15 trong ~4h, vẫn crash-loop)
postgresql   → ip-10-0-11-40
```
`postgresql` và `jaeger` **nằm chung 1 node**, và 2 lần OOM gần nhất cách nhau **~7 phút**.

## 2. Đối chiếu như thế nào

**Bước 1 — đối chiếu cấu hình tĩnh:** `shared_buffers` mặc định Postgres 17 là 128MB, tưởng như vượt sẵn `limits: 100Mi` ngay từ lúc khởi động. Nhưng đây là cấp phát shared-memory kiểu mmap (địa chỉ ảo) — cgroup chỉ tính phần trang nhớ thực sự bị chạm tới, không tính nguyên cấu hình. Với dataset nhỏ (catalog/reviews/accounting ở mức demo), phần thực chạm tới rất thấp — nên phép so sánh tĩnh này **không đủ** để kết luận nguyên nhân.

**Bước 2 — đối chiếu bằng tải thật:** chạy Locust 200 user / ramp-up 20 / 15 phút (đúng thông số acceptance run) trên nguyên cấu hình `100Mi` cũ — **không OOM lại**. Nếu 100Mi thực sự không đủ cho compute cần thiết, bài test này phải tái hiện được lỗi; nó không tái hiện → loại trừ khả năng "thiếu compute per-se".

**Bước 3 — đối chiếu vị trí + thời gian:** cùng node với Jaeger, OOM cách nhau 7 phút → đối chiếu chéo với `C0G-19` (đo trực tiếp qua Prometheus): Jaeger đạt peak thật **762 MiB** trước khi crash, span rate 1200-1600/giây khi có tải, do `MEMORY_MAX_TRACES: 25000` chưa được giảm. Một pod tiêu tốn gần 800MiB và crash-loop liên tục trên cùng node là tải trọng đáng kể lên tài nguyên node dùng chung.

## 3. Phát hiện

**Root cause khả dĩ nhất: postgres không tự thiếu compute — nó là "nạn nhân cùng node" của Jaeger.** Không phải vấn đề cấu hình Postgres per-se (bước 2 đã loại trừ), mà là áp lực tài nguyên từ pod láng giềng bất ổn (bước 3). Chưa xác nhận được 100% vì role hiện tại (`TF4-BaseReadOnly`) không có quyền đọc `nodes` để xem % allocation thật — nhưng bằng chứng vị trí + thời gian + số liệu độc lập từ C0G-19 đã đủ mạnh để hành động.

**Rủi ro cấu trúc, độc lập với nguyên nhân gốc:** PostgreSQL không có PVC (`ADR-004`) — bất kể OOM vì lý do gì, mỗi lần restart là **mất vĩnh viễn dữ liệu schema `accounting`** (không được seed lại như `catalog`/`reviews`). Đây là rủi ro cần xử lý bất kể root cause có được xác định dứt điểm hay không.

## 4. Đề xuất (theo góc nhìn Performance & Cost)

**Ưu tiên 1 — `podAntiAffinity`, chi phí $0, hiệu quả nhất:**
```yaml
postgresql:
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        - labelSelector:
            matchExpressions:
              - key: app.kubernetes.io/name
                operator: In
                values: ["jaeger"]
          topologyKey: kubernetes.io/hostname
```
Không tốn thêm RAM/node nào — chỉ là quyết định scheduling. Đúng nguyên nhân circumstantial mạnh nhất hiện có, nên đây là fix ưu tiên cao nhất về cost-efficiency, không phải tăng resource.

**Ưu tiên 2 — tăng resource nhẹ, mang tính phòng ngừa (không phải "đã chứng minh thiếu"):**
```yaml
postgresql:
  resources:
    requests:
      memory: 192Mi
    limits:
      memory: 384Mi
  env:
    - name: POSTGRES_INITDB_ARGS
      value: "-c shared_buffers=96MB -c max_connections=50 -c work_mem=4MB"
```
Chi phí thêm ~284Mi RAM cho 1 pod — nhỏ so với ngân sách $300/tuần, nhưng vẫn nên coi là chi phí phòng ngừa (đổi lấy giảm rủi ro mất dữ liệu), không phải chi phí "sửa lỗi đã xác định". Rollback: `helm rollback techx-corp <revision-trước>`.

**Không khuyến nghị tiếp tục tăng RAM cho Jaeger** (đã ở 768Mi, khá tốn) — nguyên nhân gốc của Jaeger là `MEMORY_MAX_TRACES` chưa giảm, không phải thiếu RAM. Về chi phí, giảm `MEMORY_MAX_TRACES` rẻ hơn và trực tiếp hơn tăng RAM thêm — nên xử lý qua ticket riêng của Jaeger trước khi cân nhắc bất kỳ đề xuất tăng RAM nào nữa cho nó.

**Dài hạn:** PVC/StatefulSet cho PostgreSQL (đã cam kết ở ADR-004 mục 6, ~$8-16/tuần thêm cho EBS) — chi phí thấp so với rủi ro mất dữ liệu vĩnh viễn, nên đưa vào backlog Cost Optimization ưu tiên sớm thay vì tiếp tục hoãn.

---

*Owner: CDO-04. Support: CDO-08 (data durability), CDO-07 (xác nhận mất dữ liệu nếu có, audit trail).*
