# Hướng dẫn Cấu trúc Thư mục Tài liệu Dự án (Docs Folder Structure Guide)

Tài liệu này định nghĩa cấu trúc thư mục chuẩn hóa dành cho tài liệu của các đội ngũ phát triển (Teams) qua các tuần (weeks) từ **Tuần 2, Tuần 3, đến Tuần 4**.

Mục tiêu là đồng bộ hóa cách tổ chức file để các bên liên quan (PM, Tech Leads, Security, Reliability Teams) dễ dàng đọc chéo, review và tự động nhận diện file đổi tên (rename) trên GitHub mà không bị rối mắt.

---

## 1. Cấu trúc Tổng quan (Overall Directory Tree)

Mỗi thư mục tuần của các nhóm (ví dụ: `docs/cdo08/week2/`, `docs/cdo08/week3/`,...) cần được phân chia theo các Mandate (Chỉ thị) và chứa **4 thư mục con tiêu chuẩn** được bảo vệ bằng tệp `.gitkeep`:

```text
docs/cdo08/week<N>/
├── mandate0/ (General / Cross-Mandate Reliability)
│   ├── adr/
│   ├── evidence/
│   ├── implementation/
│   └── review-requests/
├── mandate1/ (Ingress Hardening / SEC-05)
│   ├── adr/
│   ├── evidence/
│   ├── implementation/
│   └── review-requests/
├── mandate5/ (Runtime Hardening / VAP)
│   ├── adr/
│   ├── evidence/
│   ├── implementation/
│   └── review-requests/
└── mandate8/ (Managed Services Migration)
    ├── adr/
    ├── evidence/
    ├── implementation/
    └── review-requests/
```

---

## 2. Định nghĩa vai trò 4 thư mục con tiêu chuẩn

| Tên thư mục            | Loại tài liệu chứa bên trong                                                                                                                                                                    | Ví dụ thực tế                                                                         |
| :--------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------ |
| **`adr/`**             | - Các quyết định thiết kế kiến trúc (ADR).<br>- Tài liệu phân tích lựa chọn kỹ thuật (`ANALYSIS.md`).<br>- Biểu mẫu ghi nhận biểu quyết Tech Lead (`DECISIONS.md`).                             | `MANDATE-08-POSTGRESQL-DECISIONS.md`, `ADR-MANDATE-05-RUNTIME-HARDENING-ADMISSION.md` |
| **`implementation/`**  | - Kế hoạch triển khai kỹ thuật (Implementation Plans).<br>- Kịch bản chạy dòng lệnh / cấu hình (Runbooks).<br>- Đề xuất baseline kỹ thuật (Proposals).                                          | `CDO08-SEC-09-RUNTIME-HARDENING-PLAN.md`, `CDO08-SEC-09-RUNTIME-HARDENING-RUNBOOK.md` |
| **`evidence/`**        | - Các báo cáo bằng chứng chạy thực tế, logs verifications.<br>- Kết quả chạy test tự động (test output).<br>- Screenshot kết quả trên dashboard (để trong thư mục `image` ở ngoài và link vào). | `MANDATE-05-RUNTIME-HARDENING-EVIDENCE.md`, `MANDATE-01-CUTOVER-REPORT.md`            |
| **`review-requests/`** | - Các biểu mẫu yêu cầu review chính thức gửi cho PM, Tech Lead chính, hoặc các đội ngũ khác (CDO04 cost, CDO07 audit).                                                                          | `REVIEW-REQUEST-CDO04-COST-SEC05.md`, `REVIEW-KARPENTER-IMPLEMENTATION-PLAN.md`       |

---

## 3. Quy tắc Cộng tác & Git

1. **Ghim thư mục trống bằng `.gitkeep`:**
   - Để Git không bỏ qua các thư mục trống khi clone/pull, bắt buộc phải có một tệp trống tên `.gitkeep` trong mỗi thư mục con.
2. **Hạn chế Merge Conflict khi làm việc nhóm:**
   - Khi nhiều Tech Lead cùng điền biểu quyết, hãy copy file template trong thư mục `adr/` thành file riêng của mình trước khi sửa (ví dụ: `MANDATE-08-POSTGRESQL-DECISIONS-NGUYEN.md`).
   - Chỉ gộp chung thành một file duy nhất (`CONSOLIDATED.md`) sau khi đã họp thống nhất phương án.
3. **Bảo toàn lịch sử Git (Rename Detection):**
   - Sử dụng lệnh `git add -A` (hoặc `git add .`) sau khi di chuyển file. Git sẽ tự động nhận diện hành động di chuyển file dưới dạng **`Rename`** thay vì **`Delete + Add`** trên GitHub Pull Request nếu nội dung giống nhau > 50%.

---
