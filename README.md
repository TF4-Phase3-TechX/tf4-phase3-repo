# Phase 3 - TechX Corp Service Takeover (TF4)

**TF4:** AIO01 + CDO04, CDO07, CDO08.

Chào mừng đến Phase 3. Đây là vòng cuối: các bạn **tiếp quản một sản phẩm AI đang chạy** của TechX Corp - một storefront thương mại điện tử gồm nhiều microservice trên Kubernetes, có hàng đợi, cơ sở dữ liệu, một tính năng AI tóm tắt review, và đầy đủ observability. Hệ thống này **đang sống và chưa hoàn hảo**: có chỗ chưa tối ưu về chi phí, bảo mật, độ tin cậy, khả năng mở rộng và truy vết.

Nhiệm vụ không phải "làm bài tập". Nhiệm vụ là **vận hành sản phẩm này như một kỹ sư thật**: tự đánh giá, tự ưu tiên, giữ SLA, xử lý sự cố, cải tiến dưới ràng buộc - và bảo vệ được mọi quyết định của mình.

## Đọc gì trước

1. **[RULES.md](docs/requirements/RULES.md)** - thể lệ đầy đủ: cấu trúc TF, 5 trụ (Security / Reliability / Performance Efficiency / Cost Optimization / Auditability) + trụ AI, timeline 3 tuần, và **luật chơi** (đọc kỹ mục luật - có điều khoản disqualify).
2. **[onboarding/](docs/requirements/onboarding/)** - hiểu hệ thống bạn tiếp quản: [ARCHITECTURE](docs/requirements/onboarding/ARCHITECTURE.md), [SLO](docs/requirements/onboarding/SLO.md), [BUDGET](docs/requirements/onboarding/BUDGET.md), [INCIDENT_HISTORY](docs/requirements/onboarding/INCIDENT_HISTORY.md), [PITCH_GUIDE](docs/requirements/onboarding/PITCH_GUIDE.md).
3. **[GETTING_STARTED.md](docs/requirements/GETTING_STARTED.md)** - cách build hệ thống từ source, đẩy image lên ECR của TF, rồi deploy và kiểm tra.

## Repo này có gì

| Đường dẫn | Nội dung |
|---|---|
| `docs/requirements/RULES.md` | Thể lệ Phase 3 (bắt buộc đọc) |
| `docs/requirements/onboarding/` | Kiến trúc, SLO, ngân sách, lịch sử sự cố, pitch guide - hiểu hệ thống trước khi đụng vào |
| `docs/requirements/GETTING_STARTED.md` | Hướng dẫn build → deploy → verify |
| `docs/requirements/mandates/` | Directive bắt buộc BTC thả vào trong lúc vận hành (trống lúc đầu) |
| `techx-corp-platform/` | Toàn bộ source code sản phẩm (microservice, AI review + LLM, observability) |
| `techx-corp-chart/` | Helm chart để deploy lên Kubernetes |
| `deploy/` | Script build/push image + các values file mẫu để deploy |

## Việc đầu tiên: đưa hệ thống lên chạy

Chính việc dựng được hệ thống và đưa nó lên chạy **là bước tiếp quản đầu tiên** - và đã được tính điểm. Bắt đầu từ [GETTING_STARTED.md](docs/requirements/GETTING_STARTED.md).

Sau khi hệ thống chạy: đọc kiến trúc, hiểu SLO/ngân sách/lịch sử, dựng backlog ưu tiên, và chuẩn bị cho buổi pitch bảo vệ ưu tiên cuối Tuần 1.

## Vài điều cần nhớ

- **Mỗi TF tự build image → đẩy lên ECR của account mình → deploy trên account của mình.** BTC cấp source + một image seed để khởi động.
- **Sự cố sẽ đến trong lúc vận hành.** Nhiệm vụ là phát hiện và xử lý để khách hàng ít bị ảnh hưởng nhất - **không phải tắt nó đi**. Cơ chế tạo sự cố do BTC kiểm soát; can thiệp/vô hiệu hóa nó = disqualify (xem RULES - mục Luật chơi).
- **Mọi quyết định phải truy được về người** (ADR / decision log ký tên). Đây là thứ được chấm.

Chúc các đội giữ được service khỏe và tỏa sáng.
