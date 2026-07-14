# CDO04 Cost Review Request

**Backlog:** CDO08-REL-03

## Objective

Yêu cầu CDO04 đánh giá chi phí của các phương án persistence và High Availability trước khi triển khai.

## Context

CDO08 đã xác nhận hiện trạng runtime:

- PostgreSQL có `postgresql-pvc` nhưng vẫn single replica, chưa có failover.
- Valkey hiện không có PVC; cart state có thể mất khi pod/node restart.
- Kafka hiện single broker/controller và không có PVC; có rủi ro mất event hoặc gián đoạn async processing.

Task REL-03 chưa triển khai thay đổi stateful. CDO08 cần CDO04 review cost trước khi chọn phương án production.

## Options cần estimate

| Option | Component | Sizing assumption cần CDO04 kiểm tra | Reliability benefit | Cost/risk cần trả lời |
|--------|-----------|--------------------------------------|---------------------|-----------------------|
| Giữ PostgreSQL hiện tại + backup/restore proof | PostgreSQL | EBS `gp2` 10Gi hiện tại, backup storage tối thiểu | Giữ persistence hiện có, bổ sung restore proof | Chi phí backup/storage thêm là bao nhiêu? Có đủ trong budget không? |
| RDS Multi-AZ | PostgreSQL | Instance class nhỏ phù hợp dev/prod-lite, Multi-AZ, backup retention tối thiểu | Managed DB, failover tốt hơn, backup/restore chuẩn hơn | Monthly cost? Có vượt budget hiện tại không? |
| Valkey StatefulSet + PVC | Valkey cart | 1-2 replica, EBS size nhỏ cho cart, storage class hiện có | Giảm rủi ro mất cart khi pod recreate | Chi phí EBS và node headroom? Có đáng so với giá trị cart không? |
| ElastiCache Multi-AZ | Valkey cart | Small node class, Multi-AZ nếu cần | Managed cache, availability tốt hơn | Monthly cost? Có quá lớn so với cart durability không? |
| Kafka StatefulSet + PVC | Kafka | Multi-broker hoặc tối thiểu single broker + PVC, retention giới hạn | Giảm rủi ro mất event khi pod recreate | EBS/node cost? Vận hành có quá nặng không? |
| Amazon MSK | Kafka | Smallest feasible cluster cho workload hiện tại | Managed Kafka, HA tốt hơn | Monthly cost? Có phù hợp budget không? |

## Output Expected

CDO04 vui lòng trả lời theo format:

| Option | Estimated monthly cost | Budget impact | Recommendation | Notes |
|--------|------------------------|---------------|----------------|-------|
| ... | ... | ... | Approve / Reject / Defer | ... |

## Decision rule

- Nếu managed service vượt budget, CDO08 sẽ ưu tiên backup/restore proof và PVC/StatefulSet incremental improvement.
- Nếu managed service nằm trong budget và migration risk được Nguyên approve, CDO08 sẽ tạo implementation task riêng.
- Không triển khai RDS/ElastiCache/MSK trước khi có cost estimate và migration/rollback approval.

## Decision

**Status:** Pending CDO04 Approval

**Reviewer**

- CDO04
