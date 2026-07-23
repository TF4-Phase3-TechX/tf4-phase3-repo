import subprocess
import time
import urllib.request
import urllib.parse
import json
import os
from datetime import datetime

NAMESPACE = "techx-observability"
DB_IDENTIFIER = "techx-tf4-postgresql"

# Target Time Window
START_TIME = "2026-07-22T23:33:00Z"
END_TIME = "2026-07-23T00:16:00Z"

# Epoch timestamps for PromQL
# 2026-07-22 23:33:00 UTC = 1784763180
# 2026-07-23 00:16:00 UTC = 1784765760
START_EPOCH = 1784763180
END_EPOCH = 1784765760

print("====================================================")
print("  D19 Bottleneck Telemetry Collector")
print("====================================================")

# 1. Start Port Forward in background for Prometheus
print("[1/3] Opening port-forward to Prometheus (localhost:19090)...")
prom_proc = subprocess.Popen(
    ["kubectl", "port-forward", "svc/prometheus", "19090:9090", "-n", NAMESPACE],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

try:
    # Wait for tunnel to establish
    time.sleep(5)
    
    def query_prometheus_range(ql):
        url = f"http://localhost:19090/api/v1/query_range?query={urllib.parse.quote(ql)}&start={START_EPOCH}&end={END_EPOCH}&step=60"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as response:
                res = json.loads(response.read().decode('utf-8'))
                if res.get('status') == 'success':
                    return res.get('data', {}).get('result', [])
        except Exception as e:
            print(f"  Error querying PromQL range '{ql}': {e}")
        return None

    print("[2/3] Querying EKS container metrics for product-reviews and product-catalog...")
    
    # Pod CPU utilization rate
    cpu_reviews = query_prometheus_range('sum(rate(container_cpu_usage_seconds_total{namespace="techx-tf4", container="product-reviews"}[5m])) by (pod)')
    cpu_catalog = query_prometheus_range('sum(rate(container_cpu_usage_seconds_total{namespace="techx-tf4", container="product-catalog"}[5m])) by (pod)')
    
    # Pod CPU throttling
    throttling_reviews = query_prometheus_range('sum(rate(container_cpu_cfs_throttled_seconds_total{namespace="techx-tf4", container="product-reviews"}[5m])) by (pod)')
    
    # Pod memory working set
    mem_reviews = query_prometheus_range('sum(container_memory_working_set_bytes{namespace="techx-tf4", container="product-reviews"}) by (pod)')
    mem_catalog = query_prometheus_range('sum(container_memory_working_set_bytes{namespace="techx-tf4", container="product-catalog"}) by (pod)')

    # 3. Query AWS CloudWatch for RDS metrics (techx-tf4-postgresql cluster)
    # Workaround CloudWatch narrow window limitations by querying a wider window and filtering in python
    print("[3/3] Querying CloudWatch RDS PostgreSQL metrics via AWS CLI...")
    rds_metrics = {}
    try:
        # Check AWS Caller Identity first to debug credentials
        try:
            identity_res = subprocess.run(["aws", "sts", "get-caller-identity", "--output", "json"], capture_output=True, text=True)
            print(f"  AWS Caller Identity: {identity_res.stdout.strip()}")
        except Exception as e:
            print(f"  Could not get AWS Caller Identity: {e}")

        query_start = "2026-07-22T23:00:00Z"
        query_end = "2026-07-23T01:00:00Z"

        def filter_datapoints(datapoints):
            filtered = []
            for dp in datapoints:
                # Timestamps from get-metric-statistics can be like "2026-07-22T23:55:00Z" or with offset
                ts_str = dp["Timestamp"]
                # Convert to UTC datetime for comparison
                # We can do simple string comparison since they are ISO format
                # e.g., 2026-07-22T23:33:00Z <= ts_str <= 2026-07-23T00:16:00Z
                # But need to normalize offset if present. Let's convert to UTC format.
                if "+" in ts_str:
                    # Parse with offset and convert to UTC
                    dt = datetime.strptime(ts_str.split("+")[0], "%Y-%m-%dT%H:%M:%S")
                    # simple approximation for the offset since we know it's +07:00
                    # subtract 7 hours to get UTC
                    import datetime as dt_mod
                    dt_utc = dt - dt_mod.timedelta(hours=7)
                    ts_utc = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    ts_utc = ts_str
                
                if "2026-07-22T23:33:00Z" <= ts_utc <= "2026-07-23T00:16:00Z":
                    filtered.append(dp)
            return sorted(filtered, key=lambda x: x["Timestamp"])

        # Query CPU
        cpu_cmd = f'aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name CPUUtilization --dimensions Name=DBClusterIdentifier,Value=techx-tf4-postgresql --start-time {query_start} --end-time {query_end} --period 300 --statistics Average --region us-east-1 --output json'
        res_cpu = subprocess.run(cpu_cmd, shell=True, capture_output=True, text=True, check=True)
        cpu_data = json.loads(res_cpu.stdout)
        raw_cpu_dps = cpu_data.get("Datapoints", [])
        rds_metrics["CPUUtilization"] = filter_datapoints(raw_cpu_dps)
        if not rds_metrics["CPUUtilization"]:
            print(f"  Debug: CPU Datapoints empty. Raw CLI Output: {res_cpu.stdout.strip()}")

        # Query Connections
        conn_cmd = f'aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name DatabaseConnections --dimensions Name=DBClusterIdentifier,Value=techx-tf4-postgresql --start-time {query_start} --end-time {query_end} --period 300 --statistics Average --region us-east-1 --output json'
        res_conn = subprocess.run(conn_cmd, shell=True, capture_output=True, text=True, check=True)
        conn_data = json.loads(res_conn.stdout)
        raw_conn_dps = conn_data.get("Datapoints", [])
        rds_metrics["DatabaseConnections"] = filter_datapoints(raw_conn_dps)
        if not rds_metrics["DatabaseConnections"]:
            print(f"  Debug: Connections Datapoints empty. Raw CLI Output: {res_conn.stdout.strip()}")
        
    except Exception as e:
        print(f"  Error querying CloudWatch RDS metrics: {e}")

    # Write output to a clean structured file
    output_path = "docs/evidence/mandate-19-Determine and raise the throughput/telemetry-bottleneck-raw.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    result_data = {
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "window": {
            "start": START_TIME,
            "end": END_TIME
        },
        "eks": {
            "product_reviews_cpu": cpu_reviews,
            "product_catalog_cpu": cpu_catalog,
            "product_reviews_throttling": throttling_reviews,
            "product_reviews_memory": mem_reviews,
            "product_catalog_memory": mem_catalog
        },
        "rds": rds_metrics
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2)
        
    print(f"Collection complete! Saved data to: {output_path}")
    print("====================================================")

    # Print brief summary
    if rds_metrics:
        print("\n--- RDS DATABASE METRICS SUMMARY ---")
        for metric_name, datapoints in rds_metrics.items():
            if datapoints:
                values = [dp["Average"] for dp in datapoints]
                print(f"  {metric_name}: Avg={sum(values)/len(values):.2f}, Max={max(values):.2f}, Min={min(values):.2f} (Data points: {len(values)})")

finally:
    # Cleanup port forward
    print("Cleaning up port-forward...")
    if prom_proc:
        prom_proc.terminate()
        prom_proc.wait()
    print("Cleanup done!")
