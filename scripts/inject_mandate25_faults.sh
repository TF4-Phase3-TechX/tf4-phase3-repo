#!/bin/bash

# scripts/inject_mandate25_faults.sh
# Kịch bản Chaos Engineering cho Mandate 25: Bơm lỗi qua flagd (Chuẩn SRE)

TARGET_FILE="techx-corp-platform/src/flagd/demo.flagd.json"

# Kiểm tra file tồn tại
if [ ! -f "$TARGET_FILE" ]; then
    echo "Lỗi: Không tìm thấy file $TARGET_FILE. Hãy chạy script từ thư mục gốc của repo."
    exit 1
fi

case "$1" in
  timeout)
    python3 -c "
import json
with open('${TARGET_FILE}', 'r+') as f:
    d = json.load(f)
    d['flags']['llmRateLimitError']['defaultVariant'] = 'on'
    d['flags']['llmInaccurateResponse']['defaultVariant'] = 'off'
    f.seek(0)
    json.dump(d, f, indent=2)
    f.truncate()
"
    echo "Đã bơm lỗi Network/Timeout. Chờ xem Circuit Breaker mở."
    ;;
  malformed)
    python3 -c "
import json
with open('${TARGET_FILE}', 'r+') as f:
    d = json.load(f)
    d['flags']['llmRateLimitError']['defaultVariant'] = 'off'
    d['flags']['llmInaccurateResponse']['defaultVariant'] = 'on'
    f.seek(0)
    json.dump(d, f, indent=2)
    f.truncate()
"
    echo "Đã bơm lỗi JSON rác. Chờ xem luồng Fallback chặn rác."
    ;;
  recover)
    python3 -c "
import json
with open('${TARGET_FILE}', 'r+') as f:
    d = json.load(f)
    d['flags']['llmRateLimitError']['defaultVariant'] = 'off'
    d['flags']['llmInaccurateResponse']['defaultVariant'] = 'off'
    f.seek(0)
    json.dump(d, f, indent=2)
    f.truncate()
"
    echo "Đã tắt bơm lỗi. Kiểm tra trạng thái Recovery."
    ;;
  *)
    echo "Cách sử dụng: bash scripts/inject_mandate25_faults.sh {timeout|malformed|recover}"
    exit 1
esac
