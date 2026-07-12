# Performance Baseline Plan

**Epic**: EPIC-03 Performance Efficiency  
**Task**: PERF-02 - Prepare Performance Baseline Plan  
**Date**: 2026-07-08

---

## OVERVIEW

This document consolidates the performance baseline testing plan for TechX Corp Platform, covering test scenarios, tooling, and safety mechanisms.

**Context**:
- **System**: 27 microservices, polyglot architecture
- **Critical SLOs**:
  - Checkout: ≥ 99.0% success rate
  - Browse/Cart: ≥ 99.5% success rate
  - p95 latency < 1s
- **Budget**: $300/week (hard limit)
- **Test Environment**: EKS cluster `techx-tf4`

---

## PERF-02.1: Performance Baseline Test Scenarios

**Owner**: Hoàng  
**Support**: Tín

### **1. Smoke Test**

**Objective**: Verify system is healthy before load testing

**Scenario**:
```
1 user × 1 iteration:
  → GET / (homepage)
  → GET /api/products (list)
  → GET /api/products/{id} (detail)
  → GET /api/cart (view cart)
```

**Success Criteria**:
- All requests return 200 OK
- No 5xx errors
- p95 latency < 2s (lenient for cold start)

**Duration**: 1 minute

---

### **2. Browse Baseline**

**Objective**: Measure product browsing performance under normal load

**Scenario**:
```
10 concurrent users, ramp-up 1 user/sec:
  → 40% Browse products (list/search)
  → 30% View product details
  → 20% Get recommendations
  → 10% View ads
```

**Target Metrics**:
- Request rate: ~50 RPS
- Error rate: < 0.5% (SLO: 99.5%)
- p95 latency: < 1s
- p99 latency: < 2s

**Duration**: 10 minutes

**Expected Bottlenecks**:
- N+1 currency conversion calls
- Product catalog search without LIMIT

---

### **3. Cart Baseline**

**Objective**: Measure cart operations performance

**Scenario**:
```
10 concurrent users:
  → 50% View cart
  → 30% Add to cart
  → 20% Update quantity
```

**Target Metrics**:
- Request rate: ~30 RPS
- Error rate: < 0.5% (SLO: 99.5%)
- p95 latency: < 500ms (cart should be fast)

**Duration**: 10 minutes

**Expected Bottlenecks**:
- Valkey-cart connection pool
- Cart service single replica (SPOF risk)

---

### **4. Checkout Baseline**

**Objective**: Measure end-to-end checkout performance (revenue-critical)

**Scenario**:
```
5 concurrent users:
  → Add product to cart
  → Fill checkout form
  → Submit order
  → Wait for confirmation
```

**Target Metrics**:
- Request rate: ~10 orders/minute
- Success rate: ≥ 99.0% (SLO)
- p95 latency: < 3s
- p99 latency: < 5s

**Duration**: 15 minutes

**Expected Bottlenecks**:
- Sequential dependencies (currency, shipping, payment, email)
- Connection pool exhaustion (INC-1 history)
- Missing timeout/retry

---

### **5. AI Review Baseline**

**Objective**: Measure AI-powered review summary performance

**Scenario**:
```
5 concurrent users:
  → View product details
  → Load reviews + AI summary
  → Ask AI assistant question
```

**Target Metrics**:
- Request rate: ~5 RPS
- Error rate: Best-effort (no hard SLA)
- p95 latency: < 5s (AI call expected to be slow)
- AI summary quality: No incorrect/hallucinated content

**Duration**: 10 minutes

**Expected Bottlenecks**:
- LLM service latency
- LLM cost accumulation

---

### **Combined Load Test (Optional Week 2)**

**Scenario**: All flows running simultaneously
```
30 concurrent users:
  → 40% Browse
  → 20% Cart operations
  → 20% Checkout
  → 10% AI reviews
  → 10% Mixed
```

**Duration**: 30 minutes  
**Purpose**: Stress test to find system limits

---

## PERF-02.2: Test Tool và Cách Chạy

**Owner**: Hoàng  
**Support**: Tuấn

### **Tool Selection**

#### **Chosen: load-generator (Locust)**

**Rationale**:
- Already integrated in Helm chart
- Locust-based (Python, flexible scripting)
- OpenTelemetry instrumented
- Web UI for real-time monitoring
- Supports both API and browser traffic

**Alternatives Considered**:
- k6: Modern, but requires separate setup
- Locust standalone: Redundant with built-in
- JMeter: Heavy, GUI-based

**Decision**: Use built-in `load-generator` service

---

### **Configuration**

#### **Helm Values**
```yaml
load-generator:
  enabled: true
  env:
    - name: LOCUST_USERS
      value: "10"              # Concurrent users
    - name: LOCUST_SPAWN_RATE
      value: "1"               # Ramp-up rate (users/sec)
    - name: LOCUST_HOST
      value: "http://frontend-proxy:8080"
    - name: LOCUST_AUTOSTART
      value: "false"           # Manual start for control
    - name: LOCUST_BROWSER_TRAFFIC_ENABLED
      value: "true"            # Include browser tests
```

#### **Start Load Test**
```bash
# Method 1: Scale deployment
kubectl scale deployment/load-generator --replicas=1 -n techx-tf4

# Method 2: Locust Web UI
kubectl port-forward svc/load-generator 8089:8089 -n techx-tf4
# → Open http://localhost:8089
# → Configure users & spawn rate
# → Click "Start swarming"

# Method 3: Helm upgrade
helm upgrade techx-corp ./techx-corp-chart \
  -n techx-tf4 \
  --reuse-values \
  --set load-generator.env[10].value="true"  # LOCUST_AUTOSTART
```

#### **Stop Load Test**
```bash
# Scale down
kubectl scale deployment/load-generator --replicas=0 -n techx-tf4

# Or via Web UI: Click "Stop"
```

---

### **Test Execution Commands**

#### **Pre-Test Checklist**
```bash
# 1. Verify all pods running
kubectl get pods -n techx-tf4

# 2. Check baseline CPU/memory in Grafana
# Capture the namespace and node resource panels for techx-tf4.

# 3. Open Grafana
kubectl port-forward svc/frontend-proxy 8080:8080 -n techx-tf4
# → http://localhost:8080/grafana/

# 4. Start monitoring script
./scripts/monitor-load-test.sh &
```

#### **Run Test Sequence**
```bash
# Test 1: Smoke test (1 min)
# - Set users: 1
# - Duration: 1 min
# - Verify: All green

# Test 2: Browse baseline (10 min)
# - Set users: 10
# - Spawn rate: 1/sec
# - Monitor: Latency, error rate

# Test 3: Cart baseline (10 min)
# - Same config, observe cart metrics

# Test 4: Checkout baseline (15 min)
# - Users: 5
# - Monitor: Success rate ≥99%

# Test 5: AI review baseline (10 min)
# - Users: 5
# - Monitor: LLM latency, cost
```

---

### **Input Parameters**

| Parameter | Smoke | Browse | Cart | Checkout | AI Review |
|-----------|-------|--------|------|----------|-----------|
| Users | 1 | 10 | 10 | 5 | 5 |
| Spawn Rate | 1 | 1 | 1 | 1 | 1 |
| Duration | 1 min | 10 min | 10 min | 15 min | 10 min |

---

### **Output to Capture**

#### **Real-time Metrics** (during test)
```text
# CPU/Memory
Theo dõi dashboard CPU/Memory của namespace `techx-tf4` trong Grafana với refresh 5 giây.

# Request stats (Locust UI)
# → http://localhost:8089
# → Captures: RPS, response time, failures
```

#### **Post-Test Evidence**
```text
# 1. Resource usage
Capture Grafana CPU/Memory panels for namespace `techx-tf4` and worker nodes.

# 2. Grafana screenshots
# - Service latency dashboard
# - Error rate panel
# - Resource usage

# 3. Jaeger traces
# - Slowest 10 checkout traces
# - AI review trace examples

# 4. Locust report
# - Export CSV from UI
# - Save screenshot of statistics

# 5. Application logs
kubectl logs -n techx-tf4 deployment/checkout --tail=500 > logs-checkout.log
kubectl logs -n techx-tf4 deployment/accounting --tail=500 > logs-accounting.log
```

---

## PERF-02.3: Stop Conditions

**Owner**: Tuấn  
**Reviewer**: Hoàng

### **Automated Stop Conditions**

Load tests will automatically stop when ANY threshold is exceeded:

#### **1. Error Rate > 5%**
```
Trigger: (5xx_responses / total_requests) × 100 > 5%
Measurement: kubectl logs | grep "ERROR" 
Rationale: 5× SLO violation (1% allowed)
```

#### **2. CPU > 90%**
```
Trigger: Any pod CPU usage > 90%
Measurement: Grafana CPU panel / PromQL
Rationale: Prevent throttling, cascading failure
```

#### **3. Memory > 85%**
```
Trigger: Any pod memory > 85% of limit
Measurement: Grafana memory panel / PromQL
Rationale: Prevent OOMKill, pod restart
```

#### **4. Latency > 5s**
```
Trigger: p95 latency > 5s for critical endpoints
Measurement: Prometheus query / Jaeger
Rationale: 5× baseline SLO (p95 < 1s)
```

#### **5. Cost Spike**
```
Trigger: Node count > baseline + 1 (>3 nodes)
Measurement: kubectl get nodes
Rationale: Each node = ~$60/week extra cost
```

#### **6. Load Generator Overload**
```
Trigger: LG pod CPU > 80% OR Memory > 1200Mi
Measurement: Grafana load-generator CPU/Memory panels
Rationale: Ensure test validity (generator not bottleneck)
```

---

### **Monitoring Script**

**File**: `scripts/monitor-load-test.sh`

**Usage**:
```bash
# Start monitoring
./scripts/monitor-load-test.sh

# Auto-stops load test when threshold exceeded
# Captures evidence automatically
# Logs to: load-test-monitor-YYYYMMDD-HHMMSS.log
```

**Key Features**:
- Checks all 6 conditions every 30 seconds
- Scales load-generator to 0 when threshold exceeded
- Captures evidence (pods, metrics, logs)
- Color-coded logging (red/yellow/green)

---

### **Manual Stop Triggers**

Manually stop if:
- SLO dashboard shows violation trend
- AWS Cost Explorer alert received
- Team observes customer impact
- Infrastructure issues detected

**Command**:
```bash
kubectl scale deployment/load-generator --replicas=0 -n techx-tf4
```

---

## SUCCESS CRITERIA

### **For Each Test Scenario**

**Smoke Test**:
- All requests 200 OK
- No errors
- Baseline established

**Browse Baseline**:
- Error rate < 0.5%
- p95 latency < 1s
- No stop conditions triggered

**Cart Baseline**:
- Error rate < 0.5%
- p95 latency < 500ms
- Valkey-cart stable

**Checkout Baseline**:
- Success rate ≥ 99%
- p95 latency < 3s
- No connection pool exhaustion

**AI Review Baseline**:
- Best-effort latency < 5s
- No incorrect summaries
- LLM cost tracked

---

## EVIDENCE FOLDER STRUCTURE

```
docs/evidence/epic-03-performance-efficiency/
├── 02-performance-baseline-plan.md (this file)
├── runtime/
│   ├── smoke-test/
│   │   ├── grafana-screenshot.png
│   │   ├── locust-stats.csv
│   │   └── evidence-pods.txt
│   ├── browse-baseline/
│   ├── cart-baseline/
│   ├── checkout-baseline/
│   └── ai-review-baseline/
└── monitor-logs/
    └── load-test-monitor-*.log
```

---

## TEST EXECUTION WORKFLOW

```
1. Pre-test
   ├─ Verify system health (all pods running)
   ├─ Start monitoring script
   ├─ Open Grafana dashboard
   └─ Baseline metrics snapshot

2. Run Tests (Sequential)
   ├─ Smoke test (1 min)
   ├─ Browse baseline (10 min)
   ├─ Cart baseline (10 min)
   ├─ Checkout baseline (15 min)
   └─ AI review baseline (10 min)

3. Post-test
   ├─ Capture evidence (screenshots, logs, metrics)
   ├─ Stop load generator
   ├─ Analyze results
   ├─ Document findings
   └─ Create recommendations
```
