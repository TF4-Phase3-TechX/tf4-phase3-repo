# Natural-Language Product Search MVP — Evaluation Framework

This directory contains the evaluation framework for **TF4AIO-4** (Natural-language product search MVP).

## Overview

The framework verifies that the `SearchProductsAIAssistant` gRPC RPC correctly:

1. Parses natural-language queries into structured search intents via AWS Bedrock (with application-level and `jsonschema` exact validation).
2. Filters the product catalog by category, price range, and keywords.
3. Refuses out-of-scope queries (general QA, math, coding, personal questions) and adversarial prompt injection attempts (DAN jailbreak, tag injection, prompt leaking, SQLi payloads, long-prefix buffer attacks).
4. Handles non-English queries (Vietnamese, French, Spanish) appropriately for search, refusal, and safety bounds.
5. Returns only products that exist in the real catalog (grounding shield).
6. Provides a complete evidence trace with token usage, latency, and estimated USD cost for every response.

## Directory Structure

| Path | Responsibility |
|------|---------------|
| `run_eval.py` | CLI Entrypoint: reads dataset, calls `SearchProductsAIAssistant` via gRPC, evaluates test cases, writes versioned evidence & report |
| `generate_dataset.py` | CLI Entrypoint: loads products → builds test cases → writes `eval_dataset.json` with SHA256 hash |
| `eval_dataset.json` | Generated test dataset (43 test cases; DO NOT edit manually — regenerate via `generate_dataset.py`) |
| `report.md` | Auto-generated markdown report summarizing historical and latest eval runs |
| `src/` | Core framework modules (`evaluator.py`, `grounding.py`, `dataset_builder.py`, `db_source.py`) |
| `tests/` | Unit tests for framework helpers (`test_run_eval_helpers.py`) |
| `evidence/` | Directory containing versioned run evidence folders (`YYYY-MM-DD-HH-mm/`) with `results.json`, `README.md`, and `snapshots/` |

## Intent Groups (D1 & Mandate 14 Compliance)

The dataset contains **43 test cases** across **8 intent groups**:

| Group | Count | Description | Expected Behavior |
|-------|-------|-------------|-------------------|
| `exact_match` | 3 | Query uses exact product name | Returns matching product(s) |
| `category` | 3 | Query filters by category (e.g., "telescopes") | Returns all products in that category |
| `price_range` | 3 | Query filters by price (e.g., "under $100") | Returns products within price range |
| `attribute_filter` | 3 | Combined category + price filter | Returns products matching both filters |
| `safety` | 13 | Out-of-domain queries (math, coding, financial, general QA) in EN/VI/ES/FR | Refused (`refused=true`, empty results) |
| `injection` | 13 | Adversarial prompt injection, DAN jailbreak, leaking, SQLi, tag overrides in EN/VI/ES/FR | Refused (`refused=true`, empty results) |
| `multilingual_search` | 3 | Vietnamese price & category search queries | Returns matching product(s) or refused if out of scope |
| `compare_edge_case` | 2 | Single-target & non-existent product comparison queries | Refused (`refused=true`, empty results) |

## Quick Start

### Prerequisites

- The `product-reviews` service must be running (via `docker compose up` in `techx-corp-platform/`)
- Python 3.10+ with the `product-reviews` virtual environment

### Generate Dataset

From the `techx-corp-platform/` directory:

```bash
make generate-nl-dataset
```

Or manually:

```bash
python3 tests/eval_natural_language_product_search_mvp/generate_dataset.py \
  --source sql \
  --sql-file techx-corp-platform/src/postgresql/init.sql
```

### Run Evaluation

From the `techx-corp-platform/` directory:

```bash
make run-nl-eval
```

Or manually (replace `PORT` with the actual gRPC port of `product-reviews`):

```bash
./src/product-reviews/venv/bin/python \
  ../tests/eval_natural_language_product_search_mvp/run_eval.py \
  --port PORT \
  --runtime-env local
```

### Read Results

- **Evidence JSON**: `evidence/results_<git_sha>_<timestamp>.json`
- **Report**: `report.md` (auto-generated from evidence files)

## Current Status

> [!IMPORTANT]
> The `SearchProductsAIAssistant` RPC has been added to `demo.proto` and implemented
> in `product_reviews_server.py`. Running the evaluation requires:
> 1. A running `product-reviews` service with the updated code (via Docker Compose)
> 2. AWS Bedrock credentials configured (for LLM intent parsing)
>
> If the RPC is not available, `run_eval.py` will raise a clear error — it will
> **never** mock the RPC or fabricate results.

## Evidence Rules

Every evidence file contains:

| Field | Description |
|-------|-------------|
| `git_sha` | Git commit hash at time of run |
| `timestamp_utc` | UTC timestamp of run |
| `runtime_env` | `local` / `staging` / `production` (explicitly declared) |
| `model_id` | Bedrock model ID used |
| `dataset_sha256` | SHA256 of the dataset used (verified before eval) |
| `results` | Per-test-case pass/fail with evaluator output |

**Anti-fabrication guarantees:**

- Number of evidence files on disk = number of runs claimed in report
- Dataset hash in evidence must match hash recomputed from `eval_dataset.json`
- All results come from real gRPC calls — no mocks, no hardcoded passes
- Unknown/ambiguous results fail closed (`passed=false`)

## Schema Assumptions (Verified)

These were verified against the actual repository before building this framework:

- `catalog.products` columns: `id`, `name`, `description`, `picture`, `price_currency_code`, `price_units`, `price_nanos`, `categories`
- `categories` is a comma-separated text field (e.g., `'accessories,telescopes'`)
- Price = `price_units + price_nanos / 1_000_000_000` (e.g., units=101, nanos=960000000 → $101.96)
- `ProductCatalogService.ListProducts(Empty)` returns all 10 products
- `ProductReviewService.SearchProductsAIAssistant` is the new RPC for NL search

## Reproduction

From a clean git clone:

```bash
# 1. Start services
cd techx-corp-platform
docker compose up -d

# 2. Generate dataset
make generate-nl-dataset

# 3. Run evaluation
make run-nl-eval
```

Results will differ across runs due to LLM non-determinism (temperature=0 reduces but
does not eliminate variance). The dataset hash and product catalog are deterministic.
