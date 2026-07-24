# CDO08-REL-23 - Shared helpers cho bo script accounting recovery.
# Dot-source truoc khi dung: . "$PSScriptRoot\00-common.ps1"
# Xem docs/cdo08/week3/mandate20/implementation/CDO08-REL-23-accounting-rds-isolation-plan.md

$ErrorActionPreference = 'Stop'

function Assert-LastExitCode {
    param([string]$Message = 'Command failed')
    if ($LASTEXITCODE -ne 0) { throw "$Message (exit $LASTEXITCODE)" }
}

function ConvertTo-Base64Utf8 {
    param([Parameter(Mandatory)][string]$PlainText)
    [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($PlainText))
}

function Get-UtcNowIso {
    (Get-Date).ToUniversalTime().ToString('o')
}

function New-RunId {
    (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ').ToLower()
}

function New-RandomPassword {
    <# Sinh password ngau nhien an toan cho RDS master (chi chu/so - tranh moi ky tu RDS cam: / " @ khoang trang). #>
    param([int]$Length = 24)
    $chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    $bytes = New-Object byte[] $Length
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

function Get-ProductionAppCreds {
    <#
    Doc secret rds-postgres-secret/dotnet-conn-string (K8s, namespace techx-tf4) va parse format Npgsql
    "Host=..;Port=..;Database=..;Username=..;Password=..;.." thanh cac field roi. Day la credential
    techx_app - IAM cua role van hanh CHI cho phep doc dung secret nay (khong doc duoc MasterUserSecret
    cua RDS), nen moi thao tac can quyen DDL/owner (ALTER SCHEMA, DROP SCHEMA...) phai ket noi bang
    techx_app roi "SET ROLE postgres" (yeu cau da GRANT postgres TO techx_app truoc, 1 lan, ngoai bo
    script nay) - dung tham so -SetRole cua New-PgClientPod. Khong echo gia tri ra console.
    #>
    param([string]$Namespace = 'techx-tf4')

    $b64 = kubectl get secret rds-postgres-secret -n $Namespace -o jsonpath='{.data.dotnet-conn-string}'
    Assert-LastExitCode 'kubectl get secret rds-postgres-secret'
    if ([string]::IsNullOrEmpty($b64)) { throw 'Khong doc duoc secret rds-postgres-secret/dotnet-conn-string' }
    $connString = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64))

    $fields = @{}
    foreach ($pair in $connString -split ';') {
        if ([string]::IsNullOrWhiteSpace($pair)) { continue }
        $idx = $pair.IndexOf('=')
        if ($idx -lt 0) { continue }
        $fields[$pair.Substring(0, $idx).Trim()] = $pair.Substring($idx + 1).Trim()
    }
    return @{
        Host     = $fields['Host']
        Port     = $fields['Port']
        Database = $fields['Database']
        User     = $fields['Username']
        Password = $fields['Password']
    }
}

function New-PgClientPod {
    <#
    Tao namespace (idempotent) + secret + pod postgres:17 dung de chay psql/pg_dump/pg_restore.
    Secret luu PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE - khong bao gio echo gia tri that ra console.
    Tra ve @{ Namespace; PodName } de dung voi Invoke-PgSql / Invoke-PgSqlFile / Remove-PgClientPod.
    #>
    param(
        [Parameter(Mandatory)][string]$Namespace,
        [Parameter(Mandatory)][string]$PodName,
        [Parameter(Mandatory)][string]$PgHost,
        [string]$PgPort = '5432',
        [Parameter(Mandatory)][string]$PgUser,
        [Parameter(Mandatory)][string]$PgPassword,
        [Parameter(Mandatory)][string]$PgDatabase,
        [string]$SetRole
    )

    kubectl create namespace $Namespace --dry-run=client -o yaml | kubectl apply -f - | Out-Null
    Assert-LastExitCode 'kubectl create namespace'

    $secretYaml = @"
apiVersion: v1
kind: Secret
metadata:
  name: pg-creds
  namespace: $Namespace
type: Opaque
data:
  PGHOST: $(ConvertTo-Base64Utf8 $PgHost)
  PGPORT: $(ConvertTo-Base64Utf8 $PgPort)
  PGUSER: $(ConvertTo-Base64Utf8 $PgUser)
  PGPASSWORD: $(ConvertTo-Base64Utf8 $PgPassword)
  PGDATABASE: $(ConvertTo-Base64Utf8 $PgDatabase)
"@
    $secretYaml | kubectl apply -f - | Out-Null
    Assert-LastExitCode 'kubectl apply secret pg-creds'

    # PGOPTIONS lam connection tu dong "SET ROLE" ngay sau khi authenticate - ap dung cho MOI libpq
    # client (psql/pg_dump/pg_restore deu ton trong), khong can sua tung cau SQL rieng. Yeu cau da
    # GRANT $SetRole TO $PgUser tu truoc (xem plan doc §9) - neu chua GRANT, ket noi se fail ngay.
    # Chi chen block "env:" khi co -SetRole - list rong/null co the bi K8s tu choi validate.
    $envBlock = ''
    if ($SetRole) {
        $envBlock = "    env:`n    - name: PGOPTIONS`n      value: `"-c role=$SetRole`"`n"
    }

    $podYaml = @"
apiVersion: v1
kind: Pod
metadata:
  name: $PodName
  namespace: $Namespace
spec:
  restartPolicy: Never
  containers:
  - name: pg-client
    image: postgres:17
    command: ["sleep", "3600"]
    envFrom:
    - secretRef:
        name: pg-creds
$envBlock    resources:
      requests: { cpu: 5m, memory: 32Mi }
      limits: { cpu: 200m, memory: 128Mi }
    securityContext:
      runAsNonRoot: true
      runAsUser: 999
      allowPrivilegeEscalation: false
      capabilities:
        drop: ["ALL"]
      seccompProfile:
        type: RuntimeDefault
"@
    $podYaml | kubectl apply -f - | Out-Null
    Assert-LastExitCode 'kubectl apply pod pg-client'
    kubectl wait --for=condition=Ready "pod/$PodName" -n $Namespace --timeout=90s | Out-Null
    Assert-LastExitCode 'kubectl wait pg-client ready'

    return @{ Namespace = $Namespace; PodName = $PodName }
}

function Remove-PgClientPod {
    param(
        [Parameter(Mandatory)][string]$Namespace,
        [Parameter(Mandatory)][string]$PodName
    )
    kubectl delete pod $PodName -n $Namespace --ignore-not-found --wait=false | Out-Null
    kubectl delete secret pg-creds -n $Namespace --ignore-not-found | Out-Null
}

function Invoke-PgSql {
    <#
    Chay 1 cau SQL don, in ket qua ra stdout. Dung stdin-pipe (khong dung -c $Sql) vi truyen SQL
    qua argument cho native exe co the vo tinh be gay khi SQL chua dau nhay kep (vd accounting."order") -
    PowerShell/Windows khong tu escape dau nhay kep long trong 1 argument cho tien trinh con.
    #>
    param(
        [Parameter(Mandatory)][string]$Namespace,
        [Parameter(Mandatory)][string]$PodName,
        [Parameter(Mandatory)][string]$Sql
    )
    $Sql | kubectl exec -i -n $Namespace $PodName -- psql -v ON_ERROR_STOP=1
    Assert-LastExitCode "psql: $Sql"
}

function Invoke-PgSqlScalar {
    <# Chay 1 cau SQL, tra ve gia tri dau tien dang string (dung -At). Xem ghi chu o Invoke-PgSql. #>
    param(
        [Parameter(Mandatory)][string]$Namespace,
        [Parameter(Mandatory)][string]$PodName,
        [Parameter(Mandatory)][string]$Sql
    )
    $out = $Sql | kubectl exec -i -n $Namespace $PodName -- psql -v ON_ERROR_STOP=1 -At
    Assert-LastExitCode "psql (scalar): $Sql"
    return $out
}

function Invoke-PgSqlFile {
    <# Pipe 1 script SQL nhieu cau lenh qua stdin cua psql trong pod. #>
    param(
        [Parameter(Mandatory)][string]$Namespace,
        [Parameter(Mandatory)][string]$PodName,
        [Parameter(Mandatory)][string]$SqlScript
    )
    $SqlScript | kubectl exec -i -n $Namespace $PodName -- psql -v ON_ERROR_STOP=1
    Assert-LastExitCode 'psql script'
}

function New-KafkaClientPod {
    <#
    Pod dung kafka-consumer-groups.sh, lay credential tu K8s secret msk-kafka-secret co san
    trong techx-tf4 (cung secret 'accounting' Deployment dang dung). Sinh /tmp/client.properties
    ben trong pod tu chinh cac bien moi truong do (khong echo ra console may local).

    Dung image apache/kafka (goc tu Apache Kafka project, kafka_versions=3.9.x khop msk.tf) thay vi
    confluentinc/cp-kafka - anh Apache chinh thuc chac chan co script *.sh duoi /opt/kafka/bin, tranh
    doan Confluent co the dong goi lai ten binary khac (chua kiem chung duoc do khong co mang de xac
    minh manifest image tai thoi diem viet). Van nen smoke-test 1 lan truoc rehearsal dau tien (xem
    plan §9 - Rui ro can xac nhan).
    #>
    param(
        [Parameter(Mandatory)][string]$Namespace,
        [Parameter(Mandatory)][string]$PodName,
        [string]$KafkaSecretName = 'msk-kafka-secret',
        [string]$KafkaSecretNamespace = 'techx-tf4',
        [string]$KafkaImage = 'apache/kafka:3.9.0',
        [string]$KafkaBinDir = '/opt/kafka/bin'
    )
    kubectl create namespace $Namespace --dry-run=client -o yaml | kubectl apply -f - | Out-Null
    Assert-LastExitCode 'kubectl create namespace (kafka pod)'

    # Copy nguyen ban base64 cua secret sang namespace ops (khong giai ma)
    $srcJson = kubectl get secret $KafkaSecretName -n $KafkaSecretNamespace -o json | ConvertFrom-Json
    Assert-LastExitCode 'kubectl get secret msk-kafka-secret'
    $copyYaml = [pscustomobject]@{
        apiVersion = 'v1'
        kind       = 'Secret'
        metadata   = @{ name = $KafkaSecretName; namespace = $Namespace }
        type       = $srcJson.type
        data       = $srcJson.data
    } | ConvertTo-Json -Depth 6
    $copyYaml | kubectl apply -f - | Out-Null
    Assert-LastExitCode 'kubectl apply secret msk-kafka-secret (copy)'

    $podYaml = @"
apiVersion: v1
kind: Pod
metadata:
  name: $PodName
  namespace: $Namespace
spec:
  restartPolicy: Never
  containers:
  - name: kafka-client
    image: $KafkaImage
    command: ["sleep", "3600"]
    env:
    - name: KAFKA_ADDR
      valueFrom: { secretKeyRef: { name: $KafkaSecretName, key: kafka-address } }
    - name: KAFKA_SECURITY_PROTOCOL
      valueFrom: { secretKeyRef: { name: $KafkaSecretName, key: security-protocol } }
    - name: KAFKA_SASL_MECHANISM
      valueFrom: { secretKeyRef: { name: $KafkaSecretName, key: sasl-mechanism } }
    - name: KAFKA_USERNAME
      valueFrom: { secretKeyRef: { name: $KafkaSecretName, key: username } }
    - name: KAFKA_PASSWORD
      valueFrom: { secretKeyRef: { name: $KafkaSecretName, key: password } }
    resources:
      requests: { cpu: 10m, memory: 128Mi }
      limits: { cpu: 300m, memory: 256Mi }
    securityContext:
      runAsNonRoot: true
      runAsUser: 1000
      allowPrivilegeEscalation: false
      capabilities:
        drop: ["ALL"]
      seccompProfile:
        type: RuntimeDefault
"@
    $podYaml | kubectl apply -f - | Out-Null
    Assert-LastExitCode 'kubectl apply pod kafka-client'
    kubectl wait --for=condition=Ready "pod/$PodName" -n $Namespace --timeout=90s | Out-Null
    Assert-LastExitCode 'kubectl wait kafka-client ready'

    # Sinh client.properties ngay trong pod tu env - khong di qua console cua may local
    $genScript = @'
cat > /tmp/client.properties <<EOF
security.protocol=${KAFKA_SECURITY_PROTOCOL}
sasl.mechanism=${KAFKA_SASL_MECHANISM}
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";
EOF
'@
    $genScript | kubectl exec -i -n $Namespace $PodName -- sh
    Assert-LastExitCode 'sinh client.properties trong kafka pod'

    return @{ Namespace = $Namespace; PodName = $PodName }
}

function Remove-KafkaClientPod {
    param(
        [Parameter(Mandatory)][string]$Namespace,
        [Parameter(Mandatory)][string]$PodName,
        [string]$KafkaSecretName = 'msk-kafka-secret'
    )
    kubectl delete pod $PodName -n $Namespace --ignore-not-found --wait=false | Out-Null
    kubectl delete secret $KafkaSecretName -n $Namespace --ignore-not-found | Out-Null
}
