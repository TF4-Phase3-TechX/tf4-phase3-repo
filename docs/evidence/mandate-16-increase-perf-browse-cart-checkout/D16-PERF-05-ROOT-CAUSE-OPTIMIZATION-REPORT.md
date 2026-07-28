# D16-PERF-05 — Root-cause optimization delivery report

**Objective:** triển khai các tối ưu hóa đã xác định tại source of truth cho Browse → Cart → Checkout, giảm request fan-out thừa, ngăn Product Catalog làm cạn PostgreSQL connection capacity, và giữ nguyên correctness, tracing, logging cùng resource envelope.

**Scope delivered:** PR #324, #558, #565 và #592.

## 1. Lý do chọn các thay đổi

| Root cause / waste | Tác động lên luồng nghiệp vụ | Quyết định |
|---|---|---|
| Browse non-USD chuyển đổi tiền từng product | Một Browse list sinh N Currency RPC; tăng request volume và contention cho Currency | Gộp toàn bộ item prices thành một `BatchConvert` có kiểm tra input/output cardinality. |
| Checkout fan-out hai Product Catalog reads | Controlled reapply làm Product Catalog quá tải và Checkout lỗi liên tục dưới load | Giữ tối đa một Product Catalog RPC in-flight cho từng Checkout; không dùng worker-pool fan-out. |
| Confirmation hydrate từng item bằng `GetProduct` | Multi-item order sinh N Product Catalog RPC sau khi Checkout đã có dữ liệu product | Mang metadata display additive trong Checkout response và dùng lại ở frontend. |
| Checkout USD convert từng item từ USD sang USD | Multi-item order tạo N Currency RPC no-op dù giá USD đã được validate | Copy `Money` đã validate; chỉ giữ Currency conversion cho shipping. |
| Go SQL pool Product Catalog quá lớn | Khi có tải, pool không bị giới hạn có thể tạo >100 PostgreSQL connections và chiếm application slots của RDS | Bound pool mỗi Product Catalog pod tại 20 open / 5 idle; giữ headroom cho client khác. |

## 2. Implementation delivered

| PR | Git SHA đã merge | Thay đổi source of truth | Correctness / safety được giữ |
|---|---|---|---|
| [#324 — batch catalog currency conversions](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/324) | `411e9a23c542805e2ba4677099d4271eb22a6731` | Thêm `CurrencyService.BatchConvert`; frontend chỉ batch khi catalog không rỗng và currency khác USD; kiểm tra response cardinality trước khi gắn giá theo index. | USD, currency rỗng và catalog rỗng không gọi Currency; input/output giữ thứ tự; không dùng JavaScript floating point. |
| [#558 — restore sequential product reads](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/558) | `496abcddaad2a200d135c045e94184e05ec0aa86` | Bỏ worker pool Product Catalog trong Checkout; `getProducts` đọc tuần tự theo thứ tự cart item. | Giữ retry/deadline, nil-response validation, cancellation của preparation branch, Shipping quote parallelization, non-USD batching và exact-money handling. |
| [#565 — remove redundant confirmation RPCs](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/565) | `14da18472a826f9edd58dd3d00a5da995b5bdfb6` | Thêm protobuf field additive `OrderItem.product_display { name, picture, categories }`; Checkout tái sử dụng product đã đọc để giá và display; frontend dùng `productDisplay` trước. USD item price dùng `copyMoney` sau validation thay vì gọi `Convert`. | Compatibility fallback gọi `getProductForDisplay` khi frontend mới gặp Checkout pod cũ chưa trả field mới. Monetary fields từ Checkout vẫn authoritative. Non-USD item prices vẫn dùng `BatchConvert`; shipping vẫn convert một lần. |
| [#592 — bound PostgreSQL connection usage](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/592) | `9fcb5887947b63341f0cdfd56f608a07fe23e106` | `product-catalog` đặt `db.SetMaxOpenConns(20)` và `db.SetMaxIdleConns(5)`; Helm values đặt `PGAPPNAME=product-catalog` (cùng attribution cho các PostgreSQL client liên quan). | Không đổi replica count, HPA, CPU/memory request/limit, instance class hay node capacity. Lifetime/idle-time của connection vẫn là 5 phút / 2 phút. |

### 2.1 Regression đã xác minh: two-worker Product Catalog reads trong Checkout

Một controlled reapply của worker pool hai Product Catalog reads từ PR [#496](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/496) đã tạo tải đồng thời vượt khả năng xử lý của Product Catalog và làm Checkout lỗi liên tục dưới load. Đây là regression đã xác minh, không phải tối ưu hóa được giữ lại.

PR #558 đã revert phần fan-out này bằng cách trả `getProducts` về đọc tuần tự, tối đa một Product Catalog RPC in-flight cho mỗi Checkout. Rollback chỉ giới hạn ở worker pool gây tải; Shipping quote parallelization độc lập, non-USD `BatchConvert`, retry/deadline, nil-response validation và exact-money handling vẫn được giữ. Vì vậy, không được reintroduce two-worker fan-out trong bất kỳ rollout hoặc tuning nào của task này.

## 3. Business effect

### 3.1 Giảm downstream work trên normal path

- **Browse non-USD:** từ N Currency `Convert` xuống **1 `BatchConvert` mỗi catalog response**. Điều này giảm Currency RPC volume theo số product hiển thị, giữ giá trả về đúng product và hạn chế contention từ fan-out.
- **Checkout confirmation:** từ **N Product Catalog `GetProduct`** xuống **0 RPC hydrate bổ sung** khi Checkout trả `product_display`. Lợi ích trực tiếp là confirmation response ít phụ thuộc hơn vào Product Catalog và bớt request load trên service đang là dependency nóng.
- **Checkout USD multi-item:** từ **N Currency `Convert` cho item prices** xuống **0**; chỉ còn **1 `Convert` cho shipping cost**. Điều này bỏ round-trip no-op nhưng không thay đổi exact-money total.
- **Checkout Product Catalog read:** giữ **1 in-flight read** trong một Checkout thay vì hai worker đồng thời, loại bỏ failure mode Product Catalog overload đã tái hiện dưới controlled load.

### 3.2 Kết quả runtime thực tế của Product Catalog DB pool cap

Cửa sổ quan sát 23:37–23:52 ICT ngày 23/07/2026 chạy ở tải 200 users, sau khi cap pool đã được triển khai.

| Runtime signal | Kết quả |
|---|---|
| `db_sql_connection_max_open` | Cả hai Product Catalog pods đều báo **20**; cấu hình runtime đúng với source of truth. |
| Runaway connection creation | Đã được chặn: không còn pool Go không giới hạn có thể mở hơn 100 PostgreSQL connections. |
| RDS reserved application slots | Không thấy lỗi `remaining connection slots are reserved` trong cửa sổ tải. |
| Hot pod | Một pod đạt peak **20 open connections**, có 0.75–0.99 waits/s và acquire wait khoảng 90–101 ms; pod còn lại khoảng 5 open connections. |

Kết quả này chứng minh pool cap containment đang hoạt động: queue được bound ở Product Catalog thay vì chuyển thành connection storm làm cạn RDS. Nó cũng chỉ ra hành động vận hành đúng là giữ cap 20 và xử lý traffic skew/pod distribution, không mua thêm database connections hay tăng pool mù quáng.

## 4. Performance instrumentation và observability

- Product Catalog đăng ký OpenTelemetry SQL DB stats; metric runtime `db_sql_connection_max_open` xác nhận cap theo từng pod.
- `PGAPPNAME=product-catalog` được khai báo trong Helm source of truth để PostgreSQL connection ownership có attribution rõ ràng khi điều tra và vận hành.
- Các thay đổi giữ OpenTelemetry tracing, logging, retry/deadline, validation, cardinality validation và exact-money validation. Không có tracing/logging bị tắt để đổi lấy latency.
- Các tín hiệu vận hành dùng trong rollout: `db_sql_connection_max_open`, open connections, pool acquire wait/wait rate, Product Catalog error rate/latency, Checkout success rate và confirmation/checkout error rate.

## 5. Test và verification

### Automated validation

Các lệnh đã chạy thành công cho delivery:

```text
go test -count=1 ./...
go vet ./...
go build ./...
npm run typecheck
git diff --check
```

Coverage regression ở Checkout xác nhận:

- metadata `name`, `picture`, `categories` đi đúng item và giữ input ordering;
- Checkout USD nhiều item không gọi `Convert` hoặc `BatchConvert` cho item prices;
- exact total USD vẫn đúng và Currency `Convert` chỉ được gọi một lần cho shipping;
- Product Catalog reads trong preparation có maximum concurrency bằng 1;
- output `BatchConvert` sai cardinality/currency/money bị từ chối;
- preparation failure không tạo Payment, ShipOrder hoặc EmptyCart write.

CI của PR #558, #565 và #592 đã PASS các check liên quan: Helm lint/render, YAML parse, Docker smoke build Checkout + Shipping, secret scan, SAST/dependency scan và manifest scan. PR #565 cũng PASS frontend resilience typecheck/unit test. PR #324 đã merge với implementation batching; historical CI của PR này có Trivy SAST/dependency scan FAILURE, vì vậy không dùng kết quả check đó làm bằng chứng PASS cho acceptance của delivery hiện tại.

### Runtime smoke test

PASS cho DB-pool rollout: cả hai Product Catalog pods báo `db_sql_connection_max_open = 20`; không có RDS reserved-slot error trong cửa sổ tải 200 users. Đây đồng thời xác nhận code/config deployed khớp với source of truth.

## 6. Guardrail compliance

| Guardrail | Kết quả |
|---|---|
| Không tăng worker node / node-hours / instance class | PASS — không có thay đổi infrastructure capacity. |
| Không tăng HPA minimum replicas | PASS — không có thay đổi HPA minimum replicas. |
| Không tăng CPU/memory requests để lấy thêm compute | PASS — PR #324/#558/#565/#592 không thay đổi resource requests/limits. |
| Không giảm validation | PASS — giữ và bổ sung validation cho `Money`, target currency, response cardinality và nil response. |
| Không tắt tracing/logging | PASS — giữ OTel và DB stats; thêm connection attribution. |
| Không thay đổi load contract | PASS — DB-pool smoke được quan sát trong run 200-user; không đổi endpoint mix hoặc measurement window để làm đẹp số đo. |

## 7. Deployment plan — approved source of truth

1. Merge source PR vào `main` sau khi PR validation pass.
2. Với application change, workflow main-only build image theo short Git SHA, resolve immutable ECR digest và tạo GitOps promotion PR chỉ cho service thay đổi. Với chart-only change, workflow tạo GitOps promotion PR pin full chart source SHA.
3. Platform owner review và merge GitOps promotion PR. Argo CD sync GitOps revision đã merge; không chạy `helm upgrade` trực tiếp từ PR CI.
4. Dùng controlled window 15 phút, không chạy concurrent load test hoặc rollout khác. Roll out Checkout/Frontend trước cho #565, sau đó Product Catalog cho #592; quan sát readiness, error rate, DB pool metrics và Checkout success trong toàn bộ window.
5. Smoke test sau rollout:
   - đặt order USD nhiều item và xác nhận correct total, một shipping conversion, confirmation trả display fields;
   - đặt Browse non-USD và xác nhận item count/order/converted currency;
   - xác nhận Product Catalog metric `db_sql_connection_max_open = 20`, open connections không vượt 20/pod và không có RDS reserved-slot errors.
6. Mở rộng quan sát chỉ khi smoke test pass; dừng rollout và rollback ngay khi Checkout error/success SLO regress, product display thiếu ngoài mixed-version fallback, hoặc DB connectivity error xuất hiện.

**Controlled deployment window đã thực hiện cho pool cap:** 23:37–23:52 ICT, 23/07/2026, với run 200-user. Các lần deploy/rollback tiếp theo phải dùng cửa sổ được phê duyệt riêng theo quy trình trên.

## 8. Rollback plan

Rollback dùng GitOps source of truth: tạo/merge GitOps revert khôi phục chart source SHA hoặc image tag **và immutable digest** trước đó; Argo CD thực hiện rollout revision cũ. Không deploy thủ công vào cluster.

| Change | Rollback-ready revision | Điều kiện rollback |
|---|---|---|
| #324 BatchConvert | parent `7bbbef33c665370929255002643572e4fae6874c` | Browse non-USD sai cardinality/order/currency hoặc Currency errors tăng. |
| #558 Sequential product reads | parent `fe3bd7e4d275bf97d0f85b74124dd688fc8c8361` | Chỉ rollback theo incident commander; rollback sẽ tái đưa fan-out đã gây Product Catalog overload. |
| #565 Confirmation metadata / USD bypass | parent `c3005bcf9f6d588160f45e9ab00688b09db789af` | Confirmation failure không được cover bởi mixed-version fallback, hoặc exact-money/correctness failure. |
| #592 DB pool cap | parent `d9b18fafd1857a5615b5b4dad45386af43349268` | Persistent DB acquire waits/errors làm Checkout không đạt availability gate và mitigation không đủ. Không tăng cap theo phản xạ; phải kiểm tra global RDS ownership trước. |

Sau rollback, lặp lại smoke test ở mục 7 và xác nhận revision/image digest đang chạy khớp GitOps revision đã revert.

## 9. Jira acceptance checklist

- [x] Application code hoặc configuration source-of-truth đã merge: #324, #558, #565, #592.
- [x] Unit/integration/correctness validation PASS cho delivery hiện tại: `go test`, `go vet`, `go build`, frontend typecheck và regression coverage nêu trên.
- [x] Không có resource-buying change.
- [x] Deployment plan qua GitOps source of truth và Argo CD đã xác định.
- [x] Rollback commit/version sẵn sàng.
- [x] Runtime smoke test PASS cho Product Catalog DB pool cap.
- [ ] PR approval review: GitHub hiện báo `REVIEW_REQUIRED` cho #324, #558, #565 và #592; chỉ có comment từ Copilot không thể review do quota, chưa có approving review được ghi nhận. Cần một reviewer có thẩm quyền approve trước khi đóng acceptance này.
- [x] Controlled deployment window được ghi nhận cho DB pool cap; các rollout tiếp theo dùng window được phê duyệt theo mục 7.

## 10. Dependency

Task này phụ thuộc **D16-PERF-04**. Các thay đổi ở đây là corrective implementation tại code/config source of truth; chúng không tăng capacity và giữ các guardrail của performance program.
