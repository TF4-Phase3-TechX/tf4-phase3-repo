# CDO08-REL-26 - Evidence drill khôi phục dữ liệu accounting trên RDS

Video evidence: <https://drive.google.com/file/d/1RiUMXy2-k2U8nOkDc5mLttjsxrvAQqDp/view?usp=sharing>

## Phạm vi an toàn của drill

Đây là restore drill ở môi trường dry-run có kiểm soát, không thực hiện xóa dữ liệu hoặc restore trực tiếp trên RDS production.

Trong quá trình drill, script tạo thêm 2 RDS tạm:

1. `techx-tf4-drill-rel26-20260727-accounting-source`: RDS temp source được restore từ production PITR. Đây là bản sao dùng để mô phỏng xóa nhầm.
2. `techx-tf4-drill-rel26-20260727-accounting-restore`: RDS drill restore được restore từ PITR của RDS temp source tại thời điểm trước khi marker bị xóa.

RDS production `techx-tf4-postgresql` chỉ được dùng làm nguồn PITR để tạo RDS temp source. Production không bị ghi, không bị xóa data, không bị restore đè và không bị thay đổi endpoint.

## Kết luận

REL-26 restore drill đã PASS.

Drill mô phỏng tình huống xóa nhầm dữ liệu `accounting` nhưng không đụng vào RDS production. Script tạo một RDS temp source từ production PITR, tạo marker data trên RDS temp, xóa marker trên RDS temp, restore một RDS drill từ PITR trước thời điểm xóa, xác minh marker có lại trên RDS drill, rồi restore marker rows về RDS temp source.

Kết quả cuối từ log:

```text
rel26_completed production_modified=false temp_source_corrupted=true marker_restored=true marker_order_id=rel26-20260727-controlled-delete-order drill_setup_seconds=1965 recovery_rto_seconds=789
cleanup_complete_no_drill_resources_remaining
```

Ý nghĩa:

- `production_modified=false`: RDS production không bị sửa.
- `temp_source_corrupted=true`: dữ liệu marker đã bị xóa có kiểm soát trên RDS temp source để mô phỏng incident.
- `marker_restored=true`: dữ liệu marker đã được khôi phục lại thành công.
- `drill_setup_seconds=1965`: thời gian dựng môi trường drill, không tính vào RTO.
- `recovery_rto_seconds=789`: thời gian recovery thực tế sau khi xác nhận xóa nhầm.

## Thông tin drill

| Field | Value |
|---|---|
| Ngày chạy | 2026-07-27 |
| AWS account | `511825856493` |
| Region | `us-east-1` |
| Production RDS | `techx-tf4-postgresql` |
| App secret dùng để connect | `techx/tf4/rds-postgres` |
| Temp source RDS | `techx-tf4-drill-rel26-20260727-accounting-source` |
| Drill restore RDS | `techx-tf4-drill-rel26-20260727-accounting-restore` |
| Marker order id | `rel26-20260727-controlled-delete-order` |
| Source restore time | `2026-07-27T00:06:35Z` |
| Drill restore time | `2026-07-27T01:03:52Z` |
| Drill setup time | `1965s` / `32m45s` |
| Recovery RTO | `789s` / `13m09s` |
| Cleanup | PASS |

## Flow đã thực hiện

### 1. `environment_preflight`

Mục đích: kiểm tra điều kiện trước khi tạo tài nguyên drill.

Stage này xác nhận:

- đang ở đúng AWS account;
- production RDS `techx-tf4-postgresql` tồn tại và sẵn sàng;
- PITR timestamp nằm trong restore window;
- tên RDS temp/drill chưa tồn tại;
- app secret `techx/tf4/rds-postgres` đọc được;
- marker id đã được set.

Evidence:

```text
preflight_passed prod=techx-tf4-postgresql temp_source=techx-tf4-drill-rel26-20260727-accounting-source drill_target=techx-tf4-drill-rel26-20260727-accounting-restore source_restore_time=2026-07-27T00:06:35Z app_secret=techx/tf4/rds-postgres marker_order_id=rel26-20260727-controlled-delete-order
```

### 2. `create_validation_identity`

Mục đích: tạo IAM role/profile tạm cho EC2 validation.

Role này cho EC2 private chạy command qua SSM và đọc app secret cần thiết. Role chỉ dùng trong drill, sau đó bị xóa ở cleanup.

Evidence:

```text
created_role=techx-tf4-rel26-validation instance_profile=techx-tf4-rel26-validation
validation_secret_policy_updated resources=["arn:aws:secretsmanager:us-east-1:511825856493:secret:techx/tf4/rds-postgres-T586rF"]
```

### 3. `create_isolated_network`

Mục đích: tạo network tạm để validation không mở public access.

Script tạo:

- một security group cho EC2 validation;
- một security group cho RDS temp/drill;
- chỉ cho phép EC2 validation connect RDS qua port `5432`;
- không expose RDS public.

Evidence:

```text
created_validation_sg=sg-0c2403a5ccee67696 created_rds_sg=sg-0874bfdae1577c7e8
```

### 4. `create_validation_ec2`

Mục đích: tạo EC2 private để chạy `psql`/restore validation qua SSM.

EC2 không có public IP. Script cài PostgreSQL tools, `jq`, AWS CLI và verify SSM online.

Evidence:

```text
validation_instance=i-0df2aa837c1e916f6 ssm_status=Online
created_validation_ec2=i-0df2aa837c1e916f6 public_ip=none ssm=Online
```

### 5. `create_temp_source_from_prod`

Mục đích: tạo RDS temp source từ production PITR.

Đây là bước dựng môi trường drill an toàn. Production chỉ được dùng làm nguồn PITR, không bị sửa data.

Evidence:

```text
temp_source_ready identifier=techx-tf4-drill-rel26-20260727-accounting-source endpoint=techx-tf4-drill-rel26-20260727-accounting-source.covse6gsuue2.us-east-1.rds.amazonaws.com public=false sg=sg-0874bfdae1577c7e8 production_modified=false
phase_end duration_seconds=1416
```

### 6. `seed_marker_dataset`

Mục đích: tạo dữ liệu marker có kiểm soát trên RDS temp source.

Marker dùng để chứng minh rõ ràng:

- trước khi xóa có data;
- sau khi xóa data biến mất;
- sau khi restore data quay lại.

Marker chính:

```text
rel26-20260727-controlled-delete-order
```

Evidence:

```text
ssm_command=seed_marker command_id=e30f507a-ef26-417f-9b7f-c7337392a27f
phase_end duration_seconds=12
```

### 7. `wait_marker_recoverable`

Mục đích: chờ PITR của RDS temp source bắt kịp thời điểm sau khi insert marker.

Nếu bỏ qua bước này, RDS drill restore có thể restore về thời điểm chưa có marker, làm evidence sai.

Evidence:

```text
drill_restore_time_selected=2026-07-27T01:03:52Z marker_order_id=rel26-20260727-controlled-delete-order
drill_setup_ready setup_seconds=1965 note=setup_time_is_not_recovery_rto
```

Lưu ý: `1965s` là thời gian chuẩn bị môi trường drill, không phải RTO recovery.

### 8. `controlled_delete`

Mục đích: mô phỏng incident xóa nhầm data.

Script xóa marker trên RDS temp source, không xóa trên production. Sau khi xóa thành công, script mới bắt đầu tính RTO.

Evidence:

```text
ssm_command=delete_marker command_id=9bb4a283-ff4f-4810-99de-afa5c99e4e8c
recovery_rto_start incident=controlled_delete_confirmed marker_order_id=rel26-20260727-controlled-delete-order
```

### 9. `create_drill_restore_from_temp`

Mục đích: tạo RDS drill restore từ PITR của RDS temp source tại thời điểm trước khi xóa marker.

Đây là phần chính của recovery: dùng PITR để lấy lại trạng thái trước incident.

Evidence:

```text
drill_target_ready identifier=techx-tf4-drill-rel26-20260727-accounting-restore endpoint=techx-tf4-drill-rel26-20260727-accounting-restore.covse6gsuue2.us-east-1.rds.amazonaws.com restore_time=2026-07-27T01:03:52Z public=false
phase_end duration_seconds=774
```

### 10. `verify_drill_contains_marker`

Mục đích: xác minh RDS drill restore có marker đã bị xóa ở RDS temp source.

Nếu marker tồn tại ở RDS drill, điều này chứng minh PITR restore lấy lại được dữ liệu tại thời điểm trước incident.

Evidence:

```text
ssm_command=verify_drill_marker command_id=d21a826a-eedd-40a7-b918-aa9676307587
phase_end duration_seconds=5
```

### 11. `restore_marker_to_temp_source`

Mục đích: lấy marker rows từ RDS drill và restore lại vào RDS temp source.

Script chỉ restore đúng các marker rows bị xóa. Không drop schema, không restore đè toàn bộ DB, giảm blast radius.

Evidence:

```text
ssm_command=restore_schema_to_temp command_id=20e14f8a-6621-4b7e-8b79-4147ff54d149
phase_end duration_seconds=5
```

### 12. `final_validation`

Mục đích: xác minh marker đã quay lại RDS temp source sau restore.

Evidence:

```text
ssm_command=verify_temp_marker_restored command_id=04be4cd3-77eb-4a4a-b748-15d2d73651ba
phase_end duration_seconds=5
recovery_rto_end recovery_rto_seconds=789
rel26_completed production_modified=false temp_source_corrupted=true marker_restored=true marker_order_id=rel26-20260727-controlled-delete-order drill_setup_seconds=1965 recovery_rto_seconds=789
```

### 13. `cleanup`

Mục đích: xóa toàn bộ tài nguyên tạm sau drill để tránh phát sinh chi phí và tránh tài nguyên stale.

Các tài nguyên đã xóa:

- RDS drill restore;
- RDS temp source;
- EC2 validation;
- RDS/validation security groups;
- IAM instance profile;
- IAM role.

Evidence:

```text
cleanup_deleted_rds=techx-tf4-drill-rel26-20260727-accounting-restore
cleanup_deleted_rds=techx-tf4-drill-rel26-20260727-accounting-source
cleanup_terminated_ec2=i-0df2aa837c1e916f6
cleanup_deleted_sg=sg-0874bfdae1577c7e8
cleanup_deleted_sg=sg-0c2403a5ccee67696
cleanup_deleted_instance_profile=techx-tf4-rel26-validation
cleanup_deleted_role=techx-tf4-rel26-validation
cleanup_complete_no_drill_resources_remaining
```

Kiểm tra sau run bằng AWS CLI không trả về RDS/EC2/security group REL-26 còn sống.

## Ý nghĩa các RDS status trong log

| Status | Ý nghĩa |
|---|---|
| `creating` | RDS đang được tạo từ PITR/snapshot. AWS đang dựng DB instance và attach storage. |
| `configuring-enhanced-monitoring` | RDS đang cấu hình Enhanced Monitoring theo cấu hình của instance. |
| `backing-up` | RDS đang tạo automated backup đầu tiên hoặc thiết lập backup chain sau restore. |
| `modifying` | RDS đang apply cấu hình cuối, ví dụ monitoring, security group, backup hoặc metadata. |
| `available` | RDS đã sẵn sàng nhận connection. Script chỉ chạy SQL sau khi RDS đạt trạng thái này. |
| `Online` | EC2 validation đã online trong SSM, có thể nhận `AWS-RunShellScript`. |

## Cách tính thời gian

### Drill setup time

Không tính là RTO.

Bao gồm:

- tạo RDS temp source từ production PITR;
- insert marker data;
- chờ PITR của RDS temp source cover marker.

Kết quả:

```text
drill_setup_seconds=1965
```

### Recovery RTO

Bắt đầu sau khi marker đã bị xóa có kiểm soát và incident được xác nhận:

```text
recovery_rto_start incident=controlled_delete_confirmed
```

Kết thúc khi final validation xác nhận marker đã restore lại:

```text
recovery_rto_end recovery_rto_seconds=789
```

Kết quả RTO:

```text
789s = 13m09s
```

## Kết luận nghiệm thu

REL-26 đạt yêu cầu drill khôi phục dữ liệu RDS theo hướng an toàn:

- Production RDS không bị sửa.
- Có mô phỏng xóa nhầm thật trên RDS temp source.
- Có tạo RDS drill restore bằng PITR.
- Có verify marker quay lại trên RDS drill restore.
- Có restore marker rows về RDS temp source.
- Có final validation marker restored.
- Có cleanup toàn bộ tài nguyên tạm.
- Recovery RTO đo được: `789s`.
