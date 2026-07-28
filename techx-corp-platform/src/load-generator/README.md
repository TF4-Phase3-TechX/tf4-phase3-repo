# Load Generator

The load generator creates simulated traffic to the demo.

## Accessing the Load Generator

You can access the web interface to Locust at `http://localhost:8080/loadgen/`. 

## Modifying the Load Generator

Please see the [Locust
documentation](https://docs.locust.io/en/2.16.0/writing-a-locustfile.html) to
learn more about modifying the locustfile.

## Paid AI traffic

Baseline load tests never call paid AI endpoints. The AI Assistant scenario is
defined as one sequential synthetic user and is created only when explicitly
enabled with attribution, a time window, and a request cap:

```text
LOCUST_PAID_AI_ENABLED=true
LOCUST_PAID_AI_OWNER=<accountable-person>
LOCUST_PAID_AI_RUN_ID=<unique-run-id>
LOCUST_PAID_AI_MAX_REQUESTS=25
LOCUST_PAID_AI_WINDOW_MINUTES=10
LOCUST_PAID_AI_WAIT_SECONDS=5
```

The loader fails closed when required values are missing. It rejects more than
500 requests, a window longer than 60 minutes, or a request interval below one
second. Reaching either the configured cap or window stops the paid-AI user;
ordinary storefront load continues.

The cap is enforced inside the single load-generator process used by this
deployment. Do not use this control unchanged with a distributed Locust worker
topology, where each worker would need a shared request budget.

## Mandate targeted load

The mixed Locust UI workload is useful for a healthy-busy or noise window, but
it does not reliably put enough traffic on one target service. The image also
contains `mandate_targeted_load.py` for the reviewed Mandate 15/22 drill
window.

The command is plan-only unless `--execute` is present. It requires an owner,
run ID, attempt cap, worker cap and pacing, pins traffic to the in-cluster
frontend proxy, adds owner/run attribution headers, and stops when the
configured rolling failure ratio is breached. One checkout attempt performs
two HTTP requests: cart preload and checkout.

```sh
python mandate_targeted_load.py \
  --scenario product-reviews \
  --owner tam \
  --run-id m22-20260728-calibration \
  --max-requests 500 \
  --workers 5 \
  --pace-seconds 0.10
```

After named approval, repeat with `--execute`. Supported scenarios are:

- `product-reviews`: repeatedly requests one product ID to maximize cache reuse
  and minimize unexpected Bedrock work. The operator must still monitor the
  `app_llm_calls_total` budget during the run;
- `checkout`: creates a unique cart and then submits one valid checkout
  workflow using `people.json`.

The JSON output is load evidence only. Always correlate it with Prometheus,
AIOps incident/audit output, Deployment readiness and the final GitOps restore.
