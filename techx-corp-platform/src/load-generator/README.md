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
