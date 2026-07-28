import boto3
import time
import sys
import os
import argparse

# Thiết lập UTF-8 để hiển thị tiếng Việt có dấu trên Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description="Script giả lập hành vi bất thường (exfiltration spam) cho Secrets Manager.")
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE"), help="AWS Profile name (tùy chọn, mặc định đọc từ env AWS_PROFILE)")
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"), help="AWS Region (mặc định: us-east-1)")
    parser.add_argument("--secret-id", default="techx/tf4/test-secret-does-not-exist", help="Secret ID để spam gọi API")
    parser.add_argument("--count", type=int, default=15, help="Số lượng request cần spam (mặc định: 15)")
    parser.add_argument("--delay", type=float, default=2.0, help="Thời gian nghỉ giữa các request tính bằng giây (mặc định: 2.0)")

    args = parser.parse_args()

    # Khởi tạo Session dựa trên Profile được cung cấp
    try:
        if args.profile:
            print(f"Sử dụng AWS Profile: {args.profile}")
            session = boto3.Session(profile_name=args.profile)
        else:
            print("Sử dụng Session mặc định (Default session hoặc IAM Role của Pod)")
            session = boto3.Session()
    except Exception as e:
        print(f"[CẢNH BÁO] Không thể load profile '{args.profile}', đang thử dùng default session. Chi tiết: {e}")
        session = boto3.Session()

    client = session.client('secretsmanager', region_name=args.region)

    print("=== BẮT ĐẦU GIẢ LẬP HÀNH VI BẤT THƯỜNG (SPAM GETSECRETVALUE) ===")
    print(f"Mục tiêu: Gửi {args.count} yêu cầu tới Secret '{args.secret_id}'...")

    for i in range(1, args.count + 1):
        try:
            sys.stdout.write(f"\rĐang gửi yêu cầu {i}/{args.count}...")
            sys.stdout.flush()
            
            # Thực hiện gọi secret
            client.get_secret_value(SecretId=args.secret_id)
            
        except client.exceptions.ResourceNotFoundException:
            # Lỗi này là bình thường vì secret không tồn tại, nhưng vẫn được CloudTrail ghi nhận
            pass
        except Exception as e:
            print(f"\n[LỖI] Gặp lỗi khi gọi API ở request {i}: {e}")
            
        time.sleep(args.delay)

    print("\n=== HOÀN THÀNH CHẠY GIẢ LẬP ===")
    print("Vui lòng đợi 1-2 phút và kiểm tra kênh Slack xem có cảnh báo 'MANDATE-11 H2 Anomaly Alarm' màu đỏ không.")

if __name__ == "__main__":
    main()
