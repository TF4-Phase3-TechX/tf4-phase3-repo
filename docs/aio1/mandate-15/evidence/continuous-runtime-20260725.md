# Continuous AIOps runtime capture — 2026-07-25

**Captured at:** `2026-07-25T05:26:52Z`  
**Namespace:** `techx-tf4`  
**Capture type:** Read-only Kubernetes API query  
**Deployment source:** [GitOps PR #118](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/118), merged as `ff8071fc07d7818a2466bc1011760373e0868a76`

## Reproduction commands

Run with a valid read-only kubeconfig and AWS profile:

```powershell
kubectl -n techx-tf4 get deploy aiops `
  -o custom-columns='NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas,AVAILABLE:.status.availableReplicas,IMAGE:.spec.template.spec.containers[0].image' `
  --no-headers

kubectl -n techx-tf4 get pods `
  -l app.kubernetes.io/name=aiops `
  -o custom-columns='NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,START:.status.startTime,IMAGE:.status.containerStatuses[0].imageID' `
  --no-headers
```

## Captured output

```text
aiops   1   1   1   511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:c2560b9-aiops@sha256:c9e386038d1e75e28a8ef1627fdb35435db1d0a1343c0402dc2bc6749556f01d

aiops-b64656f5b-hbd88   true   0   2026-07-24T13:43:16Z   511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:c9e386038d1e75e28a8ef1627fdb35435db1d0a1343c0402dc2bc6749556f01d
```

The Deployment also reported `generation=9`, `observedGeneration=9`,
`replicas=1`, `updatedReplicas=1`, `readyReplicas=1` and
`availableReplicas=1`.

## Claim boundary

This capture proves that the detector was a standing, reconciled in-cluster
workload on the stated image at the capture time. It does not by itself prove
long-run availability, detector accuracy, alert delivery or organizer
acceptance.
