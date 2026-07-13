# PERF-04.1 Evidence: Node Placement by Availability Zone

Capture time: 2026-07-09 13:47 +07:00

Command:

```bash
kubectl get nodes -L topology.kubernetes.io/zone
```

Output:

```text
NAME                          STATUS   ROLES    AGE     VERSION               ZONE
ip-10-0-10-231.ec2.internal   Ready    <none>   4h50m   v1.34.9-eks-7d6f6ec   us-east-1a
ip-10-0-11-40.ec2.internal    Ready    <none>   4h50m   v1.34.9-eks-7d6f6ec   us-east-1b
```

Finding:

- The cluster has two ready worker nodes.
- Worker nodes are distributed across two Availability Zones: `us-east-1a` and `us-east-1b`.

