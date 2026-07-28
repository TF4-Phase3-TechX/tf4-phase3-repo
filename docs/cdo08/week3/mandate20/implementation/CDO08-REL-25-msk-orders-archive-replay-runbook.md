# CDO08-REL-25 - MSK Orders Archive Replay Runbook

**Task:** `[CDO08-REL-25][Subtask] Build MSK orders archive replay procedure`
**Owner:** CDO08 Reliability
**Mục tiêu:** Đọc orders archive theo time window, normalize và replay vào topic
drill cô lập, sau đó xác minh và cleanup.

## 1. Kiến trúc drill

```text
S3 orders archive (read-only)
  |
  | rel25-orders-archive-tool.py
  | - nhận diện protobuf OrderResult hoặc JSON batch marker
  | - lấy order_id
  | - SHA-256 + deduplicate
  | - bọc payload bằng protobuf/json-marker base64 JSON envelope
  v
Temporary local files
  |
  | rel25-replay-orders-archive.sh
  | Kafka key = order_id/correlation_id
  v
orders-replay-drill-rel25-<drill-id> (1 partition, retention 6 giờ)
  |
  | BATCH_START -> ORDER_REPLAY... -> BATCH_END
  v
Temporary validation consumer group
  |
  | so ID, hash, marker và counters
  v
JSON report -> cleanup consumer group/topic/temp files
```

Không có application production nào subscribe topic drill. Script không produce,
alter hoặc delete topic `orders`.

## 2. Các file

```text
scripts/msk/rel25-replay-orders-archive.sh
scripts/msk/lib/rel25-replay-common.sh
scripts/msk/rel25-orders-archive-tool.py
```

- Entry point: input, AWS/Kubernetes preflight, S3 discovery, topic lifecycle,
  produce, consume, report.
- Common library: log phase, Kafka helpers và EXIT cleanup.
- Python tool: chọn hourly prefix, parse protobuf bytes, normalize, deduplicate
  và verify output.

## 3. Guardrail bắt buộc

- AWS account và Kubernetes context phải khớp expected values.
- Target chỉ được khớp `orders-replay-drill-rel25-*`.
- Cấm `orders`, `orders-archive-dlq` và `orders-archive-connect-*`.
- Target phải chưa tồn tại. Script từ chối retry vào topic cũ.
- Topic drill có một partition để giữ thứ tự marker và record.
- Producer bật `enable.idempotence=true`, `acks=all`.
- Duplicate cùng `order_id` và cùng SHA-256 được skip.
- Cùng `order_id` nhưng payload khác SHA-256 là conflict và drill fail.
- S3 archive chỉ được đọc; archive writer và production cluster không bị sửa.
- EXIT trap xóa topic/group/file tạm khi PASS hoặc FAIL.
- `KEEP_TOPIC=false` là mặc định. Chỉ đổi thành `true` khi leader phê duyệt giữ
  topic để điều tra.

## 4. Prerequisite

Local:

```bash
aws --version
kubectl version --client
jq --version
python3 --version
```

AWS SSO và EKS:

```bash
aws sso login --profile tf4-cdo08-admin

aws sts get-caller-identity \
  --profile tf4-cdo08-admin \
  --query '[Account,Arn]' \
  --output table

kubectl config current-context

kubectl -n techx-tf4 get deployment kafka-connect-orders-archive
kubectl -n techx-tf4 exec deployment/kafka-connect-orders-archive -- \
  sh -c 'curl -fsS http://127.0.0.1:8083/connectors/orders-s3-archive/status'
```

Pass khi cluster đúng account, deployment `1/1` và connector/task đều
`RUNNING`.

## 4.1. Payload integrity gate

Script chỉ tạo topic sau khi toàn bộ object đã được download, parse và kiểm tra
byte integrity.

Archive legacy `.json` không được dùng nếu JSON string chứa `U+FFFD`. Ký tự này
chứng minh binary protobuf đã bị UTF-8 decoder thay byte không hợp lệ và không
thể dựng lại payload gốc. Script ghi failure counters rồi dừng trước
`create_isolated_topic`.

Archive hợp lệ cần một trong các dạng:

- raw ByteArray object `.bin` bảo toàn protobuf và có record framing không nhập
  nhằng; hoặc
- JSON envelope chứa protobuf base64, không chuyển binary trực tiếp thành UTF-8
  string.

Với `ByteArrayFormat`, không nên dùng newline mặc định để phân cách nhiều
protobuf records vì protobuf có thể chứa newline byte. Phương án đơn giản cho
drill là `flush.size=1` để mỗi object chứa đúng một event, hoặc dùng formatter
framing/base64 được review.

Ngày 2026-07-27, legacy window `2026-07-22T02:00:00Z` đến `03:00:00Z` chứa
50/50 record có `U+FFFD`; attempt dừng đúng ở integrity gate và không tạo topic.

Sau đó archive writer được đổi sang `ByteArrayFormat`, `ByteArrayConverter` và
`flush.size=1`. Window `2026-07-27T05:00:00Z` đến `06:00:00Z` có 53 lossless
JSON marker `.bin`; live replay 53/53 marker PASS.

## 5. Chọn time window

Archive hiện dùng partition hour:

```text
orders/orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/
```

`START_TIME` inclusive và `END_TIME` exclusive theo UTC. Vì payload protobuf
không có event timestamp, độ chính xác lựa chọn là một partition hour.

Kiểm tra object trước:

```bash
export AWS_PROFILE=tf4-cdo08-admin
export AWS_REGION=us-east-1
export ARCHIVE_BUCKET=tf4-msk-orders-archive-511825856493-us-east-1

aws s3api list-objects-v2 \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --bucket "$ARCHIVE_BUCKET" \
  --prefix 'orders/orders/topic=orders/year=2026/month=07/day=27/hour=05/' \
  --query 'Contents[].{Key:Key,Size:Size,Modified:LastModified}' \
  --output table
```

Chọn cửa sổ nhỏ trước. `MAX_OBJECTS=100` chặn tải nhầm một khoảng quá lớn.

## 6. Syntax và secret scan

Từ repository root:

```bash
bash -n \
  docs/cdo08/week3/mandate20/scripts/msk/rel25-replay-orders-archive.sh

bash -n \
  docs/cdo08/week3/mandate20/scripts/msk/lib/rel25-replay-common.sh

python3 -m py_compile \
  docs/cdo08/week3/mandate20/scripts/msk/rel25-orders-archive-tool.py

if rg -n \
  'AKIA[0-9A-Z]{16}|aws_secret_access_key|aws_session_token|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' \
  docs/cdo08/week3/mandate20/scripts/msk
then
  echo "STOP: review possible secret"
  exit 1
else
  echo "PASS: no common secret pattern found"
fi
```

## 7. Export input an toàn

```bash
export AWS_PROFILE=tf4-cdo08-admin
export AWS_REGION=us-east-1
export EXPECTED_AWS_ACCOUNT_ID=511825856493
export EXPECTED_KUBE_CONTEXT='arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster'

export ARCHIVE_BUCKET=tf4-msk-orders-archive-511825856493-us-east-1
export ARCHIVE_PREFIX=orders/orders
export START_TIME='2026-07-27T05:00:00Z'
export END_TIME='2026-07-27T06:00:00Z'

export RESTORE_DRILL_ID=rel25-20260727-msk-example
export TARGET_TOPIC=orders-replay-drill-rel25-20260727-msk-example
export MAX_OBJECTS=100
export KEEP_TOPIC=false
```

Mỗi lần live drill phải dùng ID/topic mới. Không copy topic cũ đã từng chạy.

## 8. Chạy preflight-only

```bash
export PREFLIGHT_ONLY=true
unset CONFIRM_REPLAY

bash \
  docs/cdo08/week3/mandate20/scripts/msk/rel25-replay-orders-archive.sh \
  2>&1 | tee "rel25-msk-preflight-${RESTORE_DRILL_ID}.log"
```

Preflight:

1. Kiểm tra account/context.
2. Kiểm tra bucket và Kafka Connect deployment.
3. Authenticate Kafka read-only.
4. Chặn tên production/internal topic.
5. Fail nếu target đã tồn tại.
6. Liệt kê object theo time window.
7. Dừng trước download, create topic và produce.

Pass khi log có:

```text
phase=complete message=preflight_only_passed no_topic_created=true
```

## 9. Negative guardrail test

Lệnh này phải fail trước khi gọi Kafka:

```bash
export TARGET_TOPIC=orders
export PREFLIGHT_ONLY=true

bash \
  docs/cdo08/week3/mandate20/scripts/msk/rel25-replay-orders-archive.sh

test "$?" -ne 0
```

Sau test, đặt lại:

```bash
export TARGET_TOPIC=orders-replay-drill-rel25-20260727-msk-example
```

## 10. Chụp trạng thái trước drill

```bash
kubectl -n techx-tf4 exec deployment/kafka-connect-orders-archive -- \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server "$(
    kubectl -n techx-tf4 exec deployment/kafka-connect-orders-archive -- \
      printenv CONNECT_BOOTSTRAP_SERVERS
  )" \
  --command-config /tmp/client.properties \
  --list | sort
```

Xác nhận:

- `orders` tồn tại;
- `$TARGET_TOPIC` chưa tồn tại;
- không có consumer production nào bị thay đổi;
- archive object count không thay đổi do preflight.

## 11. Chạy live drill

```bash
export PREFLIGHT_ONLY=false
export CONFIRM_REPLAY=YES
export REPORT_DIR="$PWD/rel25-replay-reports"

set -o pipefail
bash \
  docs/cdo08/week3/mandate20/scripts/msk/rel25-replay-orders-archive.sh \
  2>&1 | tee "rel25-msk-live-${RESTORE_DRILL_ID}.log"

echo "exit_code=$?"
```

Workflow:

1. Download object vào temporary directory.
2. Nhận diện raw protobuf `OrderResult` hoặc JSON batch marker.
3. Trích protobuf field 1 `order_id`, hoặc marker `order_id/marker_id`.
4. Tính SHA-256 và loại duplicate.
5. Tạo normalized JSON envelope chứa protobuf base64.
6. Tạo topic drill một partition, replication factor 2, retention 6 giờ.
7. Produce `BATCH_START`.
8. Produce order với Kafka key là `order_id/correlation_id`.
9. Produce `BATCH_END`.
10. Consumer drill đọc từ đầu và so marker, ID, hash, missing, unexpected,
    duplicate.
11. Ghi JSON report.
12. EXIT trap cleanup group, topic và local temp files.

## 12. Kết quả bắt buộc

Log thành công:

```text
replay_passed objects_read=... records_read=... replayed=... failed=0
duplicates_skipped=... source_markers_replayed=...
control_markers_replayed=2
```

Report:

```bash
jq . "rel25-replay-reports/${RESTORE_DRILL_ID}-msk-replay-report.json"
```

Report phải có:

```text
objects_read
records_read
replayed
failed
duplicates_skipped
source_markers_replayed
control_markers_replayed
validation
```

`validation=PASS`, `failed=0`, source marker count khớp input và
`control_markers_replayed=2`.

Nếu có report `*-prepare-failure.json`, drill chưa đạt. Sửa archive writer và
tạo archive object lossless mới rồi chạy lại với time window/topic mới.

## 13. Xác nhận cleanup

```bash
kubectl -n techx-tf4 exec deployment/kafka-connect-orders-archive -- \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server "$(
    kubectl -n techx-tf4 exec deployment/kafka-connect-orders-archive -- \
      printenv CONNECT_BOOTSTRAP_SERVERS
  )" \
  --command-config /tmp/client.properties \
  --list | grep -Fx "$TARGET_TOPIC"

test "$?" -ne 0
```

Kiểm tra production:

```bash
kubectl -n techx-tf4 exec deployment/kafka-connect-orders-archive -- \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server "$(
    kubectl -n techx-tf4 exec deployment/kafka-connect-orders-archive -- \
      printenv CONNECT_BOOTSTRAP_SERVERS
  )" \
  --command-config /tmp/client.properties \
  --describe --topic orders
```

Topic `orders`, S3 archive, MSK cluster và archive connector phải vẫn tồn tại và
hoạt động. Không cleanup các resource production này.

## 14. Nếu script dừng giữa chừng

EXIT trap tự cleanup. Nếu log báo topic còn sót, chạy manual cleanup chỉ sau khi
xác nhận tên:

```bash
case "$TARGET_TOPIC" in
  orders-replay-drill-rel25-*) ;;
  *) echo "STOP: unsafe topic"; exit 1 ;;
esac

kubectl -n techx-tf4 exec deployment/kafka-connect-orders-archive -- \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server "$(
    kubectl -n techx-tf4 exec deployment/kafka-connect-orders-archive -- \
      printenv CONNECT_BOOTSTRAP_SERVERS
  )" \
  --command-config /tmp/client.properties \
  --delete --topic "$TARGET_TOPIC"
```

Không thay `$TARGET_TOPIC` bằng `orders`.
