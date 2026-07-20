#!/usr/bin/env python3
"""Recompute C0G-51 reservations from captured Kubernetes YAML."""
import json
import math
from pathlib import Path

import yaml

ROOT = Path(__file__).parent


def cpu_m(value):
    text = str(value or "0")
    return int(float(text[:-1])) if text.endswith("m") else int(float(text) * 1000)


def mem_mi(value):
    text = str(value or "0")
    units = {"Ki": 1 / 1024, "Mi": 1, "Gi": 1024, "K": 1000 / 1024**2,
             "M": 1000**2 / 1024**2, "G": 1000**3 / 1024**2}
    for suffix, factor in units.items():
        if text.endswith(suffix):
            return math.ceil(float(text[:-len(suffix)]) * factor)
    return math.ceil(float(text) / 1024**2)


def amounts(containers):
    total = {"cpu_m": 0, "memory_mi": 0, "limit_cpu_m": 0, "limit_memory_mi": 0}
    missing = []
    for container in containers:
        resources = container.get("resources") or {}
        requests, limits = resources.get("requests") or {}, resources.get("limits") or {}
        for key, bucket, parser in (("cpu", "cpu_m", cpu_m), ("memory", "memory_mi", mem_mi)):
            if key not in requests:
                missing.append(f"{container.get('name')}: requests.{key}")
            else:
                total[bucket] += parser(requests[key])
            if key not in limits:
                missing.append(f"{container.get('name')}: limits.{key}")
            else:
                total[f"limit_{bucket}"] += parser(limits[key])
    return total, missing


def pod_request(pod):
    spec = pod.get("spec", {})
    regular, missing = amounts(spec.get("containers") or [])
    init, init_missing = amounts(spec.get("initContainers") or [])
    missing += init_missing
    # Kubernetes scheduler uses sum(regular) vs max(init) for each request dimension.
    request = {key: max(regular[key], init[key]) for key in regular}
    return request, missing


def add(left, right, multiplier=1):
    for key in right:
        left[key] += right[key] * multiplier


def scaled(amount, replicas):
    return {key: value * replicas for key, value in amount.items()}


rendered = [doc for doc in yaml.safe_load_all((ROOT / "10-rendered-app-manifests.yaml").read_text(encoding="utf-8-sig")) if doc]
deployments = [doc for doc in rendered if doc.get("kind") == "Deployment"]
hpas = {doc["metadata"]["name"]: doc["spec"] for doc in rendered if doc.get("kind") == "HorizontalPodAutoscaler"}

per_deployment = {}
base = {"cpu_m": 0, "memory_mi": 0, "limit_cpu_m": 0, "limit_memory_mi": 0}
hpa_max = base.copy()
rolling_surge = base.copy()
missing = {}
for deployment in deployments:
    name = deployment["metadata"]["name"]
    per_pod, absent = pod_request(deployment["spec"]["template"])
    if absent:
        missing[name] = absent
    hpa = hpas.get(name)
    replicas = int(hpa["minReplicas"]) if hpa else int(deployment["spec"].get("replicas", 1))
    maximum = int(hpa["maxReplicas"]) if hpa else replicas
    surge = math.ceil(replicas * 0.25)  # rendered Deployments use Kubernetes default maxSurge=25%.
    per_deployment[name] = {"replicas": replicas, "max_replicas": maximum, "max_surge_pods": surge, "per_pod": per_pod}
    add(base, per_pod, replicas)
    add(hpa_max, per_pod, maximum)
    add(rolling_surge, per_pod, maximum + surge)

live_pods = yaml.safe_load((ROOT / "03b-live-pods-all-namespaces-prevalidation.yaml").read_text(encoding="utf-8-sig"))["items"]
live_nodes = yaml.safe_load((ROOT / "04-live-nodes-prevalidation.yaml").read_text(encoding="utf-8-sig"))["items"]
node_allocatable = {node["metadata"]["name"]: {
    "cpu_m": cpu_m(node["status"]["allocatable"]["cpu"]),
    "memory_mi": mem_mi(node["status"]["allocatable"]["memory"]),
    "pods": int(node["status"]["allocatable"]["pods"]),
} for node in live_nodes}
node_reserved = {name: {"cpu_m": 0, "memory_mi": 0, "limit_cpu_m": 0, "limit_memory_mi": 0, "pods": 0} for name in node_allocatable}
namespace_reserved = {}
for pod in live_pods:
    if pod.get("status", {}).get("phase") not in {"Running", "Pending"}:
        continue
    node = pod.get("spec", {}).get("nodeName")
    reservation, _ = pod_request(pod)
    namespace = pod["metadata"]["namespace"]
    namespace_reserved.setdefault(namespace, {key: 0 for key in reservation})
    add(namespace_reserved[namespace], reservation)
    if node in node_reserved:
        add(node_reserved[node], reservation)
        node_reserved[node]["pods"] += 1

for node, reserved in node_reserved.items():
    alloc = node_allocatable[node]
    reserved["cpu_request_ratio"] = round(reserved["cpu_m"] / alloc["cpu_m"], 4)
    reserved["memory_request_ratio"] = round(reserved["memory_mi"] / alloc["memory_mi"], 4)
    reserved["pod_ratio"] = round(reserved["pods"] / alloc["pods"], 4)

output = {
    "assumptions": {
        "scheduler_request_formula": "sum regular containers vs maximum init-container resources per Pod",
        "hpa_baseline": "minReplicas",
        "hpa_worst_case": "maxReplicas",
        "rollout_surge": "ceil(25% of HPA-min replicas) added to every Deployment after all HPAs are at maximum; intentionally conservative simultaneous-rollout model",
    },
    "render_validation": {"deployment_count": len(deployments), "hpa_names": sorted(hpas), "missing_resource_fields": missing},
    "model_millicores_mebibytes": {"hpa_min": base, "hpa_max": hpa_max, "hpa_max_plus_global_surge": rolling_surge},
    "per_deployment": per_deployment,
    "live_namespace_reservations": namespace_reserved,
    "node_allocatable": node_allocatable,
    "node_reserved": node_reserved,
}
(ROOT / "14-reservation-calculation.json").write_text(json.dumps(output, indent=2) + "\n")
assert not missing, missing
assert len(deployments) == 22, len(deployments)
assert set(hpas) == {"checkout", "currency", "frontend"}, set(hpas)
print(json.dumps(output["model_millicores_mebibytes"], indent=2))
