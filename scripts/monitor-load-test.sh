#!/bin/bash
# Performance Test Monitor with Auto-Stop Conditions
# Task: PERF-02.3
# Owner: Tuấn
# Reviewer: Hoàng

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-techx-tf4}"
CHECK_INTERVAL="${CHECK_INTERVAL:-30}"
LOG_FILE="load-test-monitor-$(date +%Y%m%d-%H%M%S).log"

# Thresholds
ERROR_RATE_THRESHOLD=5
CPU_THRESHOLD=90
MEMORY_THRESHOLD_PERCENT=85
LATENCY_THRESHOLD=5
NODE_COUNT_BASELINE=2

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

log_ok() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

stop_load_test() {
    local reason=$1
    log_error "STOPPING LOAD TEST"
    log_error "Reason: $reason"

    # Capture evidence before stopping
    log "Capturing evidence..."
    kubectl get pods -n "$NAMESPACE" -o wide > "evidence-pods-$(date +%Y%m%d-%H%M%S).txt" 2>&1
    kubectl top pods -n "$NAMESPACE" > "evidence-top-pods-$(date +%Y%m%d-%H%M%S).txt" 2>&1
    kubectl top nodes > "evidence-top-nodes-$(date +%Y%m%d-%H%M%S).txt" 2>&1

    # Scale down load generator
    kubectl scale deployment/load-generator --replicas=0 -n "$NAMESPACE" 2>&1 | tee -a "$LOG_FILE"

    log "Load test stopped. Log saved to: $LOG_FILE"
    log "Next steps:"
    log "  1. Review logs: cat $LOG_FILE"
    log "  2. Check Grafana: kubectl port-forward svc/frontend-proxy 8080:8080 -n $NAMESPACE"
    log "  3. Analyze root cause before resuming test"

    exit 1
}

check_error_rate() {
    # Check error logs in checkout (critical service)
    local error_count
    error_count=$(kubectl logs -n "$NAMESPACE" deployment/checkout --tail=100 2>/dev/null | \
        grep -c "ERROR" || echo 0)

    if [ "$error_count" -gt "$ERROR_RATE_THRESHOLD" ]; then
        stop_load_test "Error count ${error_count} exceeds threshold $ERROR_RATE_THRESHOLD in last 100 logs"
    fi

    log_ok "Error count: $error_count (threshold: $ERROR_RATE_THRESHOLD)"
}

check_cpu_usage() {
    local max_cpu
    max_cpu=$(kubectl top pods -n "$NAMESPACE" --no-headers 2>/dev/null | \
        awk '{gsub(/m/,"",$3); if ($3 ~ /^[0-9]+$/) print $3}' | \
        sort -nr | head -1 || echo 0)

    if [ "$max_cpu" -gt $((CPU_THRESHOLD * 10)) ]; then
        stop_load_test "CPU usage ${max_cpu}m exceeds threshold $((CPU_THRESHOLD * 10))m"
    fi

    log_ok "Max CPU: ${max_cpu}m (threshold: $((CPU_THRESHOLD * 10))m)"
}

check_memory_usage() {
    local max_mem
    max_mem=$(kubectl top pods -n "$NAMESPACE" --no-headers 2>/dev/null | \
        awk '{gsub(/Mi/,"",$4); if ($4 ~ /^[0-9]+$/) print $4}' | \
        sort -nr | head -1 || echo 0)

    # Assume 1000Mi average limit, 85% = 850Mi
    local threshold=850

    if [ "$max_mem" -gt "$threshold" ]; then
        stop_load_test "Memory usage ${max_mem}Mi exceeds threshold ${threshold}Mi"
    fi

    log_ok "Max Memory: ${max_mem}Mi (threshold: ${threshold}Mi)"
}

check_node_scaling() {
    local node_count
    node_count=$(kubectl get nodes --no-headers 2>/dev/null | wc -l || echo 0)

    if [ "$node_count" -gt "$NODE_COUNT_BASELINE" ]; then
        log_warn "Node count: $node_count (baseline: $NODE_COUNT_BASELINE)"
        log_warn "Cost impact: ~\$60/week per additional node"

        if [ "$node_count" -gt $((NODE_COUNT_BASELINE + 1)) ]; then
            stop_load_test "Excessive node scaling: $node_count nodes (baseline: $NODE_COUNT_BASELINE)"
        fi
    else
        log_ok "Node count: $node_count (baseline: $NODE_COUNT_BASELINE)"
    fi
}

check_load_generator_health() {
    local lg_cpu lg_mem
    lg_cpu=$(kubectl top pod -n "$NAMESPACE" -l app=load-generator --no-headers 2>/dev/null | \
        awk '{gsub(/%/,"",$3); print $3}' || echo 0)
    lg_mem=$(kubectl top pod -n "$NAMESPACE" -l app=load-generator --no-headers 2>/dev/null | \
        awk '{gsub(/Mi/,"",$4); print $4}' || echo 0)

    if [ "$lg_cpu" -gt 80 ]; then
        stop_load_test "Load generator CPU overloaded: ${lg_cpu}%"
    fi

    if [ "$lg_mem" -gt 1200 ]; then
        stop_load_test "Load generator memory overloaded: ${lg_mem}Mi / 1500Mi"
    fi

    log_ok "Load generator health: CPU ${lg_cpu}%, Memory ${lg_mem}Mi"
}

# Main monitoring loop
main() {
    log "====================================="
    log "Load Test Monitor Started"
    log "====================================="
    log "Namespace: $NAMESPACE"
    log "Check interval: ${CHECK_INTERVAL}s"
    log "Thresholds:"
    log "  - Error rate: ${ERROR_RATE_THRESHOLD} errors/100 logs"
    log "  - CPU: ${CPU_THRESHOLD}%"
    log "  - Memory: ${MEMORY_THRESHOLD_PERCENT}%"
    log "  - Latency: ${LATENCY_THRESHOLD}s"
    log "  - Node count: ${NODE_COUNT_BASELINE}"
    log "====================================="

    while true; do
        log ""
        log "--- Check Cycle $(date +%H:%M:%S) ---"

        check_error_rate
        check_cpu_usage
        check_memory_usage
        check_node_scaling
        check_load_generator_health

        log_ok "All checks passed"

        sleep "$CHECK_INTERVAL"
    done
}

# Run
main
