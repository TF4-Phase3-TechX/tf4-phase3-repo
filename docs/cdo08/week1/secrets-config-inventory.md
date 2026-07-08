# Secrets and Sensitive Configuration Inventory

This inventory documents all hardcoded passwords, API keys, tokens, connection strings, and sensitive configurations discovered in the static analysis of the `techx-corp-chart`, `deploy`, and `techx-corp-platform/src` directories.

## Review Gate & Sign-off

* **Reviewer**: Nguyên
* **Reviewer Status**: Defer (Pending Initial Review)
* **Status Options**: `Approved` / `Needs Info` / `Defer`
* **Target Date**: End of Week 1 before pitch dry-run

---

## Runtime Verification / Blocker Status

* **Status**: `BLOCKED-BY: TF4 deployment readiness`
* **Details**: EKS cluster environment is not yet accessible locally (target cluster connection refused). Static analysis from source files, charts, and deploy configuration has been fully completed. Runtime verification will be re-run within 24 hours of the environment becoming available.

---

## Search Commands & Patterns Used (Evidence)

The inventory was compiled using ripgrep (`rg`) searches for key sensitive configuration patterns:
```bash
# PASSWORD pattern search
rg -i "PASSWORD" techx-corp-chart/ deploy/ techx-corp-platform/src/

# SECRET pattern search
rg -i "SECRET" techx-corp-chart/ deploy/ techx-corp-platform/src/

# API_KEY pattern search
rg -i "API_KEY" techx-corp-chart/ deploy/ techx-corp-platform/src/

# TOKEN pattern search
rg -i "TOKEN" techx-corp-chart/ deploy/ techx-corp-platform/src/

# DB_CONNECTION_STRING pattern search
rg -i "DB_CONNECTION_STRING" techx-corp-chart/ deploy/ techx-corp-platform/src/

# OPENAI_API_KEY pattern search
rg -i "OPENAI_API_KEY" techx-corp-chart/ deploy/ techx-corp-platform/src/

# SECRET_KEY_BASE pattern search
rg -i "SECRET_KEY_BASE" techx-corp-chart/ deploy/ techx-corp-platform/src/
```

---

## Inventory Table

| File Path | Line/Context | Key/Config Name | Service | Is Secret? | Risk Level | Recommended Handling | Protected Path? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L184) | L184 | `DB_CONNECTION_STRING` | `accounting` | Yes | P1 | Move to Secret | No |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L583) | L583 | `DB_CONNECTION_STRING` | `product-catalog` | Yes | P1 | Move to Secret | No |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L620) | L620 | `DB_CONNECTION_STRING` | `product-reviews` | Yes | P1 | Move to Secret | No |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L760) | L760 | `SECRET_KEY_BASE` | `flagd` / `flagd-ui` | Yes | P1 | Move to Secret / Protected flagd config | Yes |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L846) | L846 | `password` (OTEL metrics) | `postgresql` | Yes | P1 | Needs discussion / Move to Secret | No |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L869) | L869 | `POSTGRES_PASSWORD` | `postgresql` | Yes | P1 | Move to Secret | No |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L1196) | L1196 | `adminPassword` | `grafana` | Yes | P1 | Move to Secret | No |
| [techx-corp-chart/postgresql/init.sql](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/postgresql/init.sql#L4) | L4 | `PASSWORD` | `postgresql` | Yes | P1 | Needs discussion / Move to Secret | No |
| [techx-corp-platform/src/postgresql/init.sql](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-platform/src/postgresql/init.sql#L4) | L4 | `PASSWORD` | `postgresql` | Yes | P1 | Needs discussion / Move to Secret | No |
| [techx-corp-platform/src/flagd-ui/config/dev.exs](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-platform/src/flagd-ui/config/dev.exs#L20) | L20 | `secret_key_base` | `flagd-ui` | False Positive (Dev Key) | Low | Keep | Yes |
| [techx-corp-platform/src/flagd-ui/config/test.exs](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-platform/src/flagd-ui/config/test.exs#L11) | L11 | `secret_key_base` | `flagd-ui` | False Positive (Test Key) | Low | Keep | Yes |
| [techx-corp-chart/values.yaml](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L602) | L602 | `OPENAI_API_KEY` | `product-reviews` | False Positive (Dummy) | None | Keep | No |
| [techx-corp-platform/src/product-reviews/README.md](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-platform/src/product-reviews/README.md#L30) | L30 | `OPENAI_API_KEY` | `product-reviews` | False Positive (Doc Placeholder) | None | Keep | No |
| [deploy/values-flagd-sync.yaml](file:///d:/xbrain/xbrain-learners/phase3/deploy/values-flagd-sync.yaml#L18) | L18 | `Bearer <TOKEN>` | `flagd` | False Positive (Placeholder) | Low | Keep / Needs discussion | Yes |
| [deploy/values-aio-llm.yaml](file:///d:/xbrain/xbrain-learners/phase3/deploy/values-aio-llm.yaml#L10) | L10-11 | `OPENAI_API_KEY` | `product-reviews` | No (Secret Reference) | None | Keep (Best Practice) | No |

---

## Detailed P0/P1 Findings & Proposed Follow-ups

### 1. DB_CONNECTION_STRING in Accounting Service
* **Risk Level**: P1
* **Risk Description**: Hardcoded database credentials (Username/Password) in Helm `values.yaml` exposed in version control. If an attacker gains access to the source code repository, they immediately obtain database access to the accounting schema.
* **Affected Service/File**: `accounting` / [techx-corp-chart/values.yaml:L184](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L184)
* **Evidence**: `value: Host=postgresql;Username=otelu;Password=otelp;Database=otel`
* **Proposed Follow-up (Week 2-3)**: Move the database credentials to a Kubernetes Secret (e.g. `accounting-db-secrets`). In `values.yaml`, override the environment variable to fetch the database connection string from this secret.
* **Priority Draft**: P1

### 2. DB_CONNECTION_STRING in Product-Catalog Service
* **Risk Level**: P1
* **Risk Description**: Hardcoded database password in database connection URL inside `values.yaml`.
* **Affected Service/File**: `product-catalog` / [techx-corp-chart/values.yaml:L583](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L583)
* **Evidence**: `value: postgres://otelu:otelp@postgresql/otel?sslmode=disable`
* **Proposed Follow-up (Week 2-3)**: Store the full connection string in a Kubernetes Secret, or configure the app to read user/password from environment variables sourced via `secretKeyRef` and build the connection string dynamically.
* **Priority Draft**: P1

### 3. DB_CONNECTION_STRING in Product-Reviews Service
* **Risk Level**: P1
* **Risk Description**: Hardcoded database password (`password=otelp`) directly committed to VCS.
* **Affected Service/File**: `product-reviews` / [techx-corp-chart/values.yaml:L620](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L620)
* **Evidence**: `value: host=postgresql user=otelu password=otelp dbname=otel`
* **Proposed Follow-up (Week 2-3)**: Extract the database connection string configuration to a Kubernetes Secret and reference it using `valueFrom.secretKeyRef`.
* **Priority Draft**: P1

### 4. SECRET_KEY_BASE in Flagd-UI (Flagd Sidecar)
* **Risk Level**: P1
* **Risk Description**: Phoenix session signing base key is hardcoded. Hardcoded keys can lead to cookie tampering, session hijacking, or decryption of sensitive state managed by the Elixir flagd-ui application.
* **Affected Service/File**: `flagd` / `flagd-ui` / [techx-corp-chart/values.yaml:L760](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L760)
* **Evidence**: `value: yYrECL4qbNwleYInGJYvVnSkwJuSQJ4ijPTx5tirGUXrbznFIBFVJdPl5t6O9ASw`
* **Proposed Follow-up (Week 2-3)**: Move `SECRET_KEY_BASE` to a Kubernetes Secret, e.g. `flagd-ui-secrets`. Reference it in `values.yaml` using a `secretKeyRef`.
* **Priority Draft**: P1

### 5. POSTGRES_PASSWORD in PostgreSQL Component
* **Risk Level**: P1
* **Risk Description**: Hardcoded database admin password `otel` configured directly in `values.yaml`.
* **Affected Service/File**: `postgresql` / [techx-corp-chart/values.yaml:L869](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L869)
* **Evidence**: `value: otel`
* **Proposed Follow-up (Week 2-3)**: Move the password to a Kubernetes Secret and inject it to the database deployment using `valueFrom.secretKeyRef`.
* **Priority Draft**: P1

### 6. Scraper Password in PostgreSQL Component
* **Risk Level**: P1
* **Risk Description**: Hardcoded metrics collector scraper credentials in Pod annotations metadata inside `values.yaml`.
* **Affected Service/File**: `postgresql` / [techx-corp-chart/values.yaml:L846](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L846)
* **Evidence**: `password: otel` under `io.opentelemetry.discovery.metrics/config` annotation.
* **Proposed Follow-up (Week 2-3)**: Review metrics scraper credentials handling; credentials should be stored in the OpenTelemetry Collector's configuration secrets or fetched dynamically instead of exposing them in pod annotations which are visible to anyone queryable in the cluster.
* **Priority Draft**: P1

### 7. adminPassword in Grafana Component
* **Risk Level**: P1
* **Risk Description**: Default administrator credentials `admin` for the Grafana dashboard are hardcoded.
* **Affected Service/File**: `grafana` / [techx-corp-chart/values.yaml:L1196](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/values.yaml#L1196)
* **Evidence**: `adminPassword: admin`
* **Proposed Follow-up (Week 2-3)**: Configure the Grafana subchart to read the administrator password from a Kubernetes Secret, or disable default form login/credentials since anonymous administrator access is already enabled in this environment.
* **Priority Draft**: P1

### 8. Hardcoded Database User Password in init.sql Scripts
* **Risk Level**: P1
* **Risk Description**: Static credential initialization script `CREATE USER otelu WITH PASSWORD 'otelp';` stored in source control.
* **Affected Service/File**: `postgresql` / [techx-corp-chart/postgresql/init.sql:L4](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-chart/postgresql/init.sql#L4) & [techx-corp-platform/src/postgresql/init.sql:L4](file:///d:/xbrain/xbrain-learners/phase3/techx-corp-platform/src/postgresql/init.sql#L4)
* **Evidence**: `CREATE USER otelu WITH PASSWORD 'otelp';`
* **Proposed Follow-up (Week 2-3)**: Refactor PostgreSQL database initialization to dynamically set the password using environment variables injected from secrets at deploy time, or mount a database initialization script template that has passwords dynamically rendered.
* **Priority Draft**: P1
