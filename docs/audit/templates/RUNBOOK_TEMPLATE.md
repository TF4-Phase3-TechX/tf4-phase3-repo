# Runbook: <Dịch vụ/Kịch bản>

Người phụ trách: <team/người phụ trách>
Cập nhật lần cuối: YYYY-MM-DD
SLO liên quan: <SLO hoặc N/A>
Dashboard liên quan: <link hoặc đường dẫn>
Jira liên quan: <SCRUM-xxx hoặc N/A>

## Mục đích

<Mô tả khi nào cần dùng runbook này.>

## Triệu chứng

- <Triệu chứng quan sát được>
- <Tín hiệu alert/log/metric>
- <Ảnh hưởng tới khách hàng hoặc nghiệp vụ>

## Kiểm tra ban đầu

```powershell
<command 1>
<command 2>
```

## Các bước điều tra

1. <Kiểm tra trạng thái hiện tại và phạm vi ảnh hưởng.>
2. <Xác nhận ảnh hưởng bằng metric/log/trace.>
3. <Thu thập evidence trước khi thay đổi cấu hình hoặc thao tác xử lý.>
4. <Xác định owner hoặc hướng escalation phù hợp.>

## Giảm thiểu ảnh hưởng

<Mô tả các bước giảm thiểu an toàn. Không bypass các cơ chế incident đã được bảo vệ như flagd/OpenFeature nếu chưa có phê duyệt.>

## Chuyển tuyến xử lý

- Người phụ trách chính: <team/người phụ trách>
- Người dự phòng: <team/người phụ trách>
- Escalate khi: <điều kiện>

## Evidence cần thu thập

- Thời điểm và timezone.
- Command đã chạy và tóm tắt output.
- Screenshot/log/query link.
- Service/user/SLO bị ảnh hưởng.
- Link PR/Jira/ADR liên quan.

## Rollback

<Mô tả cách rollback nếu có thay đổi cấu hình hoặc deploy.>

## Follow-up

- <Action item>
- <Người phụ trách>
- <Hạn hoàn thành>
