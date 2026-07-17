# 🛡️ Bối cảnh & Yêu cầu Mandate 10: Secure Delivery Pipeline

- **Tên Directive:** `[DIRECTIVE #10] Từ commit tới cluster - không tin image mù`
- **Từ:** Ban Bảo mật Nền tảng & Tuân thủ - TechX Corp
- **Hiệu lực:** Kể từ khi nhận, hoàn tất và nộp trước **hết ngày 20/07/2026** (Thi đấu head-to-head giữa các TF).
- **Áp dụng:** Toàn bộ các Task Force.

---

## I. BỐI CẢNH (CONTEXT)
Hiện tại, đường đi của phần mềm từ **Code $\rightarrow$ Container Image $\rightarrow$ Kubernetes Cluster** của đa số các đội chưa được bảo mật chặt chẽ:
1. Pipeline CI chạy mang tính hình thức: CI báo lỗi (đỏ) vẫn có thể merge PR thủ công.
2. Không có cơ chế chứng minh tính "sạch" và nguồn gốc đáng tin cậy của các container image chạy trên cluster (không rõ từ commit nào, ai đã phê duyệt).
3. Một thay đổi nhỏ ở một service đơn lẻ có thể kéo theo việc build lại và deploy lại toàn bộ cụm, gây lãng phí chi phí vận hành và mở rộng vùng ảnh hưởng lỗi (blast radius).

Do đó, TechX Corp ban hành **Directive #10** nhằm thắt chặt quy trình đóng gói và giao hàng phần mềm theo mô hình **Zero Trust** (không tin tưởng mù quáng, mọi thứ phải được chứng minh).

---

## II. 6 YÊU CẦU CỐT LÕI (REQUIREMENTS)

| STT | Yêu cầu | Chi tiết kỹ thuật cần thực thi |
| :---: | :--- | :--- |
| **1** | **Cổng chặn CI/CD thật** | - Bật **Branch Protection Rules** và **Required Status Checks** trên nhánh deploy (main/master).<br>- Nếu pipeline CI (test, lint, scan, render) bị lỗi (đỏ) $\rightarrow$ **Cấm tuyệt đối** việc merge PR và deploy. |
| **2** | **Quét bảo mật trước khi Deploy** | - Quét lỗ hổng Image CVE, IaC misconfig và quét Secrets/SAST **trước khi đẩy lên Registry**.<br>- Đây phải là cổng chặn chủ động (không dùng cơ chế quét thụ động như ECR scan-on-push).<br>- Phát hiện lỗ hổng mức **HIGH** hoặc **CRITICAL** $\rightarrow$ Dừng pipeline lập tức. |
| **3** | **Bất biến & Xác thực nguồn gốc** | - Cấu hình ECR Registry ở chế độ **Immutable** (cấm ghi đè tag).<br>- Mỗi image phải được ký số bằng **Cosign**, đính kèm file danh mục phần mềm (**SBOM**) và bằng chứng provenance.<br>- EKS Admission Controller chỉ cho phép chạy image đã được ký hợp lệ và tham chiếu theo **digest** (sha256). |
| **4** | **Không phụ thuộc tag trôi nổi** | - Tất cả GitHub Actions của bên thứ ba phải được pin cố định bằng **Commit SHA** (không dùng tag phiên bản như `@v3`, `@master`).<br>- Base images trong Dockerfile phải được pin theo **Digest** (sha256). |
| **5** | **Khả năng truy vết ngược (Traceability)** | - Từ **một Pod bất kỳ** đang chạy trên cụm EKS, team phải dựng lại được chuỗi chứng cứ:<br>  *Pod $\rightarrow$ Image Digest $\rightarrow$ Commit SHA $\rightarrow$ Pull Request (ai duyệt) $\rightarrow$ Kết quả quét bảo mật $\rightarrow$ Khóa/ai đã ký $\rightarrow$ SBOM*. |
| **6** | **Blast-radius hẹp (Tối ưu hóa CI/CD)** | - Thay đổi code ở service nào thì **chỉ build và deploy đúng service đó**.<br>- Hạn chế tối đa việc kích hoạt rebuild toàn bộ hệ thống để bảo vệ ngân sách. |

---

## III. PHƯƠNG ÁN NGHIỆM THU (DELIVERABLES)
Mentor sẽ trực tiếp kiểm chứng bằng cách bấm nút thử thách hệ thống:
1. **Thao tác 1:** Tạo một Pull Request cố tình làm CI bị đỏ $\rightarrow$ Hệ thống phải chặn không cho merge.
2. **Thao tác 2:** Thử deploy thủ công một container image chưa được ký số / chưa quét bảo mật lên EKS $\rightarrow$ EKS Admission Controller (ví dụ Kyverno, OPA, hoặc VAP) phải từ chối chạy Pod.
3. **Thao tác 3:** Mentor chỉ ngẫu nhiên vào một Pod đang chạy trên cluster $\rightarrow$ Đội ngũ vận hành phải truy xuất ngược nhanh chóng toàn bộ nguồn gốc xuất xứ (provenance) của Pod đó.
