# 📝 ARCHITECTURE & IMPLEMENTATION PROPOSAL
**Dự án:** Task Force 4 · Mặt trận XBrain  
**Chủ đề:** Triển khai Amazon Athena cho Phân tích Forensics Thời gian thực trên Audit Trail  
**Người yêu cầu:** Đội CDO-07 (Auditability) 
**Trạng thái:** Đề xuất triển khai (Implementation Proposal)  

---

## I. BỐI CẢNH & ĐỘNG LỰC HẠ TẦNG (CONTEXT & MANDATE)

Để nâng cao năng lực phân tích bảo mật chuyên sâu (Security Analytics) trong **Directive #4 (Forensic Audit Challenge)**, hệ thống cần khả năng truy vấn SQL tương tác trên khối lượng lớn audit logs mà không cần tải dữ liệu về máy cục bộ. Hiện tại, team đã có đầy đủ 3 nguồn dữ liệu audit được lưu trữ bất biến:

### Nguồn dữ liệu Audit hiện có
1. **AWS CloudTrail Logs** → `s3://tf4-cloudtrail-logs-bucket-{account}/AWSLogs/{account}/CloudTrail/`
2. **AWS Config History** → `s3://tf4-aws-config-staging-{account}-us-east-1/aws-config/`  
3. **EKS Control Plane Audit Logs** → `s3://tf4-eks-audit-logs-{account}/`

### Tại sao cần Amazon Athena?
**Thách thức hiện tại:** Việc tải log nguyên thủy (định dạng .json.gz) từ S3 về máy cục bộ để giải nén và tìm kiếm thủ công là "cơn ác mộng" khi thực hiện phân tích bảo mật. S3 rất tuyệt vời làm kho lưu trữ bất biến (WORM), nhưng không được thiết kế để đọc và phân tích trực tiếp.

**Giải pháp Amazon Athena:**
* **Truy vấn SQL tương tác** trực tiếp trên S3 không cần di chuyển dữ liệu
* **Tận dụng tối đa** cấu hình nén GZIP hiện có → giảm 70-80% chi phí scan
* **Phân vùng thông minh** theo thời gian → chỉ scan đúng partition cần thiết
* **Tích hợp Data Catalog** tự động nhận diện schema JSON của các log streams

---

## II. KIẾN TRÚC GIẢI PHÁP ATHENA (SOLUTION ARCHITECTURE)

### 1. AWS Glue Data Catalog Tables

#### CloudTrail Events Table
```sql
CREATE EXTERNAL TABLE cloudtrail_events (
    eventversion string,
    useridentity struct<
        type:string,
        arn:string,
        userid:string,
        principalid:string,
        accountid:string,
        username:string
    >,
    eventtime string,
    eventsource string,
    eventname string,
    awsregion string,
    sourceipaddress string,
    useragent string,
    requestparameters string,
    responseelements string,
    requestid string,
    eventid string,
    eventtype string,
    apiversion string,
    readonly string,
    recipientaccountid string,
    errorcode string,
    errormessage string
)
PARTITIONED BY (
    year string,
    month string,
    day string
)
STORED AS INPUTFORMAT 'com.amazon.emr.cloudtrail.CloudTrailInputFormat'
OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
LOCATION 's3://tf4-cloudtrail-logs-bucket-{account}/AWSLogs/{account}/CloudTrail/us-east-1/'
```

#### AWS Config History Table
```sql
CREATE EXTERNAL TABLE aws_config_history (
    version string,
    accountid string,
    configurationitemcapturetime string,
    configurationitemstatus string,
    configurationstateid string,
    resourcecreationtime string,
    resourcetype string,
    resourceid string,
    resourcename string,
    awsregion string,
    configuration struct<
        securityGroups:array<struct<
            groupName:string,
            groupId:string,
            ipPermissions:array<struct<
                fromPort:int,
                toPort:int,
                ipProtocol:string,
                ipRanges:array<struct<cidrIp:string>>
            >>
        >>
    >,
    supplementaryconfiguration map<string,string>,
    relationships array<struct<
        resourcetype:string,
        resourceid:string,
        resourcename:string,
        relationshipname:string
    >>
)
PARTITIONED BY (
    year string,
    month string,
    day string
)
STORED AS INPUTFORMAT 'org.apache.hadoop.mapred.TextInputFormat'
OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
LOCATION 's3://tf4-aws-config-staging-{account}-us-east-1/aws-config/'
```

#### EKS Audit Logs Table
```sql
CREATE EXTERNAL TABLE eks_audit_events (
    kind string,
    apiversion string,
    level string,
    auditid string,
    stage string,
    requesturi string,
    verb string,
    user struct<
        username:string,
        uid:string,
        groups:array<string>,
        extra:map<string,array<string>>
    >,
    sourceips array<string>,
    useragent string,
    objectref struct<
        resource:string,
        namespace:string,
        name:string,
        uid:string,
        apigroup:string,
        apiversion:string,
        resourceversion:string
    >,
    responseStatus struct<
        metadata:struct<>,
        status:string,
        message:string,
        reason:string,
        details:struct<
            name:string,
            group:string,
            kind:string,
            uid:string
        >,
        code:int
    >,
    requestobject map<string,string>,
    responseobject map<string,string>,
    requestreceivedtimestamp string,
    stageTimestamp string,
    annotations map<string,string>
)
PARTITIONED BY (
    year string,
    month string,
    day string,
    hour string
)
STORED AS INPUTFORMAT 'org.apache.hadoop.mapred.TextInputFormat'
OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
LOCATION 's3://tf4-eks-audit-logs-{account}/'
```

### 2. Query Templates cho Security Analytics Scenarios

#### Scenario 1: Suspicious Security Group Changes
```sql
-- Tìm ai đã mở port 22 cho 0.0.0.0/0
SELECT 
    c.eventtime,
    c.eventname,
    c.useridentity.arn,
    c.sourceipaddress,
    c.requestparameters,
    cfg.resourcename,
    cfg.configuration.securityGroups[1].ipPermissions
FROM cloudtrail_events c
LEFT JOIN aws_config_history cfg ON 
    json_extract_scalar(c.responseelements, '$.groupId') = cfg.resourceid
WHERE c.eventname IN ('AuthorizeSecurityGroupIngress', 'ModifySecurityGroupRules')
  AND cfg.resourcetype = 'AWS::EC2::SecurityGroup'
  AND c.year = '2026' AND c.month = '07' AND c.day = '15'
  AND cfg.year = '2026' AND cfg.month = '07' AND cfg.day = '15'
ORDER BY c.eventtime DESC
```

#### Scenario 2: Unauthorized Kubernetes Resource Creation
```sql
-- Tìm Pod/Service được tạo trái phép
SELECT 
    e.requestreceivedtimestamp,
    e.user.username,
    e.sourceips[1] as source_ip,
    e.objectref.namespace,
    e.objectref.name,
    e.objectref.resource,
    e.verb,
    e.responseStatus.code
FROM eks_audit_events e
WHERE e.verb IN ('create', 'update', 'patch')
  AND e.objectref.resource IN ('pods', 'services', 'deployments')
  AND e.responseStatus.code < 300  -- successful operations
  AND e.year = '2026' AND e.month = '07' AND e.day = '15'
  AND e.hour IN ('14', '15', '16')  -- focus on specific time window
ORDER BY e.requestreceivedtimestamp DESC
```

#### Scenario 3: Cross-Service Attack Pattern Detection
```sql
-- Phát hiện pattern tấn công liên dịch vụ
WITH suspicious_aws_actions AS (
  SELECT 
    eventtime,
    useridentity.arn,
    sourceipaddress,
    eventname,
    awsregion
  FROM cloudtrail_events
  WHERE eventname IN ('DeleteSecurityGroup', 'CreateUser', 'AttachUserPolicy')
    AND year = '2026' AND month = '07' AND day = '15'
),
suspicious_k8s_actions AS (
  SELECT 
    requestreceivedtimestamp,
    user.username,
    sourceips[1] as source_ip,
    verb,
    objectref.resource
  FROM eks_audit_events
  WHERE verb IN ('create', 'delete')
    AND objectref.resource IN ('secrets', 'configmaps', 'clusterroles')
    AND year = '2026' AND month = '07' AND day = '15'
)
SELECT 
  'Cross-Service Suspicious Activity' as alert_type,
  aws.sourceipaddress,
  aws.eventname,
  aws.eventtime,
  k8s.verb,
  k8s.objectref.resource,
  k8s.requestreceivedtimestamp
FROM suspicious_aws_actions aws
INNER JOIN suspicious_k8s_actions k8s 
  ON aws.sourceipaddress = k8s.source_ip
  AND abs(date_diff('minute', 
    cast(aws.eventtime as timestamp), 
    cast(k8s.requestreceivedtimestamp as timestamp))) < 30
ORDER BY aws.eventtime DESC
```

---

## III. PHÂN TÍCH CHI PHÍ DỰ KIẾN (COST ANALYSIS)

### 1. Mô hình Pricing Amazon Athena (us-east-1)
* **Phí truy vấn:** **$5.00 / TB** dữ liệu được scan
* **Phí AWS Glue Data Catalog:** **$1.00 / 100,000 requests** (để truy vấn metadata)

### 2. Ước tính dung lượng dữ liệu và chi phí thực tế

| Nguồn dữ liệu | Dung lượng/ngày (nén) | Dung lượng/tháng | Chi phí scan 1 security investigation |
| :--- | :--- | :--- | :--- |
| **CloudTrail Logs** | **~5 MB** (KMS encrypted + GZIP) | **~150 MB** | **~$0.001** |
| **AWS Config History** | **~2 MB** (AES256 + JSON) | **~60 MB** | **~$0.0003** |
| **EKS Audit Logs** | **~170 MB** (GZIP compressed) | **~5.1 GB** | **~$0.025** |
| **TỔNG CỘNG** | **~177 MB** | **~5.31 GB** | **~$0.027** |

### 3. Chi phí vận hành thực tế
**Kịch bản phân tích bảo mật thực tế:**
- Mỗi investigation thường scan **2-5 ngày dữ liệu** (emergency response)
- Chi phí scan: **$0.027 × 3 ngày = ~$0.081** per investigation
- **Với 20 investigations/tháng:** **~$1.62**

**So sánh với giải pháp thay thế:**
- **Tải xuống S3 + phân tích local:** **$0** (cost) + **2-4 giờ** (time) per investigation
- **Amazon Athena:** **$0.081** (cost) + **5-10 phút** (time) per investigation

> **Kết luận:** ROI cực kỳ tích cực - tiết kiệm 95% thời gian chỉ với chi phí **~$2/tháng**

---

## IV. ROADMAP TRIỂN KHAI (IMPLEMENTATION ROADMAP)

### Phase 1: Thiết lập Data Catalog (1 ngày)
- [ ] Tạo Glue Database `tf4_audit_forensics`
- [ ] Deploy 3 Glue Tables với schema định nghĩa ở trên
- [ ] Test partition discovery với `MSCK REPAIR TABLE`

### Phase 2: Query Templates & Documentation (1 ngày)  
- [ ] Tạo bộ 15+ query templates cho common security analytics scenarios
- [ ] Documentation về Athena best practices cho team
- [ ] Training session cho security analysts

### Phase 3: Automation & Integration (1 ngày)
- [ ] Automated partition creation via Lambda (daily schedule)
- [ ] Grafana dashboard integration cho security analytics metrics
- [ ] Slack/Teams bot integration cho emergency queries

### Phase 4: Advanced Analytics (tùy chọn)
- [ ] Machine Learning-based anomaly detection với Amazon SageMaker
- [ ] Real-time alerting với Amazon Kinesis Analytics
- [ ] Custom security analytics dashboard với QuickSight

---

## V. YÊU CẦU PHÊ DUYỆT (APPROVAL REQUEST)

Amazon Athena sẽ biến khối dữ liệu audit "chết cứng" trên S3 thành **"security analytics database sống động"**, cho phép team security thực hiện phân tích theo thời gian thực với chi phí cực thấp. Đây là bước tiến quan trọng để đáp ứng **Directive #4** về khả năng phản ứng nhanh với incident.

**Lợi ích chính:**
- ✅ **Giảm 95% thời gian** phân tích bảo mật (từ 2-4 giờ xuống 5-10 phút)
- ✅ **Chi phí cực thấp** (~$2/tháng cho unlimited investigations)  
- ✅ **Zero infrastructure maintenance** (serverless)
- ✅ **SQL-friendly** cho security analysts không cần học syntax mới

**[ ] Approved** **[ ] Rejected** **[ ] Requires Modification** 

*Ý kiến đóng góp từ Reviewer:* ...........................................................................................

---

*Generated by: CDO-07 Team | Date: 2026-07-16 | Version: 1.0*