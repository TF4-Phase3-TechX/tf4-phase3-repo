# CDO08 SEC-05 - Bằng chứng xác minh Mandate 01

## Tóm tắt

Mandate 01 yêu cầu:

- Storefront vẫn truy cập công khai từ internet.
- Các cổng vận hành/nội bộ không truy cập được từ internet công khai.
- Người có quyền vẫn có đường truy cập riêng tư vào các cổng vận hành.
- Đường truy cập riêng tư có bằng chứng audit.

Thời điểm xác minh:

```text
2026-07-13T23:18:47+07:00
```

Public ALB:

```text
http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com
```

Image runtime của `frontend-proxy`:

```text
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:97dbd1b-frontend-proxy
```

## 1. Xác minh public exposure

Lệnh kiểm tra:

```bash
ALB="http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"

date -Iseconds
for path in / /grafana /grafana/ /jaeger /jaeger/ui/ /loadgen /loadgen/ /feature /feature/ /flagservice /flagservice/ /otlp-http /otlp-http/; do
  code=$(/usr/bin/curl -sS -o /tmp/sec05-curl-body -w '%{http_code}' "$ALB$path")
  bytes=$(/usr/bin/wc -c < /tmp/sec05-curl-body | /usr/bin/tr -d ' ')
  printf '%-16s -> %s (%s bytes)\n' "$path" "$code" "$bytes"
done
```

Kết quả:

```text
2026-07-13T23:18:47+07:00
/                -> 200 (11347 bytes)
/grafana         -> 404 (0 bytes)
/grafana/        -> 404 (0 bytes)
/jaeger          -> 404 (0 bytes)
/jaeger/ui/      -> 404 (0 bytes)
/loadgen         -> 404 (0 bytes)
/loadgen/        -> 404 (0 bytes)
/feature         -> 404 (0 bytes)
/feature/        -> 404 (0 bytes)
/flagservice     -> 404 (0 bytes)
/flagservice/    -> 404 (0 bytes)
/otlp-http       -> 404 (0 bytes)
/otlp-http/      -> 404 (0 bytes)
```

Kết luận:

```text
PASS
```

Storefront vẫn public với `HTTP 200`. Grafana, Jaeger, Load Generator, route flagd UI, route flagservice và route OTLP HTTP không còn truy cập được từ internet công khai.

## 2. Xác minh runtime health

Lệnh kiểm tra:

```bash
kubectl -n techx-tf4 get deploy frontend frontend-proxy checkout cart payment shipping product-catalog flagd -o wide
kubectl -n techx-observability get deploy grafana jaeger -o wide
kubectl -n techx-tf4 get svc grafana jaeger load-generator flagd frontend-proxy -o wide
kubectl -n techx-tf4 get ingress techx-alb-ingress -o wide
```

Kết quả chính:

```text
frontend          2/2 available
frontend-proxy    2/2 available
checkout          2/2 available
cart              2/2 available
payment           2/2 available
shipping          2/2 available
product-catalog   2/2 available
flagd             1/1 available

grafana           1/1 available
jaeger            1/1 available

techx-alb-ingress address:
k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com
```

Kết luận:

```text
PASS
```

Deployment SEC-05 không làm hỏng storefront path hoặc các service chính nằm trên checkout path trong khoảng thời gian xác minh này.

## 3. Xác minh private access

Đường truy cập riêng tư:

```text
AWS SSM Session Manager
-> EC2 Bastion
-> kubectl port-forward on bastion
-> Grafana / Jaeger / Load Generator
```

Bastion:

```text
InstanceId: i-072084d1cf0b2f1c9
Name: tf4-portal-bastion
Private IP: 10.0.10.55
SSM status: Online
```

SSM session:

```text
SessionId: nguyen-cqzlbzsh4onaob6vh2536k3vj4
Host: ip-10-0-10-55.ec2.internal
Time: 2026-07-13T16:28:54+00:00
```

Identity của bastion:

```text
arn:aws:sts::511825856493:assumed-role/tf4-portal-bastion-role/i-072084d1cf0b2f1c9
```

Kubernetes context từ bastion:

```text
arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster
```

Service discovery từ bastion:

```text
techx-observability/grafana   ClusterIP   172.20.108.200   80/TCP
techx-observability/jaeger    ClusterIP   172.20.88.27     16686/TCP and other ports
techx-tf4/load-generator      ClusterIP   172.20.219.77    8089/TCP
```

Kết quả kiểm tra private access:

Bằng chứng truy cập thành công qua SSM Tunnel:

*   **Grafana UI (`http://localhost:3000` chuyển hướng về `/grafana/dashboards`):**
    ![Grafana Private Access Screenshot](../image/grafana_private.png)

*   **Jaeger UI (`http://localhost:16686/jaeger/ui/`):**
    ![Jaeger Private Access Screenshot](../image/jaeger_private.png)

*   **Locust Load Generator UI (`http://localhost:8089`):**
    ![Locust Private Access Screenshot](../image/locust_private.png)

Kết luận:

```text
PASS
```

Người có quyền vẫn truy cập được các cổng vận hành thông qua SSM Bastion và Kubernetes port-forward chạy từ bastion host. Grafana trả `301` khi truy cập `/` là hoàn toàn bình thường do cơ chế chuyển hướng về đúng path prefix `/grafana/` đã cấu hình.

## 4. Bằng chứng audit từ SSM

Lệnh kiểm tra:

```bash
aws ssm describe-sessions \
  --region us-east-1 \
  --state History \
  --max-results 10 \
  --query 'Sessions[].{SessionId:SessionId,Target:Target,Owner:Owner,Status:Status,StartDate:StartDate,EndDate:EndDate}' \
  --output table
```

Kết quả chính:

```text
SessionId: nguyen-cqzlbzsh4onaob6vh2536k3vj4
Target:    i-072084d1cf0b2f1c9
Owner:     arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10/nguyen
Status:    Terminated
StartDate: 2026-07-13T23:28:39.495000+07:00
EndDate:   2026-07-13T23:29:08.710000+07:00
```

Kết luận:

```text
PASS với SSM session history.
PENDING với CloudTrail lookup do role xác minh hiện tại chưa có quyền.
```

Role xác minh hiện tại có thể xác nhận SSM session history. Tuy nhiên, truy vấn trực tiếp CloudTrail đang bị chặn với role này:

```text
AccessDeniedException:
not authorized to perform: cloudtrail:LookupEvents
```

CDO07/Admin cần chạy lệnh sau để attach bằng chứng CloudTrail cuối cùng:

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --max-results 10 \
  --query 'Events[].{Time:EventTime,User:Username,EventName:EventName,Resources:Resources}' \
  --output table
```

## Trạng thái cuối

```text
Mandate 01 - yêu cầu public exposure: PASS
Mandate 01 - yêu cầu private access: PASS
Mandate 01 - bằng chứng audit SSM session: PASS
Mandate 01 - CloudTrail independent lookup: PENDING quyền CDO07/Admin
```

Hệ thống hiện đã đáp ứng yêu cầu network exposure cốt lõi: storefront vẫn public, các cổng vận hành không còn public, và người có quyền vẫn truy cập được qua SSM Bastion.
